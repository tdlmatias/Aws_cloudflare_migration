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
- [ ] **DNSSEC inventory:** for each in-scope zone, record whether DNSSEC is
  enabled (a DS record published at the registrar/parent) and note the DS TTL.
  DNSSEC zones need the extra transition in Day 1 step 5 — cutting over with a
  stale DS breaks the chain of trust and returns SERVFAIL.

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
5. **Begin the DNSSEC transition for any signed zone.** You cannot carry the
   Route53 DNSSEC keys to Cloudflare, so the chain of trust must be broken
   before cutover and re-established after. For each zone with DNSSEC enabled:
   first **remove the DS record at the parent (your registrar / the TLD)** —
   disabling signing in Route53 does *not* withdraw a parent DS, and leaving the
   DS in place while the signatures change returns SERVFAIL, possibly before
   cutover even begins. Then **wait for the DS TTL to expire** so no validating
   resolver still expects the old chain. Only once the DS has aged out is it safe
   to change that zone's nameservers (and to disable Route53 signing if you
   wish). Cloudflare DNSSEC is re-enabled after verification (Day 4 step 4).
   Zones without DNSSEC skip this.

Exit criteria: export workflow green against the new account; TTLs lowered;
baseline counts recorded; DS removed (and TTL-expired, or expiring) for every
DNSSEC zone.

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
   **Merge the reviewed PR to `main`** so the reviewed `zones.json` is the tip of
   the branch you will apply from — do not apply from an unmerged or stale ref.
2. **Protected apply — review the exact plan, then approve.** `terraform-apply`
   runs two jobs: a `plan` job builds a fresh plan and prints it to the job
   summary, then a gated `apply` job consumes that saved plan. So:
   - Dispatch `terraform-apply` (`workflow_dispatch`, `confirm=apply`) against
     the reviewed commit. `workflow_dispatch` only accepts a **branch or tag**,
     not a raw SHA, so either dispatch from `main` immediately after the step-1
     merge (its tip is then the reviewed merge commit) or, safer, tag that commit
     (e.g. `git tag cutover-2026-08-20 <sha> && git push origin cutover-2026-08-20`)
     and dispatch from the tag so an intervening push to `main` cannot change it.
   - When the run pauses at the `production` environment gate, **read the plan
     job's summary** and confirm it matches the reviewed plan (same creates,
     still zero destroys) *before* approving. Because the gate is on the apply
     job, the plan already exists when you approve, and apply replays that exact
     plan — Terraform aborts if state drifted, so a stale plan cannot be applied.
   - Capture the `zone_ids` / `zone_count` / `record_count` outputs.
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
4. **Re-enable DNSSEC — in the right order, with a wait.** For each zone you
   broke DNSSEC on in Day 1 step 5:
   1. Enable DNSSEC in Cloudflare (this generates the new DS) *after* the zone
      verifies clean on the Cloudflare nameservers.
   2. **Wait for the old parent delegation TTL to expire** after the nameserver
      change before publishing the new DS. One clean query is not enough:
      resolvers can still have the old Route53 delegation cached, and if such a
      resolver picks up the new Cloudflare DS while it is still answering from
      Route53's nameservers, it validates Route53's answers against Cloudflare's
      key and returns SERVFAIL. Only once the old delegation has aged out
      everywhere is it safe to publish the new DS at the registrar. (A
      coordinated multi-signer transition avoids the wait but is more involved.)

Rollback (any time): revert the registrar NS to the recorded Route53 set.
Recovery speed is bounded by the **parent delegation TTL** (the registry/TLD's
TTL on the NS/DS records), **not** the Route53 record TTLs — validating
resolvers may keep querying the Cloudflare nameservers until the delegation
you set at cutover expires from their cache. Lowering record TTLs in Day 1
speeds recovery *within* a zone once resolvers follow the delegation back to
Route53; it does not shorten the delegation TTL itself. Size the rollback window
around that delegation TTL, and if a zone had DNSSEC, also withdraw the
Cloudflare DS as part of rolling back. (runbook §10 / rollback quick reference).

## Fri PM – Sun 23 Aug: rollback window

- Keep Route53 hosted zones intact and authoritative-capable.
- Watch resolution, email deliverability (SPF/DKIM/DMARC), and app health.
- Investigate any Cloudflare-side issue before considering the migration done.

## Day 5 — Mon 24 Aug: confirm stable, schedule decommission

- Confirm all domains resolve on Cloudflare and applications are healthy.
- **Do not delete Route53 out of urgency** — schedule the hosted-zone
  decommission as a separate, deliberate change once you are past the agreed
  stability window.

---

## Go / no-go gates

| Gate | Blocks | Condition to pass |
| ---- | ------ | ----------------- |
| G1 (end Day 1) | starting export | Export workflow green on the new account; TTLs lowered ≥48h before cutover |
| G2 (end Day 2) | apply | Plan shows creates only, count ≈ baseline, all `invalid_mx` fixed |
| G3 (end Day 3) | registrar cutover | Reviewed PR merged; apply dispatched from that SHA and the fresh in-run plan re-confirmed at the approval gate; every zone verified correct on its Cloudflare NS |
| G-DNSSEC (per zone, before its NS switch) | registrar cutover of a signed zone | Old DS removed at the parent and its DS TTL expired; new Cloudflare DS **not** published until after the NS flip verifies |
| G4 (Day 4) | leaving cutover | NS delegation observed flipping; mail + app health nominal; Cloudflare DNSSEC re-enabled + new DS published for signed zones |

## Out of scope for the automated apply (handle manually in Cloudflare)

Route53 alias records, weighted/latency/failover/geo routing, health checks,
CAA/SRV (need structured `data` blocks), and private hosted zones. These are
listed per-record in `manual-review.json` — none are migrated silently.
