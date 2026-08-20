"""End-to-end CLI tests (no AWS access required)."""

from __future__ import annotations

import json
from pathlib import Path

from migration.cli import main


def _convert(fixture_dir: Path, out_dir: Path) -> int:
    return main(
        [
            "convert",
            "--zones",
            str(fixture_dir / "hosted-zones.json"),
            "--records-dir",
            str(fixture_dir),
            "--output",
            str(out_dir / "zones.json"),
            "--review-output",
            str(out_dir / "manual-review.json"),
        ]
    )


def test_convert_writes_valid_documents(fixture_dir, tmp_path, capsys) -> None:
    assert _convert(fixture_dir, tmp_path) == 0
    zones = json.loads((tmp_path / "zones.json").read_text())
    review = json.loads((tmp_path / "manual-review.json").read_text())
    assert zones["schema_version"] == "1.1.0"
    assert any(z["name"] == "example.com" for z in zones["zones"])
    assert review["review_records"]  # unsupported / routing / structured items present
    # The user-facing manual-review note is written to stderr.
    assert "item(s) need manual review" in capsys.readouterr().err


def test_convert_is_byte_for_byte_deterministic(fixture_dir, tmp_path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _convert(fixture_dir, a)
    _convert(fixture_dir, b)
    assert (a / "zones.json").read_bytes() == (b / "zones.json").read_bytes()
    assert (a / "manual-review.json").read_bytes() == (b / "manual-review.json").read_bytes()


def test_validate_subcommand(fixture_dir, tmp_path) -> None:
    _convert(fixture_dir, tmp_path)
    assert main(["validate", str(tmp_path / "zones.json"), "--schema", "zones"]) == 0


def test_missing_records_file_errors(tmp_path, capsys) -> None:
    (tmp_path / "hosted-zones.json").write_text(
        json.dumps({"HostedZones": [{"Id": "/hostedzone/ZMISSING", "Name": "x.com."}]})
    )
    rc = main(
        [
            "convert",
            "--zones",
            str(tmp_path / "hosted-zones.json"),
            "--records-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "zones.json"),
            "--review-output",
            str(tmp_path / "review.json"),
        ]
    )
    assert rc == 1
    assert "Missing record export" in capsys.readouterr().err


def test_convert_in_scope_zone_routes_out_of_scope_to_review(tmp_path, capsys) -> None:
    (tmp_path / "hosted-zones.json").write_text(
        json.dumps(
            {
                "HostedZones": [
                    {"Id": "/hostedzone/ZIN", "Name": "example.com.", "Config": {}},
                    {"Id": "/hostedzone/ZOUT", "Name": "extra.com.", "Config": {}},
                ]
            }
        )
    )
    for zid in ("ZIN", "ZOUT"):
        (tmp_path / f"records-{zid}.json").write_text(json.dumps({"ResourceRecordSets": []}))

    rc = main(
        [
            "convert",
            "--zones",
            str(tmp_path / "hosted-zones.json"),
            "--records-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "zones.json"),
            "--review-output",
            str(tmp_path / "manual-review.json"),
            "--in-scope-zone",
            "example.com",
        ]
    )
    assert rc == 0
    zones = json.loads((tmp_path / "zones.json").read_text())
    review = json.loads((tmp_path / "manual-review.json").read_text())
    assert {z["name"] for z in zones["zones"]} == {"example.com"}
    out_of_scope = [r for r in review["review_records"] if r["reason"] == "out_of_scope_zone"]
    assert [r["zone"] for r in out_of_scope] == ["extra.com"]


def test_convert_in_scope_file_parsed_with_comments(tmp_path) -> None:
    (tmp_path / "hosted-zones.json").write_text(
        json.dumps(
            {
                "HostedZones": [
                    {"Id": "/hostedzone/ZIN", "Name": "example.com.", "Config": {}},
                    {"Id": "/hostedzone/ZOUT", "Name": "extra.com.", "Config": {}},
                ]
            }
        )
    )
    for zid in ("ZIN", "ZOUT"):
        (tmp_path / f"records-{zid}.json").write_text(json.dumps({"ResourceRecordSets": []}))
    (tmp_path / "in-scope.txt").write_text(
        "# in-scope domains\nexample.com\n\n  # trailing comment line\n"
    )

    rc = main(
        [
            "convert",
            "--zones",
            str(tmp_path / "hosted-zones.json"),
            "--records-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "zones.json"),
            "--review-output",
            str(tmp_path / "manual-review.json"),
            "--in-scope-file",
            str(tmp_path / "in-scope.txt"),
        ]
    )
    assert rc == 0
    zones = json.loads((tmp_path / "zones.json").read_text())
    review = json.loads((tmp_path / "manual-review.json").read_text())
    assert {z["name"] for z in zones["zones"]} == {"example.com"}
    assert [r["zone"] for r in review["review_records"] if r["reason"] == "out_of_scope_zone"] == [
        "extra.com"
    ]


def test_validate_rejects_bad_document(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"zones": []}))
    assert main(["validate", str(bad), "--schema", "zones"]) == 1
