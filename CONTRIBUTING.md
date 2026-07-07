# Contributing

Thanks for improving the Route53 → Cloudflare migration tooling.

## Development setup

```bash
make install          # editable install + dev tools (ruff, mypy, pytest, ...)
pre-commit install    # optional: run hooks on every commit
```

## Quality gate

Run the full local gate before opening a PR:

```bash
make ci               # lint + typecheck + tests + schema validation
make terraform-test   # fmt + validate + native terraform tests (needs registry)
make security         # gitleaks + checkov (if installed)
```

Individual targets: `make format`, `make lint`, `make typecheck`, `make test`.

## Guidelines

* **Keep the converter pure and deterministic.** Functions in
  `migration/converter.py` must not do I/O and must produce identical output for
  identical input (byte-for-byte). Add parameterised tests for new record types.
* **Never silently drop a record.** Anything that cannot be migrated
  automatically must go to the manual-review report with an explicit `reason`.
* **Update the schema together with the data shape.** `schemas/*.schema.json`
  are versioned via `SCHEMA_VERSION` in `migration/converter.py`; bump the minor
  version for additive changes and the major version for breaking ones.
* **No secrets, ever.** Do not add real tokens/keys or commit `.tfvars` or
  generated data.
* **Safety first in CI.** Do not add workflows that apply Terraform on push;
  production apply stays manual and environment-protected.

## Tests

* Python: `tests/` (unit, schema contract, CLI, shell integration).
* Terraform: `terraform/tests/*.tftest.hcl` (mock provider, no real resources).
* Coverage target for `migration/` is 85%+.

## Commit / PR

Keep changes focused, describe the "why", and ensure the quality gate passes.
Update `docs/AUDIT_REPORT.md` status if your change resolves a tracked finding.
