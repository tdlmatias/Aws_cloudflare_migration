"""Pure, deterministic Route53 -> Cloudflare record conversion.

The functions in this module are intentionally free of I/O so they can be unit
tested without AWS access. :func:`convert_hosted_zones` takes already-parsed
Route53 JSON (as produced by ``aws route53 list-hosted-zones`` and
``aws route53 list-resource-record-sets``) and returns a :class:`ConversionResult`.

Design decisions (see docs/ARCHITECTURE.md and docs/AUDIT_REPORT.md):

* Output uses the Cloudflare key ``content`` (not ``value``) so the generated
  document is directly consumable by the Terraform configuration.
* Nothing is ever silently discarded. Records that cannot be migrated
  automatically are routed to ``review_records`` (or ``alias_records``) with an
  explicit reason, so an engineer can act on them.
* ``SOA`` and zone-apex ``NS`` records are dropped on purpose because Cloudflare
  manages those automatically; they are still reported (as ``skipped_managed``)
  for auditability.
* Output ordering is deterministic so repeated runs over identical input
  produce byte-for-byte identical files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Bump the MINOR version for backwards-compatible additions to the emitted
# document and the MAJOR version for breaking changes. schemas/zones.schema.json
# and schemas/review.schema.json are versioned in lock-step.
SCHEMA_VERSION = "1.1.0"

# Record types converted directly into Cloudflare DNS records.
DIRECT_TYPES = frozenset({"A", "AAAA", "CNAME", "TXT", "MX", "NS"})

# Record types that are parsed but routed to manual review because the
# Cloudflare v5 provider expects a structured ``data`` block for them rather
# than a scalar ``content`` value. The converter parses their components so a
# human (or future automation) can map them without re-parsing Route53 output.
REVIEW_TYPES = frozenset({"CAA", "SRV"})

# Keys that indicate a Route53 routing policy which has no Cloudflare
# equivalent and must be reviewed by a human before cutover.
ROUTING_POLICY_KEYS = (
    "Weight",
    "Region",
    "Failover",
    "GeoLocation",
    "GeoProximityLocation",
    "MultiValueAnswer",
    "SetIdentifier",
)


@dataclass
class ConversionResult:
    """Structured output of a conversion run."""

    zones: list[dict[str, Any]] = field(default_factory=list)
    alias_records: list[dict[str, Any]] = field(default_factory=list)
    review_records: list[dict[str, Any]] = field(default_factory=list)

    def zones_document(self) -> dict[str, Any]:
        """Return the payload written to ``zones.json``."""
        return {"schema_version": SCHEMA_VERSION, "zones": self.zones}

    def review_document(self) -> dict[str, Any]:
        """Return the payload written to the manual-review report."""
        return {
            "schema_version": SCHEMA_VERSION,
            "alias_records": self.alias_records,
            "review_records": self.review_records,
        }


def strip_trailing_dot(value: str) -> str:
    """Remove a single trailing dot from an FQDN, if present."""
    return value[:-1] if value.endswith(".") else value


def unquote_txt(value: str) -> str:
    """Collapse a Route53 TXT value into a single unquoted string.

    Route53 stores TXT values as one or more double-quoted strings that a
    resolver concatenates (long TXT records are split into <=255 byte chunks).
    Cloudflare expects the concatenated, unquoted content.
    """
    result: list[str] = []
    i = 0
    n = len(value)
    in_quotes = False
    while i < n:
        char = value[i]
        if char == "\\" and i + 1 < n:
            # Preserve the escaped character verbatim (e.g. \" or \\).
            result.append(value[i + 1])
            i += 2
            continue
        if char == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if char == " " and not in_quotes:
            # Whitespace between quoted chunks is a separator, not content.
            i += 1
            continue
        result.append(char)
        i += 1
    return "".join(result)


def record_name_for_zone(record_name: str, zone_name: str) -> str:
    """Return a Cloudflare-relative record name.

    The zone apex is represented as ``@``; sub-records keep the label relative
    to the zone; anything outside the zone is returned unchanged (FQDN).
    """
    record_name = strip_trailing_dot(record_name).lower()
    zone_name = strip_trailing_dot(zone_name).lower()
    if record_name == zone_name:
        return "@"
    suffix = f".{zone_name}"
    if record_name.endswith(suffix):
        return record_name[: -len(suffix)]
    return record_name


def _is_apex(name: str) -> bool:
    return name == "@"


def parse_mx(value: str) -> tuple[int | None, str]:
    """Split a Route53 MX value ``"10 mail.example.com."`` -> (10, host)."""
    parts = value.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return None, strip_trailing_dot(value)
    return int(parts[0]), strip_trailing_dot(" ".join(parts[1:]))


def parse_srv(value: str) -> dict[str, Any]:
    """Parse a Route53 SRV value ``"1 10 5269 server.example.com."``."""
    parts = value.split()
    if len(parts) != 4 or not all(p.isdigit() for p in parts[:3]):
        return {"raw": value}
    return {
        "priority": int(parts[0]),
        "weight": int(parts[1]),
        "port": int(parts[2]),
        "target": strip_trailing_dot(parts[3]),
    }


def parse_caa(value: str) -> dict[str, Any]:
    """Parse a Route53 CAA value ``'0 issue "letsencrypt.org"'``."""
    parts = value.split(None, 2)
    if len(parts) != 3 or not parts[0].isdigit():
        return {"raw": value}
    return {
        "flags": int(parts[0]),
        "tag": parts[1],
        "value": unquote_txt(parts[2]),
    }


def _routing_policy_reasons(record_set: dict[str, Any]) -> list[str]:
    return [key for key in ROUTING_POLICY_KEYS if key in record_set]


def convert_record_set(
    zone_name: str, record_set: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert a single Route53 record set.

    Returns ``(direct_records, alias_records, review_records)``.
    """
    record_type = record_set.get("Type", "")
    name = record_name_for_zone(record_set.get("Name", ""), zone_name)
    ttl = int(record_set.get("TTL", 300))

    # SOA and apex NS are managed by Cloudflare automatically.
    if record_type == "SOA" or (record_type == "NS" and _is_apex(name)):
        return (
            [],
            [],
            [
                {
                    "zone": zone_name,
                    "name": name,
                    "type": record_type,
                    "reason": "skipped_managed",
                    "detail": "Cloudflare manages SOA and zone-apex NS records automatically.",
                }
            ],
        )

    # Routing policies have no Cloudflare equivalent.
    routing = _routing_policy_reasons(record_set)
    if routing:
        return (
            [],
            [],
            [
                {
                    "zone": zone_name,
                    "name": name,
                    "type": record_type,
                    "reason": "routing_policy",
                    "detail": (
                        "Route53 routing policy attributes require manual mapping: "
                        f"{', '.join(routing)}."
                    ),
                    "set_identifier": record_set.get("SetIdentifier"),
                }
            ],
        )

    # Route53 alias records do not map 1:1 to Cloudflare.
    if "AliasTarget" in record_set:
        return (
            [],
            [
                {
                    "zone": zone_name,
                    "name": name,
                    "type": record_type,
                    "target": strip_trailing_dot(record_set["AliasTarget"]["DNSName"]),
                    "detail": (
                        "Route53 alias target requires manual mapping to a "
                        "Cloudflare CNAME or origin."
                    ),
                }
            ],
            [],
        )

    resource_records = record_set.get("ResourceRecords", [])
    if not resource_records:
        # A supported type with no values is malformed input, not silently ok.
        return (
            [],
            [],
            [
                {
                    "zone": zone_name,
                    "name": name,
                    "type": record_type,
                    "reason": "empty_record_set",
                    "detail": "Record set contains no ResourceRecords and no AliasTarget.",
                }
            ],
        )

    if record_type == "MX":
        # MX needs a numeric priority; malformed values are routed to review
        # rather than emitted as an invalid Cloudflare record.
        return _convert_mx(zone_name, name, ttl, resource_records)

    if record_type in DIRECT_TYPES:
        return _convert_direct(name, record_type, ttl, resource_records), [], []

    if record_type in REVIEW_TYPES:
        return [], [], _convert_review_type(zone_name, name, record_type, ttl, resource_records)

    # Any other type is unsupported but reported, never dropped.
    return (
        [],
        [],
        [
            {
                "zone": zone_name,
                "name": name,
                "type": record_type,
                "reason": "unsupported_type",
                "detail": f"Record type {record_type} is not supported by this migration tool.",
                "values": [rr.get("Value") for rr in resource_records],
            }
        ],
    )


