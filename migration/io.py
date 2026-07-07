"""Filesystem helpers: deterministic, atomic JSON reads and writes."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """Read and parse a UTF-8 JSON file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, document: Any) -> None:
    """Write ``document`` as pretty, deterministic JSON atomically.

    The file is written to a temporary sibling and renamed so a crash mid-write
    never leaves a half-written file behind. A trailing newline is added and
    keys are not sorted (the converter already orders content deterministically,
    and dict insertion order is stable in Python 3.7+).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
