#!/usr/bin/env python3
import argparse
import json
import pathlib


SUPPORTED_TYPES = {"A", "AAAA", "CNAME", "TXT", "MX", "CAA", "SRV", "NS"}


def load_json(path: pathlib.Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def strip_trailing_dot(value: str) -> str:
    return value[:-1] if value.endswith(".") else value


def normalize_txt(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def split_mx_value(value: str):
    parts = value.split()
    if len(parts) < 2:
        return None, value
    return int(parts[0]), strip_trailing_dot(" ".join(parts[1:]))


def record_name_for_zone(record_name: str, zone_name: str) -> str:
    record_name = strip_trailing_dot(record_name)
    zone_name = strip_trailing_dot(zone_name)
    if record_name == zone_name:
        return "@"
    if record_name.endswith(f".{zone_name}"):
        return record_name[: -(len(zone_name) + 1)]
    return record_name


def expand_record(zone_name: str, record_set: dict):
    record_type = record_set["Type"]
    if record_type not in SUPPORTED_TYPES:
        return [], None

    name = record_name_for_zone(record_set["Name"], zone_name)
    ttl = record_set.get("TTL", 300)

    if "AliasTarget" in record_set:
        return [], {
            "name": name,
            "type": record_type,
            "target": record_set["AliasTarget"]["DNSName"],
            "note": "AliasTarget requires manual mapping in Cloudflare.",
        }

    records = []
    for rr in record_set.get("ResourceRecords", []):
        value = rr["Value"]
        entry = {"name": name, "type": record_type, "ttl": ttl}
        if record_type == "TXT":
            entry["value"] = normalize_txt(value)
        elif record_type == "MX":
            priority, host = split_mx_value(value)
            entry["priority"] = priority
            entry["value"] = host
        else:
            entry["value"] = strip_trailing_dot(value)
        records.append(entry)
    return records, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zones", required=True, type=pathlib.Path)
    parser.add_argument("--records-dir", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--alias-output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    hosted_zones = load_json(args.zones)["HostedZones"]
    zones_output = []
    alias_records = []

    for zone in hosted_zones:
        zone_id = zone["Id"].split("/")[-1]
        zone_name = strip_trailing_dot(zone["Name"])
        records_path = args.records_dir / f"records-{zone_id}.json"
        record_sets = load_json(records_path)["ResourceRecordSets"]

        records = []
        for record_set in record_sets:
            expanded, alias_entry = expand_record(zone_name, record_set)
            records.extend(expanded)
            if alias_entry:
                alias_entry["zone"] = zone_name
                alias_records.append(alias_entry)

        zones_output.append(
            {
                "id": zone_id,
                "name": zone_name,
                "records": records,
            }
        )

    args.output.write_text(
        json.dumps({"zones": zones_output}, indent=2), encoding="utf-8"
    )
    args.alias_output.write_text(
        json.dumps({"alias_records": alias_records}, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