def _convert_direct(
    name: str, record_type: str, ttl: int, resource_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Expand a multi-value record set into one Cloudflare record per value."""
    records: list[dict[str, Any]] = []
    for rr in resource_records:
        value = rr["Value"]
        entry: dict[str, Any] = {"name": name, "type": record_type, "ttl": ttl}
        if record_type == "TXT":
            entry["content"] = unquote_txt(value)
        else:
            entry["content"] = strip_trailing_dot(value)
        entry["proxied"] = False
        records.append(entry)
    return records


def _convert_mx(
    zone_name: str, name: str, ttl: int, resource_records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert MX values, routing any without a numeric priority to review."""
    direct: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for rr in resource_records:
        priority, host = parse_mx(rr["Value"])
        if priority is None:
            review.append(
                {
                    "zone": zone_name,
                    "name": name,
                    "type": "MX",
                    "reason": "invalid_mx",
                    "detail": (
                        "MX value is missing a numeric priority; expected "
                        f"'<priority> <host>' but got {rr['Value']!r}."
                    ),
                }
            )
        else:
            direct.append(
                {
                    "name": name,
                    "type": "MX",
                    "ttl": ttl,
                    "content": host,
                    "priority": priority,
                    "proxied": False,
                }
            )
    return direct, [], review


def _convert_review_type(
    zone_name: str,
    name: str,
    record_type: str,
    ttl: int,
    resource_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for rr in resource_records:
        value = rr["Value"]
        components = parse_srv(value) if record_type == "SRV" else parse_caa(value)
        parsed.append(
            {
                "zone": zone_name,
                "name": name,
                "type": record_type,
                "ttl": ttl,
                "reason": "structured_data_required",
                "detail": (
                    f"{record_type} records require a structured Cloudflare 'data' block; "
                    "review before creating."
                ),
                "components": components,
            }
        )
    return parsed


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda r: (
            r.get("name", ""),
            r.get("type", ""),
            str(r.get("content", "")),
            r.get("priority") if r.get("priority") is not None else -1,
        ),
    )


def convert_hosted_zones(
    hosted_zones: list[dict[str, Any]],
    record_sets_by_zone_id: dict[str, list[dict[str, Any]]],
    *,
    allow_private_zones: bool = False,
    in_scope_zones: set[str] | None = None,
) -> ConversionResult:
    """Convert every hosted zone into the deterministic migration document.

    :param hosted_zones: the ``HostedZones`` list from ``list-hosted-zones``.
    :param record_sets_by_zone_id: maps a short hosted-zone id to its
        ``ResourceRecordSets`` list.
    :param allow_private_zones: private hosted zones must not be migrated into a
        public Cloudflare zone; by default they are routed to manual review.
    :param in_scope_zones: an optional allowlist of in-scope domain names. When
        provided, any hosted zone whose name is not in the allowlist is routed
        to manual review (reason ``out_of_scope_zone``) instead of being
        migrated — the converter otherwise has no notion of scope and would
        migrate every public zone in the export. Names are compared
        case-insensitively and ignoring a trailing dot. ``None`` (the default)
        disables the filter and preserves the previous behaviour.
    """
    result = ConversionResult()
    allowlist = (
        {strip_trailing_dot(name).lower() for name in in_scope_zones}
        if in_scope_zones is not None
        else None
    )

    for zone in sorted(hosted_zones, key=lambda z: strip_trailing_dot(z.get("Name", ""))):
        zone_id = zone["Id"].split("/")[-1]
        zone_name = strip_trailing_dot(zone["Name"])
        is_private = bool(zone.get("Config", {}).get("PrivateZone", False))

        if allowlist is not None and zone_name.lower() not in allowlist:
            result.review_records.append(
                {
                    "zone": zone_name,
                    "name": "@",
                    "type": "ZONE",
                    "reason": "out_of_scope_zone",
                    "detail": (
                        "Hosted zone is not in the in-scope allowlist; not "
                        "migrated. Add it to the allowlist to include it."
                    ),
                }
            )
            continue

        if is_private and not allow_private_zones:
            result.review_records.append(
                {
                    "zone": zone_name,
                    "name": "@",
                    "type": "ZONE",
                    "reason": "private_hosted_zone",
                    "detail": (
                        "Private Route53 hosted zone must not be migrated into a "
                        "public Cloudflare zone."
                    ),
                }
            )
            continue

        record_sets = record_sets_by_zone_id.get(zone_id, [])
        records: list[dict[str, Any]] = []
        for record_set in record_sets:
            direct, aliases, review = convert_record_set(zone_name, record_set)
            records.extend(direct)
            for alias in aliases:
                result.alias_records.append(alias)
            for item in review:
                result.review_records.append(item)

        result.zones.append({"name": zone_name, "records": _sort_records(records)})

    result.alias_records = _sort_records(result.alias_records)
    result.review_records = _sort_records(result.review_records)
    return result
