# Phase 1 Execution Tracker — Route53 → Cloudflare (Days 1–3)

**Scope of this phase:** build and verify the Cloudflare zones for the 12
in-scope domains, up to and including the protected `terraform apply`, and
verify resolution on the Cloudflare nameservers. **No registrar cutover in this
phase** — Route53 stays authoritative and untouched throughout.

This is the operational tracker that sits on top of
[`CUTOVER_PLAN.md`](CUTOVER_PLAN.md) (the dated schedule) and
[`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md) (the detailed procedure). Follow
those for the "why"; use this to record state and pass each go/no-go gate.

> Fill in the `〔 〕` placeholders as you go. Keep this file updated in the PR so
> the second reviewer sees live state.

### Conventions

- **In-scope zone count = `N = 12`.** This is the single source of truth for
  this migration (per the repo scope: "Migration of 12 Domains and DNS
  Records"). Every "12" / "expect 12" below refers to this `N`; if the in-scope
  domain set changes, update it here and re-derive the expectations.
- **Field types.** 🎯 marks a **strict expectation** — a mismatch means the
  gate is **HOLD**, not PASS (e.g. `zone_count` must equal `N`; destroys must be
  zero). ✍️ marks an **observed value to record** for later comparison (e.g.
  baseline record counts, run URLs, nameservers) — recording it never fails a
  gate by itself, but it feeds a 🎯 check downstream.

---

## 0. Readiness snapshot (verified by tooling review)

| Check | State | Notes |
| ----- | ----- | ----- |
| Python quality gate (ruff / mypy / pytest) | ✅ Green | 59 tests, 98.48% coverage locally |
| `zones.json` schema validation | ✅ Valid | but see next row — it is still **sample data** |
| Real Route53 export performed | ❌ **Not yet** | `terraform/data/zones.json` still holds the sample `example.com` zone; **no export workflow run exists** |
| `AWS_ROUTE53_READONLY_ROLE_ARN` secret (`export` env) | ❓ Unverified | export workflow has never run — must be confirmed in Day 1 |
| Cloudflare creds in `plan` environment | ❌ **Absent** | latest `terraform-plan` on `main` **skipped** the plan steps (creds gate false) |
| Cloudflare creds in `production` environment | ❓ Unverified | needed for the protected apply (Day 3) |
| Terraform remote backend configured | ❓ Unverified | `terraform/backend.tf` must exist (from `backend.tf.example`) before apply |

**Bottom line:** the gating blocker for this phase is that **no real export of
the 12 domains has ever run**, and **Cloudflare credentials are not yet
configured**. Everything below Day 1 depends on clearing those.

---

## Prerequisites checklist (have in hand before Day 1)

- [ ] Registrar login for every in-scope domain (needed later; not used this phase).
- [ ] Admin on the **new** AWS account holding the 12 hosted zones.
- [ ] Cloudflare account id (32-hex) + a scoped API token (`Zone:Edit`, `DNS:Edit`).
- [ ] Terraform remote backend configured (`terraform/backend.tf` from the example).
- [ ] A second engineer lined up to review the plan on Day 3.
- [ ] DNSSEC inventory started (table in Day 1 §5).

---

## Day 1 — Preflight (T-72h)

### 1.1 Rotate the export identity to the new AWS account

In the **new** AWS account (the one that now holds the 12 zones):

1. Ensure a GitHub OIDC provider exists: `token.actions.githubusercontent.com`,
   audience `sts.amazonaws.com`.
2. Create a **read-only Route53 role** with the trust policy and IAM policy from
   [`SECURITY_MODEL.md`](SECURITY_MODEL.md). Keep the repo name in `sub` exactly
   `tdlmatias/Aws_cloudflare_migration` (capital `A`) — IAM `StringLike` is
   case-sensitive.
3. Set the GitHub secret `AWS_ROUTE53_READONLY_ROLE_ARN` in the **`export`**
   environment to the new role's ARN.

- Role ARN recorded in `export` env secret: 〔 yes / no 〕
- Trust `sub` scoped to `...:environment:export`: 〔 yes / no 〕

### 1.2 Smoke-test the export workflow

Dispatch **Route53 Export** (`workflow_dispatch`). Confirm the log line
`Found N hosted zone(s)` equals **12**.

- ✍️ Run URL: 〔 …/actions/runs/____ 〕
- 🎯 `Found N hosted zone(s)` → N = 〔 __ 〕 (must equal 12)
- 🎯 Result: 〔 green / failed 〕 (must be green)

> If it fails at "Configure AWS credentials": re-check the trust-policy `sub`
> and the account id.

### 1.3 Lower Route53 TTLs to 300s (the key downtime lever)

Must happen **≥48h before** any cutover. This phase stops before cutover, but do
it now so the clock is running.

- TTLs lowered on in-scope records: 〔 yes / no 〕 — timestamp: 〔 ____ 〕

### 1.4 Record the baseline (per zone)

Per zone: current authoritative NS and record count
(`aws route53 list-resource-record-sets` count). Compare against the Terraform
plan on Day 2–3.

| # | Domain | Route53 record count | Current authoritative NS | DNSSEC? | DS TTL |
| - | ------ | -------------------- | ------------------------ | ------- | ------ |
| 1 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 2 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 3 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 4 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 5 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 6 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 7 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 8 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 9 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 10 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 11 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |
| 12 | 〔 〕 | 〔 〕 | 〔 〕 | 〔 y/n 〕 | 〔 〕 |

### 1.5 Begin the DNSSEC transition (signed zones only)

For every zone marked DNSSEC = yes above: **remove the DS record at the parent
(registrar/TLD) first**, then wait for the DS TTL to expire. Do **not** carry
Route53 DNSSEC keys to Cloudflare. (Cloudflare DNSSEC is re-enabled only after
cutover verification — that is Day 4, outside this phase.)

- Zones needing DNSSEC transition: 〔 list 〕
- DS removed at parent: 〔 per-zone status 〕

**Gate G1 (end Day 1):** export green against the new account (N = 12); TTLs
lowered; baseline recorded; DS removed/expiring for every signed zone. → 〔 PASS / HOLD 〕

---

## Day 2 — Export, resolve, validate, plan

### 2.1 Export the reviewed data

Run the **Route53 Export** workflow (or `./scripts/export_route53.sh
terraform/data`) and download the artifact (`zones.json` +
`manual-review.json`). The export is **not** auto-committed — a human reviews
the diff.

- ✍️ Export run URL: 〔 〕
- 🎯 Zones in `zones.json`: 〔 __ 〕 (must equal 12)

### 2.2 Resolve the manual-review report

Open `manual-review.json`. Every `invalid_mx` **must** be fixed at source and
re-exported before apply. Decide the Cloudflare equivalent for aliases, routing
policies, and CAA/SRV; confirm private hosted zones are intentionally left
behind. (Table of reasons/actions is in [`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md) §3.)

