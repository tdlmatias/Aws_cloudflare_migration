# Migration Runbook

A step-by-step, safety-first procedure for migrating a set of domains from
Route53 to Cloudflare. Do not skip the preflight or verification steps — the
"low/zero downtime" property depends on them.

For a concrete, dated schedule of a single migration week (with go/no-go gates),
see [`CUTOVER_PLAN.md`](CUTOVER_PLAN.md).

## 0. Roles and prerequisites

* AWS CLI authenticated with **read-only** Route53 access
  (`route53:ListHostedZones`, `route53:ListResourceRecordSets`).
* Cloudflare API token with `Zone:Edit` and `DNS:Edit`.
* `python3`, `jq`, and `terraform ~> 1.9` installed (`make install` for Python).
* Access to the domain registrar to change nameservers.
* A configured remote Terraform backend (`terraform/backend.tf` from the example).

## 1. Preflight (T-48h or earlier)

### 1a. Re-point the export at the current AWS account

Do this whenever the hosted zones live in a **different AWS account** than the
last export ran against (e.g. after consolidating domains into a new account).
The tooling has no hardcoded account id — it reaches Route53 only through the
OIDC role named by the `AWS_ROUTE53_READONLY_ROLE_ARN` secret, so rotating to a
new account is an IAM + secret change, not a code change:

1. In the **new** AWS account, ensure a GitHub OIDC identity provider exists
   (`token.actions.githubusercontent.com`, audience `sts.amazonaws.com`).
2. Create a read-only Route53 role with the trust policy and minimal IAM
   permissions in `docs/SECURITY_MODEL.md`. Keep the repo name in the trust
   `sub` **exactly** `tdlmatias/Aws_cloudflare_migration` (capital `A`) — IAM
   `StringLike` is case-sensitive and a lower-cased name silently rejects the
   token.
3. Update the `AWS_ROUTE53_READONLY_ROLE_ARN` secret in the GitHub `export`
   environment to the new role's ARN.
4. Run the **Route53 Export** workflow (`workflow_dispatch`) once as a smoke
   test and confirm the log line `Found N hosted zone(s)` matches the number of
   domains you moved into the account. If it fails at "Configure AWS
   credentials", re-check the trust policy `sub` and account id.

### 1b. Prepare for a fast rollback

1. **Lower TTLs** on the records you will migrate in Route53 (e.g. 300s) so a
   rollback propagates quickly. Wait at least the old TTL before cutover.
2. Confirm which hosted zones are in scope. **Private hosted zones are not
   migrated** to public Cloudflare — the tooling routes them to manual review.
3. Note current authoritative nameservers and record counts per zone.

## 2. Export Route53

```bash
./scripts/export_route53.sh terraform/data
```

Produces `terraform/data/zones.json` (Terraform input) and
`terraform/data/manual-review.json`. The export publishes atomically; a failure
leaves previous output untouched.

## 3. Resolve manual-review items

Open `terraform/data/manual-review.json`. For each entry:

| reason | action |
| ------ | ------ |
| `skipped_managed` | None — Cloudflare manages SOA and apex NS. |
| `routing_policy` | Decide the Cloudflare equivalent (or accept as out of scope). |
| `invalid_mx` | Fix the malformed MX value (needs `<priority> <host>`) at source and re-export, or recreate it manually. Must be resolved before apply. |
| `structured_data_required` (CAA/SRV) | Add manually in Cloudflare or extend Terraform. |
| `unsupported_type` | Recreate manually if still needed. |
| `private_hosted_zone` | Do **not** migrate to public Cloudflare. |
| `out_of_scope_zone` | Zone excluded by the in-scope allowlist (`--in-scope-file`/`--in-scope-zone`). Confirm the exclusion is intended; add it to the allowlist and re-export to include it. |
| alias records | Map to a Cloudflare CNAME/origin. |

## 4. Validate

```bash
make validate          # zones.json vs schema
make test              # Python unit/contract/integration tests
```

## 5. Plan

Open a PR. CI runs lint/type/tests/`terraform validate`/`terraform test`. The
`terraform-plan` workflow publishes a **reviewable plan artifact**. Confirm:

* Zone count matches the number of in-scope domains.
* Record count is sane (compare to the Route53 counts from step 1).
* There are **no unexpected destroy actions**.

## 6. Human review

A second engineer reviews the plan artifact and the resolved manual-review
items. Record the reviewed plan and a migration timestamp in the PR.

## 7. Protected apply

Trigger `terraform-apply` via **workflow_dispatch** with input `confirm=apply`.
The `production` environment requires reviewer approval before the job runs.
Terraform applies the exact plan produced in the run. Capture the
`zone_ids`/`zone_count`/`record_count` outputs.

## 8. DNS verification (before cutover)

Query the **Cloudflare nameservers directly** (shown in the Cloudflare
dashboard for each zone) and compare against Route53:

```bash
# Example: verify apex A and MX resolve identically on the new NS
dig @<cloudflare-ns> example.com A +short
dig @<cloudflare-ns> example.com MX +short
```

Verify MX, SPF (TXT), DKIM (TXT), and DMARC (TXT) explicitly. Do not proceed
until answers match the intended state.

## 9. Registrar nameserver cutover

At the registrar, replace the Route53 nameservers with the Cloudflare
nameservers for each domain. Propagation is bounded by the registrar/TLD TTL.

## 10. Post-cutover monitoring & rollback window

* Monitor resolution and application health.
* **Keep Route53 hosted zones intact and authoritative-capable for the rollback
  window** (e.g. 48h). Do not delete them yet.
* **Rollback:** if problems appear, revert the registrar nameservers to the
  Route53 set. Because Route53 is unchanged and TTLs were lowered, resolution
  returns to the old state quickly.
* Once stable, decommission Route53 zones in a separate, deliberate change.

## Rollback quick reference

1. Registrar → set nameservers back to the recorded Route53 NS.
2. Confirm `dig NS example.com` returns Route53 NS.
3. Confirm application health.
4. Investigate the Cloudflare-side issue before re-attempting cutover.
