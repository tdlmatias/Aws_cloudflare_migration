"""Pure, deterministic analysis helpers used by the migration agent's tools.

Every function here is free of I/O, network, and third-party dependencies so it
can be unit-tested without AWS, Cloudflare, or an Anthropic API key. The agent
tools in :mod:`migration.agent.tools` wrap these with subprocess/filesystem
calls; keeping the logic here means the error-prone parts (classification,
diffing, plan interpretation, DNS comparison) are covered by fast unit tests.
"""

from __future__ import annotations

from typing import Any

# Review reasons that MUST be resolved before a production apply (per
# docs/MIGRATION_RUNBOOK.md §3). Everything else is informational or handled
# manually in Cloudflare.
BLOCKING_REVIEW_REASONS = frozenset({"invalid_mx", "empty_record_set"})


def classify_manual_review(review_doc: dict[str, Any]) -> dict[str, Any]:
    """Summarise a ``manual-review.json`` document.

    Returns counts per ``reason``, the number of alias records, and a list of
    *blocking* items (malformed input that must be fixed before apply). A
    ``ready_for_apply`` flag is true only when nothing blocking remains.
    """
    review_records = review_doc.get("review_records", [])
    alias_records = review_doc.get("alias_records", [])

    reason_counts: dict[str, int] = {}
    blockers: list[dict[str, Any]] = []
    for item in review_records:
        reason = item.get("reason", "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if reason in BLOCKING_REVIEW_REASONS:
            blockers.append(
                {
                    "zone": item.get("zone"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "reason": reason,
                    "detail": item.get("detail"),
                }
            )

    return {
        "alias_count": len(alias_records),
        "review_count": len(review_records),
        "reason_counts": dict(sorted(reason_counts.items())),
        "blockers": blockers,
        "ready_for_apply": not blockers,
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


def _normalise_rrset(values: list[str]) -> list[str]:
    """Normalise a set of DNS answers for order-independent comparison."""
    return sorted(v.strip().rstrip(".").lower() for v in values if v.strip())


def compare_rrset(expected: list[str], observed: list[str]) -> dict[str, Any]:
    """Compare an expected answer set against what a nameserver actually returned.

    Comparison is order-independent and ignores trailing dots and case, matching
    how :mod:`migration.converter` normalises records. Returns the missing and
    unexpected values and a ``match`` flag.
    """
    exp = _normalise_rrset(expected)
    obs = _normalise_rrset(observed)
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
    """
    answers: dict[str, list[str]] = {}
    for zone in zones_doc.get("zones", []):
        if zone["name"] != zone_name:
            continue
        for record in zone.get("records", []):
            key = f"{record['name']} {record['type']}"
            content = record["content"]
            if record["type"] == "MX" and record.get("priority") is not None:
                content = f"{record['priority']} {content}"
            answers.setdefault(key, []).append(content)
    return {key: sorted(vals) for key, vals in sorted(answers.items())}
