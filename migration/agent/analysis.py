"""Pure, deterministic analysis helpers used by the migration agent's tools.

Every function here is free of I/O, network, and third-party dependencies so it
can be unit-tested without AWS, Cloudflare, or an Anthropic API key. The agent
tools in :mod:`migration.agent.tools` wrap these with subprocess/filesystem
calls; keeping the logic here means the error-prone parts (classification,
diffing, plan interpretation, DNS comparison) are covered by fast unit tests.
"""

from __future__ import annotations

from typing import Any

from migration.converter import unquote_txt

# Review reasons that MUST be fixed at source before a production apply because
# they represent malformed input (per docs/MIGRATION_RUNBOOK.md §3).
BLOCKING_REVIEW_REASONS = frozenset({"invalid_mx", "empty_record_set"})

# The only review reason that needs no operator action: Cloudflare manages SOA
# and zone-apex NS automatically. Every OTHER review item (aliases, routing
# policies, CAA/SRV, unsupported types) is omitted from zones.json, so it is
# silently absent from the Terraform plan until a human maps it in Cloudflare.
MANAGED_REVIEW_REASONS = frozenset({"skipped_managed"})


def classify_manual_review(review_doc: dict[str, Any]) -> dict[str, Any]:
    """Summarise a ``manual-review.json`` document.

    Returns counts per ``reason``, the alias count, the subset of *blocking*
    items (malformed input that must be fixed), and ``requires_action`` — every
    item that is missing from ``zones.json`` and needs an operator decision
    (aliases plus any non-managed review record). ``ready_for_apply`` is true
    only when nothing needs action: no blockers AND no unresolved aliases or
    non-managed records. Reporting ready-to-apply while, say, an apex alias is
    silently absent from the plan would be dangerous, so managed items
    (Cloudflare-owned SOA/apex NS) are the only ones that do not gate.
    """
    review_records = review_doc.get("review_records", [])
    alias_records = review_doc.get("alias_records", [])

    reason_counts: dict[str, int] = {}
    blockers: list[dict[str, Any]] = []
    requires_action: list[dict[str, Any]] = []

    for alias in alias_records:
        requires_action.append(
            {
                "zone": alias.get("zone"),
                "name": alias.get("name"),
                "type": alias.get("type"),
                "reason": "alias_record",
                "detail": alias.get("detail"),
            }
        )

    for item in review_records:
        reason = item.get("reason", "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        entry = {
            "zone": item.get("zone"),
            "name": item.get("name"),
            "type": item.get("type"),
            "reason": reason,
            "detail": item.get("detail"),
        }
        if reason in BLOCKING_REVIEW_REASONS:
            blockers.append(entry)
            requires_action.append(entry)
        elif reason not in MANAGED_REVIEW_REASONS:
            requires_action.append(entry)

    return {
        "alias_count": len(alias_records),
        "review_count": len(review_records),
        "reason_counts": dict(sorted(reason_counts.items())),
        "blockers": blockers,
        "requires_action": requires_action,
        "ready_for_apply": not requires_action,
    }


def zone_record_counts(zones_doc: dict[str, Any]) -> dict[str, int]:
    """Map each zone name to its record count from a ``zones.json`` document."""
    return {zone["name"]: len(zone.get("records", [])) for zone in zones_doc.get("zones", [])}


def diff_record_counts(
    baseline: dict[str, int],
    current: dict[str, int],
    *,
    drop_ratio_threshold: float = 0.5,
) -> dict[str, Any]:
    """Compare a saved baseline (zone -> record count) against the current export.

    The baseline is captured from Route53 before migrating (runbook §1b step 3).
    Flags the dangerous cases that indicate an incomplete or wrong export:
    zones that vanished entirely, and zones whose record count dropped by more
    than ``drop_ratio_threshold``. ``safe`` is true only when neither occurs.
    """
    missing_zones = sorted(set(baseline) - set(current))
    new_zones = sorted(set(current) - set(baseline))

    dropped: list[dict[str, Any]] = []
    for zone in sorted(set(baseline) & set(current)):
        before = baseline[zone]
        after = current[zone]
        if before > 0 and after < before * (1 - drop_ratio_threshold):
            dropped.append({"zone": zone, "baseline": before, "current": after})

    return {
        "missing_zones": missing_zones,
        "new_zones": new_zones,
        "significant_drops": dropped,
        "baseline_total": sum(baseline.values()),
        "current_total": sum(current.values()),
        "safe": not missing_zones and not dropped,
    }


# Terraform plan action semantics from ``terraform show -json <plan>``.
_DESTRUCTIVE = ("delete",)


def summarize_terraform_plan(plan_json: dict[str, Any]) -> dict[str, Any]:
    """Summarise a ``terraform show -json <plan>`` document.

    Counts resource changes by action and, crucially, surfaces any resource
    that will be **destroyed** or **replaced** — the single most important
    signal before an apply (runbook §5: "no unexpected destroy actions").
    ``no_destroys`` is true only when nothing is deleted or replaced.
    """
    counts = {"create": 0, "update": 0, "delete": 0, "replace": 0, "no-op": 0, "read": 0}
    destroys: list[dict[str, Any]] = []

    for change in plan_json.get("resource_changes", []):
        actions = change.get("change", {}).get("actions", [])
        # A replace is represented as ["delete", "create"] or ["create", "delete"].
        if "delete" in actions and "create" in actions:
            counts["replace"] += 1
            destroys.append({"address": change.get("address"), "action": "replace"})
            continue
        for action in actions:
            counts[action] = counts.get(action, 0) + 1
            if action in _DESTRUCTIVE:
                destroys.append({"address": change.get("address"), "action": action})

    return {
        "counts": counts,
        "destroys": destroys,
        "no_destroys": not destroys,
    }


