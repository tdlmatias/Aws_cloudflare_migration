"""Unit tests for the pure migration-agent analysis helpers.

These need no Anthropic API key, AWS, or network — they exercise the logic the
agent's tools depend on to make safe/unsafe calls.
"""

from __future__ import annotations

from migration.agent import analysis


def test_classify_manual_review_flags_blockers() -> None:
    review = {
        "alias_records": [{"zone": "example.com", "name": "@", "type": "A"}],
        "review_records": [
            {"zone": "example.com", "name": "@", "type": "MX", "reason": "invalid_mx"},
            {"zone": "example.com", "name": "w", "type": "SRV", "reason": "unsupported_type"},
            {"zone": "example.com", "name": "@", "type": "NS", "reason": "skipped_managed"},
        ],
    }
    result = analysis.classify_manual_review(review)
    assert result["alias_count"] == 1
    assert result["review_count"] == 3
    assert result["reason_counts"] == {
        "invalid_mx": 1,
        "skipped_managed": 1,
        "unsupported_type": 1,
    }
    assert len(result["blockers"]) == 1
    assert result["blockers"][0]["reason"] == "invalid_mx"
    # requires_action = 1 alias + invalid_mx + unsupported_type (skipped_managed excluded)
    assert len(result["requires_action"]) == 3
    assert result["ready_for_apply"] is False


def test_classify_manual_review_ready_only_managed_items() -> None:
    review = {
        "alias_records": [],
        "review_records": [
            {"zone": "example.com", "name": "@", "type": "SOA", "reason": "skipped_managed"},
        ],
    }
    result = analysis.classify_manual_review(review)
    assert result["ready_for_apply"] is True
    assert result["blockers"] == []
    assert result["requires_action"] == []


def test_classify_manual_review_not_ready_with_unresolved_alias() -> None:
    # An alias is silently absent from zones.json, so even with no malformed
    # blockers the export is NOT ready to apply — the operator must map it.
    review = {
        "alias_records": [{"zone": "example.com", "name": "@", "type": "A"}],
        "review_records": [],
    }
    result = analysis.classify_manual_review(review)
    assert result["blockers"] == []
    assert result["ready_for_apply"] is False
    assert result["requires_action"][0]["reason"] == "alias_record"


def test_zone_record_counts() -> None:
    zones_doc = {
        "zones": [
            {"name": "example.com", "records": [{"name": "@"}, {"name": "www"}]},
            {"name": "empty.net", "records": []},
        ]
    }
    assert analysis.zone_record_counts(zones_doc) == {"example.com": 2, "empty.net": 0}


def test_diff_record_counts_safe() -> None:
    baseline = {"example.com": 10, "example.org": 4}
    current = {"example.com": 10, "example.org": 5}
    result = analysis.diff_record_counts(baseline, current)
    assert result["safe"] is True
    assert result["missing_zones"] == []
    assert result["new_zones"] == []
    assert result["significant_drops"] == []


def test_diff_record_counts_detects_missing_zone_and_drop() -> None:
    baseline = {"example.com": 10, "example.org": 4, "gone.io": 3}
    current = {"example.com": 3, "example.org": 4}  # gone.io missing, example.com dropped
    result = analysis.diff_record_counts(baseline, current)
    assert result["safe"] is False
    assert result["missing_zones"] == ["gone.io"]
    assert result["significant_drops"] == [{"zone": "example.com", "baseline": 10, "current": 3}]


