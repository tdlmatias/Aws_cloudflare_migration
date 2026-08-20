"""Unit tests for the pure conversion logic."""

from __future__ import annotations

import pytest

from migration.converter import (
    SCHEMA_VERSION,
    convert_hosted_zones,
    convert_record_set,
    parse_caa,
    parse_mx,
    parse_srv,
    record_name_for_zone,
    strip_trailing_dot,
    unquote_txt,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("example.com.", "example.com"), ("example.com", "example.com"), (".", "")],
)
def test_strip_trailing_dot(value: str, expected: str) -> None:
    assert strip_trailing_dot(value) == expected


@pytest.mark.parametrize(
    ("record", "zone", "expected"),
    [
        ("example.com.", "example.com.", "@"),
        ("www.example.com.", "example.com.", "www"),
        ("*.example.com.", "example.com.", "*"),
        ("a.b.example.com.", "example.com.", "a.b"),
        ("EXAMPLE.COM.", "example.com.", "@"),
        ("other.net.", "example.com.", "other.net"),
    ],
)
def test_record_name_for_zone(record: str, zone: str, expected: str) -> None:
    assert record_name_for_zone(record, zone) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('"simple"', "simple"),
        ('"v=spf1 ~all"', "v=spf1 ~all"),
        ('"part-one-" "part-two"', "part-one-part-two"),
        ('"has a \\"quote\\" inside"', 'has a "quote" inside'),
        ('"a" "b" "c"', "abc"),
        # An escaped backslash collapses to a single backslash.
        ('"foo\\\\bar"', "foo\\bar"),
        # Whitespace outside the quoted chunks is a separator, not content.
        ('  "leading and trailing"  ', "leading and trailing"),
    ],
)
def test_unquote_txt(value: str, expected: str) -> None:
    assert unquote_txt(value) == expected


def test_parse_mx() -> None:
    assert parse_mx("10 mail.example.com.") == (10, "mail.example.com")
    assert parse_mx("mail.example.com.") == (None, "mail.example.com")


def test_parse_srv() -> None:
    assert parse_srv("1 10 5060 sip.example.com.") == {
        "priority": 1,
        "weight": 10,
        "port": 5060,
        "target": "sip.example.com",
    }
    assert parse_srv("garbage") == {"raw": "garbage"}


def test_parse_caa() -> None:
    assert parse_caa('0 issue "letsencrypt.org"') == {
        "flags": 0,
        "tag": "issue",
        "value": "letsencrypt.org",
    }


def _rs(name: str, rtype: str, values: list[str], **extra: object) -> dict:
    rs = {"Name": name, "Type": rtype, "TTL": 300}
    if values:
        rs["ResourceRecords"] = [{"Value": v} for v in values]
    rs.update(extra)
    return rs


def test_multi_value_a_expands() -> None:
    direct, _, _ = convert_record_set(
        "example.com", _rs("example.com.", "A", ["1.1.1.1", "2.2.2.2"])
    )
    assert [r["content"] for r in direct] == ["1.1.1.1", "2.2.2.2"]
    assert all(r["name"] == "@" for r in direct)


def test_mx_sets_priority_and_host() -> None:
    direct, _, _ = convert_record_set(
        "example.com", _rs("example.com.", "MX", ["10 mail.example.com."])
    )
    assert direct[0] == {
        "name": "@",
        "type": "MX",
        "ttl": 300,
        "content": "mail.example.com",
        "priority": 10,
        "proxied": False,
    }


def test_invalid_mx_routed_to_review() -> None:
    direct, _, review = convert_record_set(
        "example.com", _rs("example.com.", "MX", ["mail.example.com."])
    )
    assert direct == []
    assert review[0]["reason"] == "invalid_mx"


def test_soa_is_skipped_managed() -> None:
    direct, alias, review = convert_record_set("example.com", _rs("example.com.", "SOA", ["x"]))
    assert direct == [] and alias == []
    assert review[0]["reason"] == "skipped_managed"


def test_apex_ns_is_skipped_but_delegation_kept() -> None:
    _, _, review = convert_record_set("example.com", _rs("example.com.", "NS", ["ns.aws."]))
    assert review[0]["reason"] == "skipped_managed"

    direct, _, _ = convert_record_set("example.com", _rs("sub.example.com.", "NS", ["ns.other."]))
    assert direct[0]["type"] == "NS"
    assert direct[0]["name"] == "sub"


def test_alias_routed_to_alias_records() -> None:
    rs = {
        "Name": "cdn.example.com.",
        "Type": "A",
        "AliasTarget": {"DNSName": "d1.cloudfront.net.", "EvaluateTargetHealth": False},
    }
    direct, alias, _ = convert_record_set("example.com", rs)
    assert direct == []
    assert alias[0]["target"] == "d1.cloudfront.net"


def test_routing_policy_routed_to_review() -> None:
    rs = _rs("api.example.com.", "A", ["198.51.100.10"], SetIdentifier="us", Weight=100)
    direct, _, review = convert_record_set("example.com", rs)
    assert direct == []
    assert review[0]["reason"] == "routing_policy"


def test_unsupported_type_reported_not_dropped() -> None:
    _, _, review = convert_record_set(
        "example.com", _rs("ptr.example.com.", "PTR", ["h.example.com."])
    )
    assert review[0]["reason"] == "unsupported_type"