- `invalid_mx` count: 〔 __ 〕 → all fixed & re-exported: 〔 yes / no 〕
- Aliases / routing / CAA / SRV decisions recorded: 〔 yes / no 〕
- Private hosted zones intentionally excluded: 〔 yes / no 〕

### 2.3 Validate

```bash
make validate    # schema
make test        # Python suite   (if pytest cov plugin errors, use: python -m pytest --cov=migration --cov-report=term-missing --cov-fail-under=85)
```

- validate: 〔 pass / fail 〕 · test: 〔 pass / fail 〕

### 2.4 Open a PR with the reviewed `zones.json`

CI runs lint/type/tests/`terraform validate`/`terraform test`. The
`terraform-plan` workflow publishes a reviewable plan artifact **only once
Cloudflare creds exist in the `plan` environment** (otherwise it skips green —
this is the current state, so configure those creds first).

- PR: 〔 #____ 〕 · CI: 〔 green / red 〕 · plan artifact produced: 〔 yes / no 〕

### 2.5 Sanity-check the plan

- 🎯 Zone count == 12: 〔 yes / no 〕
- 🎯 Record count ≈ Day-1 baseline sum (✍️ record both): 〔 plan __ vs baseline __ 〕
- 🎯 **Zero unexpected destroys**: 〔 confirmed 〕

