"""JSON Schema contract tests for generated documents."""

from __future__ import annotations

import pytest

from migration.converter import SCHEMA_VERSION, convert_hosted_zones
from migration.io import read_json
from migration.schema import SchemaValidationError, validate_document


@pytest.fixture
def result(fixture_dir):
    hosted = read_json(fixture_dir / "hosted-zones.json")["HostedZones"]
    records = {
        "Z1PUBLIC0000000000": read_json(fixture_dir / "records-Z1PUBLIC0000000000.json")[
            "ResourceRecordSets"
        ],
        "Z2PRIVATE000000000": read_json(fixture_dir / "records-Z2PRIVATE000000000.json")[
            "ResourceRecordSets"
        ],
    }
    return convert_hosted_zones(hosted, records)


def test_generated_zones_document_matches_schema(result) -> None:
    validate_document(result.zones_document(), "zones")


def test_generated_review_document_matches_schema(result) -> None:
    validate_document(result.review_document(), "review")


def test_bundled_sample_zones_json_is_valid() -> None:
    from pathlib import Path

    sample = Path(__file__).resolve().parent.parent / "terraform" / "data" / "zones.json"
    validate_document(read_json(sample), "zones")


def test_missing_required_field_fails() -> None:
    bad = {"schema_version": SCHEMA_VERSION, "zones": [{"name": "example.com"}]}
    with pytest.raises(SchemaValidationError):
        validate_document(bad, "zones")


def test_trailing_dot_zone_name_rejected() -> None:
    bad = {"schema_version": SCHEMA_VERSION, "zones": [{"name": "example.com.", "records": []}]}
    with pytest.raises(SchemaValidationError):
        validate_document(bad, "zones")


def test_invalid_record_type_rejected() -> None:
    bad = {
        "schema_version": SCHEMA_VERSION,
        "zones": [
            {
                "name": "example.com",
                "records": [{"name": "@", "type": "PTR", "content": "x", "ttl": 300}],
            }
        ],
    }
    with pytest.raises(SchemaValidationError):
        validate_document(bad, "zones")


def test_mx_without_priority_rejected() -> None:
    bad = {
        "schema_version": SCHEMA_VERSION,
        "zones": [
            {
                "name": "example.com",
                "records": [{"name": "@", "type": "MX", "content": "mail.example.com", "ttl": 300}],
            }
        ],
    }
    with pytest.raises(SchemaValidationError):
        validate_document(bad, "zones")
