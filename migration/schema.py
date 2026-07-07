"""JSON Schema loading and validation for migration documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


class SchemaValidationError(ValueError):
    """Raised when a migration document does not satisfy its schema."""


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema (e.g. ``"zones"`` or ``"review"``) from ``schemas/``."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_document(document: dict[str, Any], schema_name: str) -> None:
    """Validate ``document`` against the named schema.

    Raises :class:`SchemaValidationError` with an actionable message on failure.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise SchemaValidationError(
            "The 'jsonschema' package is required for validation. "
            "Install it with 'pip install jsonschema'."
        ) from exc

    schema = load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(
            f"  - {'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors
        )
        raise SchemaValidationError(
            f"Document failed '{schema_name}' schema validation:\n{messages}"
        )