**Gate G2 (end Day 2):** plan shows **creates only**, count ≈ baseline, all
`invalid_mx` fixed. → 〔 PASS / HOLD 〕

---

## Day 3 — Review + protected apply + verify (NO cutover)

### 3.1 Second-engineer review + merge

Second engineer reviews the plan artifact and resolved review items. Record the
reviewed plan + a migration timestamp in the PR, then **merge to `main`** so the
reviewed `zones.json` is the tip you apply from.

- Reviewer: 〔 〕 · Reviewed plan recorded in PR: 〔 yes 〕 · Merged commit: 〔 sha 〕

### 3.2 Protected apply — review the exact plan, then approve

`terraform-apply` runs a `plan` job (prints plan to the job summary) then a
gated `apply` job (protected `production` environment, required reviewer).

1. Tag the reviewed commit and dispatch from the tag (safer than dispatching
   from `main`, which an intervening push could move):
   ```bash
   git tag cutover-2026-08-20 <reviewed-sha>
   git push origin cutover-2026-08-20
   ```
   Dispatch **Terraform Apply** (`workflow_dispatch`, `confirm=apply`) from the tag.
2. When it pauses at the `production` gate, **read the plan job's summary** and
   confirm it matches the reviewed plan (same creates, still zero destroys)
   **before** approving. Terraform aborts if state drifted, so a stale plan
   cannot be applied.
3. Capture outputs: `zone_count`, `record_count`, `zone_ids`.

- ✍️ Apply run URL: 〔 〕 · 🎯 plan re-confirmed at gate: 〔 yes 〕
- 🎯 `zone_count` = 〔 __ 〕 (must equal 12) · ✍️ `record_count` = 〔 __ 〕 (record; compare to baseline)

### 3.3 Verify against the Cloudflare nameservers directly (before any registrar change)

For each zone, dig the apex A/AAAA, MX, and the mail TXT trio explicitly on the
zone's assigned Cloudflare NS:

```bash
dig @<cloudflare-ns> example.com A +short
dig @<cloudflare-ns> example.com MX +short
dig @<cloudflare-ns> example.com TXT +short                 # SPF
dig @<cloudflare-ns> _dmarc.example.com TXT +short
dig @<cloudflare-ns> <selector>._domainkey.example.com TXT +short   # DKIM
```

Do not treat this phase as done until answers match the intended state on every
zone. (Proxied records won't match origin content — verify those another way,
per the agent's `skipped_proxied` handling.)

- 🎯 Zones verified clean on Cloudflare NS: 〔 __ / 12 〕 (must be 12/12 to pass G3)

**Gate G3 (end Day 3):** reviewed PR merged; apply dispatched from that
SHA/tag and the fresh in-run plan re-confirmed at the approval gate; every zone
verified correct on its Cloudflare NS; **Route53 still untouched and
authoritative**. → 〔 PASS / HOLD 〕

---

## Phase 1 exit

- [ ] All 12 zones exist in Cloudflare and resolve correctly on their Cloudflare NS.
- [ ] Route53 unchanged and still authoritative (no registrar NS change made).
- [ ] Outputs and verification recorded above.
- [ ] Cutover (Day 4) scheduled as a **separate** change — not part of this phase.

## Decision / deviation log

| Date | Decision or deviation | By |
| ---- | --------------------- | -- |
| 〔 〕 | 〔 〕 | 〔 〕 |