def _normalise_value(value: str, record_type: str, *, is_observed: bool) -> str:
    """Normalise a single DNS answer for comparison, per record type.

    Domain-name and address payloads (A/AAAA/CNAME/MX/NS) are compared
    case-insensitively with any trailing dot removed. TXT payloads are compared
    **byte-faithfully** (case preserved, no trailing-dot stripping) — a DKIM
    ``p=`` base64 key is case-sensitive, so lowercasing it would turn a real
    mismatch into a false match.

    The two sides are shaped differently for TXT: the expected value is the
    already-unquoted content stored in ``zones.json`` and is compared verbatim —
    NOT stripped, so a payload with meaningful leading/trailing spaces is not
    silently equated with one missing them. The observed ``dig +short`` answer is
    wrapped in double quotes (long records split into multiple quoted chunks), so
    only the observed side is run through
    :func:`migration.converter.unquote_txt`; stripping there removes just the
    presentation whitespace around the quotes, never bytes inside them.
    """
    if record_type == "TXT":
        return unquote_txt(value.strip()) if is_observed else value
    return value.strip().rstrip(".").lower()


def _normalise_rrset(values: list[str], record_type: str, *, is_observed: bool) -> list[str]:
    """Normalise a set of DNS answers for order-independent comparison."""
    return sorted(
        _normalise_value(v, record_type, is_observed=is_observed) for v in values if v.strip()
    )


def compare_rrset(
    expected: list[str], observed: list[str], record_type: str = ""
) -> dict[str, Any]:
    """Compare an expected answer set against what a nameserver actually returned.

    Comparison is order-independent. Normalisation depends on ``record_type``:
    domain/address payloads ignore case and trailing dots; TXT payloads are
    compared faithfully (see :func:`_normalise_value`), unquoting only the
    observed (``dig``) side. Returns the missing and unexpected values and a
    ``match`` flag.
    """
    exp = _normalise_rrset(expected, record_type, is_observed=False)
    obs = _normalise_rrset(observed, record_type, is_observed=True)
    missing = sorted(set(exp) - set(obs))
    unexpected = sorted(set(obs) - set(exp))
    return {
        "expected": exp,
        "observed": obs,
        "missing": missing,
        "unexpected": unexpected,
        "match": not missing and not unexpected,
    }


def expected_answers_for_zone(zones_doc: dict[str, Any], zone_name: str) -> dict[str, list[str]]:
    """Group a zone's intended records into ``"<name> <TYPE>" -> [content, ...]``.

    Used by the DNS-verification tool to know what each Cloudflare nameserver
    *should* answer before cutover. MX content is prefixed with its priority to
    match ``dig``'s ``<priority> <host>`` answer format.

    **Proxied records are excluded.** A record with ``proxied: true`` resolves to
    Cloudflare edge addresses (and a proxied CNAME is flattened), not its origin
    ``content``, so comparing the origin content to the nameserver answer would
    always mismatch. Proxied records cannot be origin-verified this way; list
    them with :func:`proxied_record_keys` and check them another way.
    """
    answers: dict[str, list[str]] = {}
    for zone in zones_doc.get("zones", []):
        if zone["name"] != zone_name:
            continue
        for record in zone.get("records", []):
            if record.get("proxied"):
                continue
            key = f"{record['name']} {record['type']}"
            content = record["content"]
            if record["type"] == "MX" and record.get("priority") is not None:
                content = f"{record['priority']} {content}"
            answers.setdefault(key, []).append(content)
    return {key: sorted(vals) for key, vals in sorted(answers.items())}


def verification_passed(
    *, verified_count: int, all_match: bool, skipped_proxied_count: int
) -> bool:
    """Decide whether the origin-verification cutover gate is satisfied.

    The gate passes only when at least one record was actually origin-verified,
    every verified record matched, AND no proxied record was left unverified.
    This prevents a false pass for a zone with no origin-verifiable records
    (e.g. an all-proxied zone), where ``all_match`` is vacuously true because no
    query ran. Proxied records must be confirmed another way (or explicitly
    attested by the operator) before cutover.
    """
    return verified_count > 0 and all_match and skipped_proxied_count == 0


def proxied_record_keys(zones_doc: dict[str, Any], zone_name: str) -> list[str]:
    """Return ``"<name> <TYPE>"`` keys for the zone's proxied records.

    These are skipped by :func:`expected_answers_for_zone` because the Cloudflare
    edge, not the origin, answers for them — the verification tool reports them so
    an operator knows they were not origin-verified.
    """
    keys = {
        f"{record['name']} {record['type']}"
        for zone in zones_doc.get("zones", [])
        if zone["name"] == zone_name
        for record in zone.get("records", [])
        if record.get("proxied")
    }
    return sorted(keys)
