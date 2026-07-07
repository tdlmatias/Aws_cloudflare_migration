# Engineering Audit Report — Route53 → Cloudflare Migration

Date: 2026-07-07
Scope: full repository (Terraform, Python, shell, CI/CD, data, documentation).
Method: static inspection, provider/version cross-checks, and executed local
validation (ruff, mypy, pytest+coverage, shellcheck, terraform fmt, checkov,
yamllint). `terraform validate`/`terraform test` could not be executed in the
audit environment because the Terraform provider registry
(`registry.terraform.io`) is blocked by egress policy; those checks are wired
into CI and documented for local execution.

Severity legend: **Critical** (data loss / credential exposure / uncontrolled
production change), **High**, **Medium**, **Low**, **Informational**.

## Summary of findings

| ID | Severity | Category | Finding | Status |
| -- | -------- | -------- | ------- | ------ |
| TF-001 | Critical | Python/Terraform | Converter emitted `value`; Terraform reads `content` — export→apply pipeline produced records Terraform could not consume | Fixed |
| SEC-001 | Critical | Security | `terraform/terraform.tfvars` committed with credential-shaped placeholders and undeclared `aws_access_key`/`aws_secret_key` vars | Fixed |
| CI-001 | Critical | CI/CD | `terraform apply -auto-approve` ran automatically on every push to `main`, no approval, no environment protection | Fixed |
| CI-002 | High | CI/CD | Production apply used long-lived AWS access keys instead of OIDC | Fixed |
| DNS-001 | High | DNS | Unsupported record types silently discarded by converter (`return [], None`) | Fixed |
| DNS-002 | High | DNS | No guard against applying an empty/incomplete export → mass zone/record deletion | Fixed |
| CI-003 | High | CI/CD | Backup workflow file (`terraform-apply_yml.backup`) with `secrets` used in job-level `if` (never evaluates) stored in `.github/workflows` | Fixed |
| ARC-001 | High | Architecture | Two divergent implementations (root vs `route53-to-cloudflare-migration/`); nested one orphaned and its workflow `cd terraform` targeted the root module | Fixed |
| TF-002 | Medium | Terraform | Dead AWS provider + `aws_region`/`cloudflare_plan` variables (config creates only Cloudflare resources) | Fixed |
| TF-003 | Medium | Terraform | No variable validation, no sensitive handling guidance, no remote-backend example | Fixed |
| DNS-003 | Medium | DNS | Route53 alias/routing policies (Weight/Failover/Geo) not detected; risk of silent partial migration | Fixed |
| DNS-004 | Medium | DNS | Private hosted zones would be migrated into public Cloudflare zones | Fixed |
| TXT-001 | Medium | Python | TXT handling only stripped one pair of quotes; split/long/escaped TXT mishandled | Fixed |
| CI-004 | Medium | CI/CD | Overlapping workflows (`ci.yml`, `terraform-validate.yml`, `staging-deploy.yml`, apply `tests` job) duplicating fmt/validate | Fixed |
| TEST-001 | High | Testing | No automated tests, schema, or coverage anywhere in the repo | Fixed |
| SH-001 | Medium | Shell | `export_route53.sh` had no dependency checks, no cwd-independence, no atomic publish, wrote partial output on failure | Fixed |
| DOC-001 | Medium | Documentation | README/nested README claimed "fully automated / zero-downtime", wrong file names, Terraform 1.14.0 vs `~>1.9`, MIT vs GPL-3.0 | Fixed |
| SH-002 | Low | Shell | Committed `logs/migration.log` and generated data under version control | Fixed |
| TF-004 | Low | Terraform | Nested `.gitignore` ignored `*.hcl`/`*.lock.hcl` (would exclude the provider lock file that should be committed) | Fixed (dir removed) |
| INFO-001 | Informational | Docs | No SECURITY.md, CONTRIBUTING.md, runbook, or architecture docs | Fixed |

## Detailed findings

