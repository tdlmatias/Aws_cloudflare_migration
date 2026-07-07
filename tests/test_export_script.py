"""Integration test for scripts/export_route53.sh using a stubbed AWS CLI.

The real AWS API is never contacted: a fake `aws` executable on PATH returns the
committed fixtures. This exercises argument forwarding, dependency checks, the
temp-dir/atomic-publish flow, and the full export -> convert pipeline.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "export_route53.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="requires bash and jq",
)

FAKE_AWS = """#!/usr/bin/env bash
# Minimal stand-in for the AWS CLI used by export_route53.sh.
set -euo pipefail
if [[ "$1" == "route53" && "$2" == "list-hosted-zones" ]]; then
  cat "$FIXTURE_DIR/hosted-zones.json"
  exit 0
fi
if [[ "$1" == "route53" && "$2" == "list-resource-record-sets" ]]; then
  # Args: --hosted-zone-id <id> --output json
  zid="$4"
  cat "$FIXTURE_DIR/records-${zid}.json"
  exit 0
fi
echo "unexpected aws call: $*" >&2
exit 2
"""


def test_export_script_runs_with_stubbed_aws(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS)
    fake.chmod(0o755)

    out_dir = tmp_path / "out"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FIXTURE_DIR"] = str(REPO_ROOT / "tests" / "fixtures")

    result = subprocess.run(
        ["bash", str(SCRIPT), str(out_dir)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    zones = json.loads((out_dir / "zones.json").read_text())
    assert any(z["name"] == "example.com" for z in zones["zones"])
    assert (out_dir / "manual-review.json").exists()


def test_export_script_fails_without_aws(tmp_path) -> None:
    # Empty PATH bin dir: no aws -> dependency check must fail cleanly.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "jq", "python3", "mktemp", "date", "mkdir", "mv", "rm", "dirname"):
        src = shutil.which(tool)
        if src:
            (bin_dir / tool).symlink_to(src)

    env = dict(os.environ)
    env["PATH"] = str(bin_dir)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path / "out")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "aws" in result.stderr
