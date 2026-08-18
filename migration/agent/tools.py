"""Tools exposed to the migration agent.

Each tool wraps a deterministic, low-risk step of the migration pipeline. They
are intentionally limited to **read, validate, and verify** operations plus the
read-only Route53 export. There is deliberately NO tool that runs
``terraform apply`` or changes registrar nameservers — those irreversible steps
stay behind the human-gated GitHub workflows. See :mod:`migration.agent` for the
safety rationale; do not add a mutating tool here.

Tool results are returned as compact JSON strings so the model always parses
structured data rather than scraping prose.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from anthropic import beta_tool

from migration.agent import analysis
from migration.io import read_json
from migration.schema import SchemaValidationError, validate_document

# Repository root, resolved from this file so tools work from any cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _ok(**payload: Any) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _err(message: str, **payload: Any) -> str:
    return json.dumps({"ok": False, "error": message, **payload}, ensure_ascii=False)


def _resolve(path: str) -> Path:
    """Resolve a path relative to the repo root when it is not absolute."""
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


@beta_tool
def run_route53_export(output_dir: str = "terraform/data") -> str:
    """Run the read-only Route53 export and report zone/record counts.

    Shells out to scripts/export_route53.sh, which needs the AWS CLI
    authenticated with read-only Route53 access (this only reads Route53; it
    never changes any infrastructure). On success, returns the number of zones,
    total records, and a classification of the manual-review report.

    Args:
        output_dir: Directory (relative to the repo root unless absolute) where
            zones.json and manual-review.json are written. Defaults to
            terraform/data.
    """
    script = REPO_ROOT / "scripts" / "export_route53.sh"
    if not script.exists():
        return _err(f"export script not found at {script}")
    if shutil.which("aws") is None:
        return _err("the 'aws' CLI is not installed or not on PATH; cannot export Route53")

    out = _resolve(output_dir)
    try:
        proc = subprocess.run(
            ["bash", str(script), str(out)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        return _err("export timed out after 600s")
    if proc.returncode != 0:
        return _err("export failed", stderr=proc.stderr[-2000:])

    try:
        zones_doc = read_json(out / "zones.json")
        review_doc = read_json(out / "manual-review.json")
    except FileNotFoundError as exc:
        return _err(f"export produced no output: {exc}")

    counts = analysis.zone_record_counts(zones_doc)
    return _ok(
        zones_json=str(out / "zones.json"),
        review_json=str(out / "manual-review.json"),
        zone_count=len(counts),
        record_total=sum(counts.values()),
        records_per_zone=counts,
        manual_review=analysis.classify_manual_review(review_doc),
    )


@beta_tool
def validate_zones_document(zones_file: str = "terraform/data/zones.json") -> str:
    """Validate a zones.json document against the bundled JSON Schema.

    Args:
        zones_file: Path (relative to the repo root unless absolute) to the
            zones.json to validate.
    """
    path = _resolve(zones_file)
    try:
        document = read_json(path)
    except FileNotFoundError:
        return _err(f"file not found: {path}")
    try:
        validate_document(document, "zones")
    except SchemaValidationError as exc:
        return _err("schema validation failed", detail=str(exc))
    counts = analysis.zone_record_counts(document)
    return _ok(valid=True, zone_count=len(counts), record_total=sum(counts.values()))


@beta_tool
def summarize_manual_review(review_file: str = "terraform/data/manual-review.json") -> str:
    """Classify the manual-review report and flag items that block an apply.

    Blocking reasons (malformed input that must be fixed before apply):
    invalid_mx, empty_record_set. Everything else is informational or handled
    manually in Cloudflare (aliases, routing policies, CAA/SRV, private zones).

    Args:
        review_file: Path (relative to the repo root unless absolute) to the
            manual-review.json produced by the export.
    """
    path = _resolve(review_file)
    try:
        review_doc = read_json(path)
    except FileNotFoundError:
        return _err(f"file not found: {path}")
    return _ok(**analysis.classify_manual_review(review_doc))


@beta_tool
def diff_record_counts(
    baseline_file: str,
    zones_file: str = "terraform/data/zones.json",
) -> str:
    """Compare the current export against a pre-migration Route53 baseline.

    Flags zones that disappeared or lost more than half their records, which
    indicate an incomplete or wrong export that would cause a destructive apply.

    Args:
        baseline_file: Path to a JSON object mapping each zone name to its
            Route53 record count, captured before migrating (runbook §1b).
        zones_file: Path to the current zones.json. Defaults to
            terraform/data/zones.json.
    """
    baseline_path = _resolve(baseline_file)
    zones_path = _resolve(zones_file)
    try:
        baseline = read_json(baseline_path)
        zones_doc = read_json(zones_path)
    except FileNotFoundError as exc:
        return _err(f"file not found: {exc}")
    if not isinstance(baseline, dict):
        return _err("baseline must be a JSON object mapping zone name -> record count")
    current = analysis.zone_record_counts(zones_doc)
    return _ok(**analysis.diff_record_counts(baseline, current))


@beta_tool
def summarize_terraform_plan(plan_json_file: str) -> str:
    """Summarise a Terraform plan and surface any destroy/replace actions.

    The input is the JSON produced by ``terraform show -json <plan>`` (a human
    or CI generates the plan; this agent only reads and summarises it — it never
    applies). A non-empty ``destroys`` list is a hard stop before apply.

    Args:
        plan_json_file: Path to the ``terraform show -json`` output of a plan.
    """
    path = _resolve(plan_json_file)
    try:
        plan = read_json(path)
    except FileNotFoundError:
        return _err(f"file not found: {path}")
    return _ok(**analysis.summarize_terraform_plan(plan))


def _dig(nameserver: str, fqdn: str, record_type: str) -> list[str]:
    proc = subprocess.run(
        ["dig", f"@{nameserver}", fqdn, record_type, "+short"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


@beta_tool
def verify_cloudflare_records(
    zone: str,
    nameserver: str,
    zones_file: str = "terraform/data/zones.json",
) -> str:
    """Verify a zone resolves on a Cloudflare nameserver as zones.json intends.

    For every intended record in the zone, queries the given Cloudflare
    nameserver directly (with ``dig``) and compares the answer to what
    zones.json says it should be — the pre-cutover verification gate (runbook
    §8). Run this BEFORE switching registrar nameservers. ``all_match`` is true
    only when every record matches.

    Args:
        zone: The zone apex name, e.g. example.com.
        nameserver: A Cloudflare nameserver assigned to the zone, from the
            Cloudflare dashboard, e.g. dana.ns.cloudflare.com.
        zones_file: Path to the zones.json describing the intended records.
    """
    if shutil.which("dig") is None:
        return _err("the 'dig' tool is not installed or not on PATH")
    path = _resolve(zones_file)
    try:
        zones_doc = read_json(path)
    except FileNotFoundError:
        return _err(f"file not found: {path}")

    expected = analysis.expected_answers_for_zone(zones_doc, zone)
    skipped_proxied = analysis.proxied_record_keys(zones_doc, zone)
    if not expected and not skipped_proxied:
        return _err(f"zone {zone!r} not found in {path} (or it has no records)")

    results = []
    all_match = True
    for key, exp_values in expected.items():
        name, record_type = key.split(" ")
        fqdn = zone if name == "@" else f"{name}.{zone}"
        try:
            observed = _dig(nameserver, fqdn, record_type)
        except subprocess.TimeoutExpired:
            results.append({"record": key, "error": "dig timed out"})
            all_match = False
            continue
        comparison = analysis.compare_rrset(exp_values, observed, record_type)
        all_match = all_match and comparison["match"]
        results.append({"record": key, "fqdn": fqdn, **comparison})

    fully_verified = analysis.verification_passed(
        verified_count=len(expected),
        all_match=all_match,
        skipped_proxied_count=len(skipped_proxied),
    )
    return _ok(
        zone=zone,
        nameserver=nameserver,
        # all_match reflects only the origin-verifiable (unproxied) records that
        # were queried; it is vacuously true when nothing was queried.
        all_match=all_match,
        records=results,
        # Proxied records resolve to the Cloudflare edge, not the origin content,
        # so they are not origin-verified here — the operator checks them another
        # way (e.g. that the proxied hostname serves the expected app).
        skipped_proxied=skipped_proxied,
        # The actual cutover gate: passes only when records were origin-verified,
        # all matched, and nothing proxied was left unverified. Do not treat this
        # zone as verified for cutover unless fully_verified is true (or a human
        # has attested the proxied records separately).
        fully_verified=fully_verified,
    )


# The complete, capability-gated tool set. Adding a mutating tool (apply,
# registrar change) here would break the safety boundary documented in
# migration/agent/__init__.py.
ALL_TOOLS: list[Any] = [
    run_route53_export,
    validate_zones_document,
    summarize_manual_review,
    diff_record_counts,
    summarize_terraform_plan,
    verify_cloudflare_records,
]