### TF-001 — Converter/Terraform field mismatch (Critical, Fixed)
* Location: former `scripts/route53_to_cloudflare.py:61-70` (emitted `entry["value"]`) vs `terraform/main.tf` (`each.value.content`, and the `for_each` key referenced `record.content`).
* Evidence: the committed `terraform/data/zones.json` was hand-authored with `content`, masking the mismatch. A real export would produce `value` keys, so every `cloudflare_dns_record` would fail on a missing `content` argument.
* Impact: the documented export→apply pipeline was broken end to end.
* Remediation: the new `migration.converter` emits Cloudflare-native `content`, and a JSON Schema (`schemas/zones.schema.json`) plus `terraform test` assertions lock the contract.
* Validation: `tests/test_converter.py::test_mx_sets_priority_and_host`, `tests/test_cli.py`, `terraform/tests/plan.tftest.hcl`.

### SEC-001 — Committed credential-shaped tfvars (Critical, Fixed)
* Location: `terraform/terraform.tfvars`, `route53-to-cloudflare-migration/terraform/terraform.tfvars`.
* Evidence: tracked despite `*.tfvars` in `.gitignore` (added before the ignore rule / force-added); contained `aws_access_key`/`aws_secret_key` that were not declared variables, so `terraform apply` using the file would also error.
* Impact: normalises committing secrets; misleading undeclared variables.
* Remediation: `git rm --cached` both files, added `terraform/terraform.tfvars.example` with obvious placeholders and env-var guidance. No real secrets were found in the working tree or local git history.
* Validation: `git ls-files | grep tfvars` returns only the `.example`; gitleaks wired into `security.yml`.

### CI-001 / CI-002 — Uncontrolled auto-apply (Critical/High, Fixed)
* Location: `.github/workflows/terraform-apply.yml` (`on: push: branches: [main]`, `terraform apply -auto-approve`).
* Impact: any merge to `main` mutated production DNS with no human gate; long-lived AWS keys in repo secrets.
* Remediation: apply is now `workflow_dispatch` only, requires a typed `confirm=apply` input and a protected `production` GitHub Environment (required reviewers), uses a concurrency lock, and applies a plan produced in the same run. AWS keys are removed from apply entirely (Terraform only touches Cloudflare); an OIDC read-only role is used by the separate export workflow.

### DNS-001 / DNS-003 / DNS-004 — Safe handling of un-migratable records (High/Medium, Fixed)
* The old converter returned `[], None` for any unsupported type — a silent drop. Alias records were partially handled; routing policies and private zones were not detected.
* Remediation: nothing is dropped silently. `convert_record_set` routes aliases to `alias_records` and SOA/apex-NS, routing policies, structured-data types (CAA/SRV), unsupported types, empty sets, and private zones to `review_records` with an explicit `reason`. Output is schema-validated (`schemas/review.schema.json`).

### DNS-002 — Empty-export apply guard (High, Fixed)
* A `terraform_data.guard` precondition now fails the plan/apply when `zones.json` contains zero zones, preventing a mass-delete from an incomplete export.

### SH-001 — Export script robustness (Medium, Fixed)
* `scripts/export_route53.sh` now checks for `aws`/`jq`/`python3`, resolves the repo root so it works from any cwd, writes to a `mktemp` dir with a cleanup trap, and only publishes `zones.json`/`manual-review.json` after a fully successful run.

### ARC-001 — Duplicate implementations (High, Fixed)
* The nested `route53-to-cloudflare-migration/` tree was orphaned (its `migrate_dns.yml` ran the nested exporter but then `cd terraform` into the **root** module) and diverged in data format (`domains.json` map vs `zones.json`). The root implementation is authoritative (referenced by all root workflows). The nested tree was removed and its useful ideas (boto3 export, pagination) folded into documentation and the optional `export` extra.

Remaining items and environment-limited validations are tracked in the "Deferred
items" section of the final report and in `docs/MIGRATION_RUNBOOK.md`.
