# This-Week Cutover Plan — Route53 → Cloudflare

Concrete, dated schedule for migrating the domains (now consolidated in the new
AWS account) from AWS Route53 to Cloudflare. This is the operational overlay on
top of `MIGRATION_RUNBOOK.md`; follow the runbook for the detailed procedure of
each step. Week of **Tue 18 Aug – Mon 24 Aug 2026**.

**Cutover principle:** Route53 stays authoritative and unchanged until the
registrar nameserver switch. Cloudflare is built and verified *before* any
traffic moves, and Route53 is kept intact as a rollback target through the
weekend. Nothing is a one-click button — the low-downtime property comes from
lowering TTLs early, verifying on the new nameservers, and not deleting Route53.

## Prerequisites to have in hand before Day 1

- [ ] Registrar login for every in-scope domain (to change nameservers).
- [ ] Admin on the **new** AWS account (to create the OIDC export role).
- [ ] Cloudflare account id + a scoped API token (`Zone:Edit`, `DNS:Edit`).
- [ ] Terraform remote backend configured (`terraform/backend.tf` from the example).
- [ ] A second engineer available to review the plan on Day 3.

---

## Day 1 — Tue 18 Aug: preflight (T-72h)

Goal: point the tooling at the new account and start the TTL clock.

1. **Rotate the export identity to the new AWS account** (runbook §1a):
   create the OIDC provider + read-only Route53 role, update the
   `AWS_ROUTE53_READONLY_ROLE_ARN` secret in the `export` environment. Keep the
   trust-policy repo name exactly `tdlmatias/Aws_cloudflare_migration`.
2. **Smoke-test the export workflow** (`workflow_dispatch`). Confirm
   `Found N hosted zone(s)` equals the number of domains you moved.
3. **Lower Route53 TTLs** to 300s on the records in scope. This is the single
   most important downtime lever — it must happen ≥48h before cutover.
4. **Record the baseline:** per zone, note the current authoritative NS and the
   record count (`aws route53 list-resource-record-sets` count). You will
   compare the Terraform plan against these numbers on Day 2–3.

Exit criteria: export workflow green against the new account; TTLs lowered;
baseline counts recorded.

## Day 2 — Wed 19 Aug: export, resolve, validate, plan

1. **Export** the reviewed data: run the export workflow (or
   `./scripts/export_route53.sh terraform/data`) and download the artifact.
2. **Resolve the manual-review report** (`manual-review.json`) — runbook §3.
   Every `invalid_mx` **must** be fixed at source and re-exported before apply.
   Decide the Cloudflare equivalent for aliases, routing policies, and CAA/SRV;
   confirm private hosted zones are intentionally left behind.
3. **Validate:** `make validate` (schema) and `make test` (Python suite).
4. **Open a PR** with the reviewed `zones.json`. CI runs lint/type/tests/
   `terraform validate`/`terraform test`; the `terraform-plan` workflow publishes
   a reviewable plan artifact.
5. **Sanity-check the plan:** zone count == in-scope domains; record count is
   close to the Day 1 baseline; **zero unexpected destroys**.

Exit criteria: PR open, CI green, plan artifact shows creates only (no
surprising destroys), manual-review items resolved.

## Day 3 — Thu 20 Aug: review + protected apply + verify (no cutover)

1. **Second-engineer review** of the plan artifact and resolved review items;
   record the reviewed plan + a migration timestamp in the PR (runbook §6).
2. **Protected apply:** trigger `terraform-apply` via `workflow_dispatch` with
   `confirm=apply`; approve the `production` environment gate. Capture the
   `zone_ids` / `zone_count` / `record_count` outputs.
3. **Verify against the Cloudflare nameservers directly** — *before* any
   registrar change (runbook §8). For each zone, dig the apex A/AAAA, MX, and the
   mail TXT trio explicitly:
   ```bash
   dig @<cloudflare-ns> example.com A +short
   dig @<cloudflare-ns> example.com MX +short
   dig @<cloudflare-ns> example.com TXT +short      # SPF
   dig @<cloudflare-ns> _dmarc.example.com TXT +short
   dig @<cloudflare-ns> <selector>._domainkey.example.com TXT +short  # DKIM
   ```
   Do not proceed until answers match the intended state on every zone.

Exit criteria: apply succeeded; every in-scope zone resolves correctly on its
Cloudflare nameservers; Route53 still untouched and authoritative.

## Day 4 — Fri 21 Aug (morning): registrar cutover + monitor

Cut over in the morning so the team is present through the propagation window.

1. At the registrar, replace the Route53 nameservers with the Cloudflare
   nameservers, one domain at a time (runbook §9). Propagation is bounded by the
   registrar/TLD TTL.
2. **Monitor** resolution and application/email health as each domain flips.
   `dig NS example.com +short` should begin returning the Cloudflare NS.
3. **Do not touch Route53.** It remains the rollback target.

Rollback (any time): revert the registrar NS to the recorded Route53 set;
because Route53 is unchanged and TTLs are low, resolution returns to the old
state quickly (runbook §10 / rollback quick reference).

## Fri PM – Sun 23 Aug: rollback window

- Keep Route53 hosted zones intact and authoritative-capable.
- Watch resolution, email deliverability (SPF/DKIM/DMARC), and app health.
- Investigate any Cloudflare-side issue before considering the migration done.

## Day 5 — Mon 24 Aug: confirm stable, schedule decommission

- Confirm all domains resolve on Cloudflare and applications are healthy.
- **Do not delete Route53 yet from urgency** — schedule the hosted-zone
  decommission as a separate, deliberate change once you are past the agreed
  stability window.

---

## Go / no-go gates

| Gate | Blocks | Condition to pass |
| ---- | ------ | ----------------- |
| G1 (end Day 1) | starting export | Export workflow green on the new account; TTLs lowered ≥48h before cutover |
| G2 (end Day 2) | apply | Plan shows creates only, count ≈ baseline, all `invalid_mx` fixed |
| G3 (end Day 3) | registrar cutover | Every zone verified correct on its Cloudflare NS |
| G4 (Day 4) | leaving cutover | NS delegation observed flipping; mail + app health nominal |

## Out of scope for the automated apply (handle manually in Cloudflare)

Route53 alias records, weighted/latency/failover/geo routing, health checks,
CAA/SRV (need structured `data` blocks), and private hosted zones. These are
listed per-record in `manual-review.json` — none are migrated silently.
