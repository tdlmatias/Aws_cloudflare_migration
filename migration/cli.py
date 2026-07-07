"""Command-line interface for the migration tooling.

Subcommands
-----------
``convert``   Read a Route53 export and emit ``zones.json`` + a review report.
``validate``  Validate an existing ``zones.json`` against the bundled schema.

The CLI performs no network calls; the AWS export is done separately by
``scripts/export_route53.sh`` (which shells out to the AWS CLI). This keeps the
transformation logic fully testable without credentials.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from migration.converter import convert_hosted_zones
from migration.io import read_json, write_json_atomic
from migration.schema import SchemaValidationError, validate_document


def _load_record_sets(records_dir: Path, hosted_zones: list[dict]) -> dict[str, list[dict]]:
    mapping: dict[str, list[dict]] = {}
    for zone in hosted_zones:
        zone_id = zone["Id"].split("/")[-1]
        records_path = records_dir / f"records-{zone_id}.json"
        if not records_path.exists():
            raise FileNotFoundError(
                f"Missing record export for zone {zone_id}: expected {records_path}"
            )
        mapping[zone_id] = read_json(records_path)["ResourceRecordSets"]
    return mapping


def cmd_convert(args: argparse.Namespace) -> int:
    hosted_zones = read_json(args.zones)["HostedZones"]
    record_sets = _load_record_sets(args.records_dir, hosted_zones)

    result = convert_hosted_zones(
        hosted_zones,
        record_sets,
        allow_private_zones=args.allow_private_zones,
    )

    zones_doc = result.zones_document()
    review_doc = result.review_document()

    if not args.no_validate:
        validate_document(zones_doc, "zones")
        validate_document(review_doc, "review")

    write_json_atomic(args.output, zones_doc)
    write_json_atomic(args.review_output, review_doc)

    zone_count = len(result.zones)
    record_count = sum(len(z["records"]) for z in result.zones)
    review_count = len(result.review_records)
    alias_count = len(result.alias_records)
    print(
        f"Wrote {args.output} ({zone_count} zones, {record_count} records) and "
        f"{args.review_output} ({alias_count} aliases, {review_count} review items)."
    )
    if review_count or alias_count:
        print(
            f"NOTE: {alias_count + review_count} item(s) need manual review; "
            f"see {args.review_output}.",
            file=sys.stderr,
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    document = read_json(args.document)
    validate_document(document, args.schema)
    print(f"{args.document} is valid against the '{args.schema}' schema.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migration", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="Convert a Route53 export to zones.json")
    convert.add_argument("--zones", required=True, type=Path, help="hosted-zones.json")
    convert.add_argument(
        "--records-dir", required=True, type=Path, help="Directory with records-<id>.json"
    )
    convert.add_argument("--output", required=True, type=Path, help="zones.json output path")
    convert.add_argument(
        "--review-output", required=True, type=Path, help="Manual-review report output path"
    )
    convert.add_argument(
        "--allow-private-zones",
        action="store_true",
        help="Migrate private hosted zones instead of routing them to review (unsafe).",
    )
    convert.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSON Schema validation of the generated documents.",
    )
    convert.set_defaults(func=cmd_convert)

    validate = sub.add_parser("validate", help="Validate a document against a schema")
    validate.add_argument("document", type=Path, help="Document to validate")
    validate.add_argument(
        "--schema", default="zones", choices=["zones", "review"], help="Schema name"
    )
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, SchemaValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