def test_summarize_terraform_plan_counts_and_flags_destroys() -> None:
    plan = {
        "resource_changes": [
            {"address": 'cloudflare_zone.zones["a"]', "change": {"actions": ["create"]}},
            {"address": 'cloudflare_dns_record.records["x"]', "change": {"actions": ["update"]}},
            {"address": 'cloudflare_dns_record.records["y"]', "change": {"actions": ["delete"]}},
            {
                "address": 'cloudflare_dns_record.records["z"]',
                "change": {"actions": ["delete", "create"]},
            },  # noqa: E501
            {"address": 'cloudflare_dns_record.records["n"]', "change": {"actions": ["no-op"]}},
        ]
    }
    result = analysis.summarize_terraform_plan(plan)
    assert result["counts"]["create"] == 1
    assert result["counts"]["update"] == 1
    assert result["counts"]["delete"] == 1
    assert result["counts"]["replace"] == 1
    assert result["no_destroys"] is False
    addresses = {d["address"] for d in result["destroys"]}
    assert addresses == {
        'cloudflare_dns_record.records["y"]',
        'cloudflare_dns_record.records["z"]',
    }


def test_summarize_terraform_plan_clean_plan() -> None:
    plan = {"resource_changes": [{"address": "a", "change": {"actions": ["create"]}}]}
    result = analysis.summarize_terraform_plan(plan)
    assert result["no_destroys"] is True
    assert result["destroys"] == []


def test_compare_rrset_normalises_order_case_and_dots() -> None:
    result = analysis.compare_rrset(
        ["1.2.3.4", "5.6.7.8"],
        ["5.6.7.8", "1.2.3.4"],
    )
    assert result["match"] is True

    mismatch = analysis.compare_rrset(["mail.example.com."], ["MAIL.EXAMPLE.COM"])
    assert mismatch["match"] is True  # trailing dot + case normalised

    missing = analysis.compare_rrset(["1.2.3.4", "9.9.9.9"], ["1.2.3.4"])
    assert missing["match"] is False
    assert missing["missing"] == ["9.9.9.9"]
    assert missing["unexpected"] == []


def test_compare_rrset_txt_is_case_sensitive_and_unquotes() -> None:
    # A DKIM base64 payload differing only in case must NOT match.
    dkim = analysis.compare_rrset(
        ["v=DKIM1; k=rsa; p=AbCdEf"],
        ['"v=DKIM1; k=rsa; p=abcdef"'],
        "TXT",
    )
    assert dkim["match"] is False

    # dig wraps TXT in quotes and splits long records into chunks; unquoting
    # them should reproduce the stored, concatenated content exactly.
    spf = analysis.compare_rrset(
        ["v=spf1 include:_spf.example.com ~all"],
        ['"v=spf1 include:_spf.example.com ~all"'],
        "TXT",
    )
    assert spf["match"] is True

    split = analysis.compare_rrset(["abcdefghij"], ['"abcde" "fghij"'], "TXT")
    assert split["match"] is True


def test_expected_answers_for_zone_prefixes_mx_priority() -> None:
    zones_doc = {
        "zones": [
            {
                "name": "example.com",
                "records": [
                    {"name": "@", "type": "A", "content": "1.2.3.4"},
                    {"name": "@", "type": "MX", "content": "mail.example.com", "priority": 10},
                    {"name": "www", "type": "CNAME", "content": "example.com"},
                ],
            }
        ]
    }
    answers = analysis.expected_answers_for_zone(zones_doc, "example.com")
    assert answers["@ A"] == ["1.2.3.4"]
    assert answers["@ MX"] == ["10 mail.example.com"]
    assert answers["www CNAME"] == ["example.com"]
    assert analysis.expected_answers_for_zone(zones_doc, "absent.net") == {}


def test_expected_answers_excludes_proxied_records() -> None:
    zones_doc = {
        "zones": [
            {
                "name": "example.com",
                "records": [
                    {"name": "@", "type": "A", "content": "1.2.3.4", "proxied": False},
                    {"name": "app", "type": "A", "content": "10.0.0.9", "proxied": True},
                    {
                        "name": "shop",
                        "type": "CNAME",
                        "content": "origin.example.com",
                        "proxied": True,
                    },
                ],
            }
        ]
    }
    answers = analysis.expected_answers_for_zone(zones_doc, "example.com")
    # Only the unproxied apex A can be origin-verified.
    assert answers == {"@ A": ["1.2.3.4"]}
    assert analysis.proxied_record_keys(zones_doc, "example.com") == ["app A", "shop CNAME"]
