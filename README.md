# AWS Route53 → Cloudflare Migration

Infrastructure-as-Code tooling to migrate DNS zones and records from **AWS
Route53** to **Cloudflare**. Route53 is exported to a deterministic,
schema-validated `zones.json`, which Terraform turns into Cloudflare zones and
DNS records. Records that cannot be migrated automatically are written to a
manual-review report — never silently dropped.

## Project status

Ready for **controlled staging**. Production apply is manual and
environment-protected. See `docs/AUDIT_REPORT.md` for the engineering audit and
`docs/ARCHITECTURE.md` for the design. This is not a one-click "zero downtime"
button: low-downtime cutover depends on following `docs/MIGRATION_RUNBOOK.md`
(lower TTLs, verify, keep Route53 as rollback).

## Supported vs unsupported Route53 features

| Automatically migrated | Reported for manual review |
| ---------------------- | -------------------------- |
| A, AAAA, CNAME, TXT (incl. split/long/escaped), MX (with priority), NS delegations | Alias records, weighted/latency/failover/geo routing, health checks |
| Zone-apex normalisation to `@`, multi-value round-robin, wildcards | CAA, SRV (parsed but need Cloudflare `data` blocks) |
| Trailing-dot removal, deterministic ordering | Private hosted zones (never migrated to public Cloudflare) |
| SOA / apex NS dropped (Cloudflare-managed) | Unsupported record types |

## Repository layout

```
migration/            # Python package: converter, schema validation, CLI
schemas/              # Versioned JSON Schema for zones.json and the review report
scripts/              # export_route53.sh (AWS CLI export + convert)
terraform/            # Cloudflare zones + DNS records from data/zones.json
  data/zones.json     # Sample/generated Terraform input
  tests/              # Native terraform tests (mock provider)
tests/                # pytest: unit, schema contract, CLI, shell integration
docs/                 # Audit, architecture, runbook, security model, diagrams
.github/workflows/    # ci, terraform-plan, terraform-apply, security, export
```

## Prerequisites

* AWS CLI authenticated with read-only Route53 access.
* Cloudflare API token (`Zone:Edit`, `DNS:Edit`).
* `python3` (>= 3.10), `jq`, Terraform `~> 1.9`.

## Install

```bash
make install     # editable install with dev tooling
```

## Local validation and tests

```bash
make ci               # ruff + mypy + pytest (+coverage) + schema validation
make lint             # ruff + shellcheck + terraform fmt -check
make terraform-test   # terraform fmt/validate/test (needs provider registry)
make security         # gitleaks + checkov (if installed)
```

## 1. Export Route53

```bash
./scripts/export_route53.sh terraform/data
```

Writes `terraform/data/zones.json` (Terraform input) and
`terraform/data/manual-review.json` (aliases, routing policies, unsupported
records, private zones). Review the report before continuing.

## 2. Dry run / validate

```bash
python -m migration validate terraform/data/zones.json --schema zones
```

## 3. Plan

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars   # or use env vars
export CLOUDFLARE_API_TOKEN="<token>"            # read by the provider, not a TF var
export TF_VAR_cloudflare_account_id="<32-hex-account-id>"

cd terraform
terraform init            # configure a remote backend first (see backend.tf.example)
terraform plan -out=tfplan
```

Review the plan: zone count, record count, and **no unexpected destroys**.

## 4. Controlled apply

Production apply runs through the protected `terraform-apply` GitHub workflow
(`workflow_dispatch`, `confirm=apply`, required-reviewer environment). For a
non-production/staging account you can apply the reviewed plan locally:

```bash
terraform apply tfplan
```

The configuration refuses to apply an empty `zones.json` (guard against
destroying zones from an incomplete export).

## 5. Verify, cut over, roll back

Follow `docs/MIGRATION_RUNBOOK.md`: verify records against the Cloudflare
nameservers directly, switch registrar nameservers, monitor, and keep Route53
authoritative during the rollback window.

## Security

* No long-lived AWS keys — CI export uses GitHub OIDC (read-only Route53).
* Terraform manages Cloudflare only and never receives AWS credentials.
* Secrets via environment/secret store, never committed. `*.tfvars` and
  generated data are git-ignored; gitleaks + checkov run in CI.
* See `SECURITY.md` and `docs/SECURITY_MODEL.md`.

## Troubleshooting

| Symptom | Cause / fix |
| ------- | ----------- |
| `cloudflare_account_id must be a 32-character hexadecimal string` | Use the account id, not a zone id. |
| Plan wants to destroy many records | Stale/incomplete `zones.json`; re-run the export. |
| Apply blocked: "contains no zones" | The guard fired on an empty export; re-export. |
| `terraform init` cannot reach the registry | Network/egress policy blocks `registry.terraform.io`. |
| Records need a `data` block (CAA/SRV) | See the manual-review report; add manually in Cloudflare. |

## Documentation

* [`docs/AUDIT_REPORT.md`](docs/AUDIT_REPORT.md) — findings and remediations
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — design + diagrams
* [`docs/MIGRATION_RUNBOOK.md`](docs/MIGRATION_RUNBOOK.md) — step-by-step migration
* [`docs/CUTOVER_PLAN.md`](docs/CUTOVER_PLAN.md) — dated week-of cutover schedule and go/no-go gates
* [`docs/AGENT.md`](docs/AGENT.md) — optional AI agent that automates the export/verify steps (capability-gated: no apply/cutover)
* [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) — credentials, OIDC, state

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