def test_caa_srv_routed_to_review_with_components() -> None:
    _, _, review = convert_record_set(
        "example.com", _rs("example.com.", "CAA", ['0 issue "le.org"'])
    )
    assert review[0]["reason"] == "structured_data_required"
    assert review[0]["components"]["tag"] == "issue"


def test_empty_supported_record_set_reported() -> None:
    _, _, review = convert_record_set(
        "example.com", {"Name": "example.com.", "Type": "A", "TTL": 300}
    )
    assert review[0]["reason"] == "empty_record_set"


def test_private_zone_routed_to_review(fixture_dir) -> None:
    from migration.io import read_json

    hosted = read_json(fixture_dir / "hosted-zones.json")["HostedZones"]
    records = {
        "Z1PUBLIC0000000000": read_json(fixture_dir / "records-Z1PUBLIC0000000000.json")[
            "ResourceRecordSets"
        ],
        "Z2PRIVATE000000000": read_json(fixture_dir / "records-Z2PRIVATE000000000.json")[
            "ResourceRecordSets"
        ],
    }
    result = convert_hosted_zones(hosted, records)
    zone_names = {z["name"] for z in result.zones}
    assert "internal.example" not in zone_names
    assert any(r["reason"] == "private_hosted_zone" for r in result.review_records)


def test_private_zone_included_when_allowed(fixture_dir) -> None:
    from migration.io import read_json

    hosted = read_json(fixture_dir / "hosted-zones.json")["HostedZones"]
    records = {
        "Z1PUBLIC0000000000": read_json(fixture_dir / "records-Z1PUBLIC0000000000.json")[
            "ResourceRecordSets"
        ],
        "Z2PRIVATE000000000": read_json(fixture_dir / "records-Z2PRIVATE000000000.json")[
            "ResourceRecordSets"
        ],
    }
    result = convert_hosted_zones(hosted, records, allow_private_zones=True)
    zone_names = {z["name"] for z in result.zones}
    assert "internal.example" in zone_names
    assert not any(r["reason"] == "private_hosted_zone" for r in result.review_records)


def _public_zone(zone_id: str, name: str) -> dict:
    return {"Id": f"/hostedzone/{zone_id}", "Name": name, "Config": {"PrivateZone": False}}


def test_out_of_scope_public_zone_routed_to_review() -> None:
    hosted = [
        _public_zone("Z1IN0000000000000", "example.com."),
        _public_zone("Z2OUT000000000000", "extra.com."),
    ]
    result = convert_hosted_zones(hosted, {}, in_scope_zones={"example.com"})
    zone_names = {z["name"] for z in result.zones}
    assert zone_names == {"example.com"}
    assert "extra.com" not in zone_names
    out = [r for r in result.review_records if r["reason"] == "out_of_scope_zone"]
    assert [r["zone"] for r in out] == ["extra.com"]


def test_allowlist_none_migrates_every_public_zone() -> None:
    hosted = [
        _public_zone("Z1IN0000000000000", "example.com."),
        _public_zone("Z2OUT000000000000", "extra.com."),
    ]
    result = convert_hosted_zones(hosted, {}, in_scope_zones=None)
    assert {z["name"] for z in result.zones} == {"example.com", "extra.com"}
    assert not any(r["reason"] == "out_of_scope_zone" for r in result.review_records)


def test_allowlist_matches_case_insensitively_and_ignores_trailing_dot() -> None:
    hosted = [_public_zone("Z1IN0000000000000", "Example.COM.")]
    result = convert_hosted_zones(hosted, {}, in_scope_zones={"example.com."})
    assert {z["name"] for z in result.zones} == {"Example.COM"}
    assert not any(r["reason"] == "out_of_scope_zone" for r in result.review_records)


def test_in_scope_private_zone_still_routed_to_private_review() -> None:
    hosted = [
        {
            "Id": "/hostedzone/Z9PRIVATE00000000",
            "Name": "internal.example.",
            "Config": {"PrivateZone": True},
        }
    ]
    # Even though the zone is in the allowlist, a private zone must not be
    # migrated into a public Cloudflare zone.
    result = convert_hosted_zones(hosted, {}, in_scope_zones={"internal.example"})
    assert result.zones == []
    reasons = {r["reason"] for r in result.review_records}
    assert reasons == {"private_hosted_zone"}


def test_conversion_is_deterministic(fixture_dir) -> None:
    from migration.io import read_json

    hosted = read_json(fixture_dir / "hosted-zones.json")["HostedZones"]
    records = {
        "Z1PUBLIC0000000000": read_json(fixture_dir / "records-Z1PUBLIC0000000000.json")[
            "ResourceRecordSets"
        ],
        "Z2PRIVATE000000000": read_json(fixture_dir / "records-Z2PRIVATE000000000.json")[
            "ResourceRecordSets"
        ],
    }
    first = convert_hosted_zones(hosted, records).zones_document()
    second = convert_hosted_zones(hosted, records).zones_document()
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    # Direct records for example.com: A/AAAA/CNAME/MX/TXT plus the NS delegation.
    example = next(z for z in first["zones"] if z["name"] == "example.com")
    types = sorted({r["type"] for r in example["records"]})
    assert types == ["A", "AAAA", "CNAME", "MX", "NS", "TXT"]
