# Phase 1 Execution Tracker — Route53 → Cloudflare (Days 1–3)

**Scope of this phase:** build and verify the Cloudflare zones for the 12
in-scope domains, up to and including the protected `terraform apply`, and
verify resolution on the Cloudflare nameservers. **No registrar cutover in this
phase** — Route53 stays authoritative and rollback-capable throughout, with no
record changes other than the planned Day-1 TTL reductions.

This is the operational tracker that sits on top of
[`CUTOVER_PLAN.md`](CUTOVER_PLAN.md) (the dated schedule) and
[`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md) (the detailed procedure). Follow
those for the "why"; use this to record state and pass each go/no-go gate.

> Fill in the `〔 〕` placeholders as you go. Keep this file updated in the PR so
> the second reviewer sees live state.

### Conventions

- **In-scope zone count = `N = 12` public zones.** This is the single source of
  truth for this migration (per the repo scope: "Migration of 12 Domains and DNS
  Records"). `N` counts the **public, in-scope** zones — the ones that reach
  `zones.json` and Terraform. Track them as an explicit **named set**, not just a
  number, so a private-zone exclusion can't be hidden by a count. Every "12"
  below refers to this `N`; if the in-scope domain set changes, update it here.
- **Two different denominators — don't gate them against the same number.**
  `scripts/export_route53.sh` logs `Found N hosted zone(s)` = **every** hosted
  zone in the account, **including private and out-of-scope** ones.
  By default `convert_hosted_zones()` drops **only private** zones (routed to
  review as `private_hosted_zone`) and migrates **every public** zone, in-scope
  or not — so without an allowlist both the raw account count *and* `zones.json`
  can exceed 12. Passing the **in-scope allowlist** (§2.1a) additionally routes
  every non-listed zone to review as `out_of_scope_zone`, so `zones.json` then
  holds exactly the 12 listed domains while the raw account count may still be
  higher.
- **The set is the gate, not a count.** Confirm `zones.json`'s zone set is
  **exactly the 12 named in-scope domains** — no missing ones, and no extras. An
  out-of-scope public zone is not migrated **only if** you pass the in-scope
  allowlist (`--in-scope-file` / `--in-scope-zone`, or `IN_SCOPE_ZONES_FILE` for
  the export script); without it, an extra public zone enters the plan and
  creates an unintended Cloudflare zone. Apply the allowlist and validate the
  set — see §2.1a.
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

### 1.1a Commit the in-scope allowlist (before the smoke test)

Do this **now**, not on Day 2: the export workflow's `in_scope_file` input
defaults to `config/in-scope-zones.txt` and **fails closed** if that path is set
but missing. On a fresh checkout only `config/in-scope-zones.txt.example` exists,
so the §1.2 smoke test would error before it ever queries Route53. Either:

- **Recommended:** copy the example, list your 12 domains, and commit it — then
  every export (Day 1 onward) is scope-enforced:
  ```bash
  cp config/in-scope-zones.txt.example config/in-scope-zones.txt
  $EDITOR config/in-scope-zones.txt && git add config/in-scope-zones.txt && git commit
  ```
- **Or**, for an unscoped smoke test only, dispatch §1.2 with the `in_scope_file`
  input **cleared** (blank) — every public zone is exported and you reconcile by
  hand per §2.1a.

- 🎯 `config/in-scope-zones.txt` committed with the 12 domains, **or** decision to run §1.2 unscoped recorded: 〔 committed / unscoped 〕

### 1.2 Smoke-test the export workflow

Dispatch **Route53 Export** (`workflow_dispatch`), leaving the `in_scope_file`
input at its default once §1.1a is committed (or blank for an unscoped run). The
`Found N hosted zone(s)`
log counts **all** hosted zones in the account — public, private, and
out-of-scope — so `N ≥ 12`; it equals 12 only if the account holds nothing but
the in-scope public zones. The real check is that **all 12 in-scope public
domains appear** in the export.

- ✍️ Run URL: 〔 …/actions/runs/____ 〕
- ✍️ `Found N hosted zone(s)` → N = 〔 __ 〕 (raw account total; ≥ 12, may include private/out-of-scope)
- 🎯 All 12 in-scope public domains present in the export: 〔 __ / 12 〕 (must be 12/12)
- ✍️ Non-in-scope zones seen (private / out-of-scope), if any: 〔 list 〕
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

**Gate G1 (end Day 1):** export green against the new account with **all 12
in-scope public domains present** (the raw `Found N` may be higher if the
account holds private/out-of-scope zones); TTLs lowered; baseline recorded; DS
removed/expiring for every signed zone. → 〔 PASS / HOLD 〕

---

## Day 2 — Export, resolve, validate, plan

### 2.1 Export the reviewed data

Run the **Route53 Export** workflow (or `./scripts/export_route53.sh
terraform/data`) and download the artifact (`zones.json` +
`manual-review.json`). The export is **not** auto-committed — a human reviews
the diff.

- ✍️ Export run URL: 〔 〕
- ✍️ Reconcile from the **`manual-review.json` reason counts** (each excluded zone appears under exactly one reason, so they don't overlap): raw `Found N` 〔 __ 〕 − `private_hosted_zone` entries 〔 __ 〕 − `out_of_scope_zone` entries 〔 __ 〕 = zones in `zones.json` 〔 __ 〕
  - *Count zone-level exclusions from the report, not from your own head-count: the converter checks the allowlist **before** the private-zone check, so a private zone that isn't on the allowlist is emitted once as `out_of_scope_zone` (not `private_hosted_zone`) — counting it under both would double-subtract. With the §2.1a allowlist the result should equal 12; without it, `out_of_scope_zone` is 0 and any extra public zone stays in `zones.json` (prune per §2.1a).*
- 🎯 `zones.json` zone set == the 12 named in-scope domains, **no extras**: 〔 yes / no 〕
- ✍️ Zones excluded as `out_of_scope_zone` (allowlist) / extras still to prune: 〔 list / none 〕

### 2.1a Scope the export to the 12 in-scope domains

By default the converter drops private zones but **not** out-of-scope public
zones, so any extra public zone in the export would otherwise enter the plan.
**Enforce scope with the in-scope allowlist** so this is handled by the tooling
rather than by hand: any zone not on the list is routed to manual review as
`out_of_scope_zone` instead of migrated.

```bash
# Commit the 12 in-scope domains, one per line (see config/in-scope-zones.txt.example):
cp config/in-scope-zones.txt.example config/in-scope-zones.txt
$EDITOR config/in-scope-zones.txt      # list the 12 real domains, then commit

# Route53 Export workflow: the in_scope_file input defaults to
# config/in-scope-zones.txt — if that file exists, scope is enforced automatically.

# Local script:
IN_SCOPE_ZONES_FILE=config/in-scope-zones.txt ./scripts/export_route53.sh terraform/data

# Or directly on the converter:
python -m migration convert --zones … --records-dir … \
  --output zones.json --review-output manual-review.json \
  --in-scope-file config/in-scope-zones.txt   # or repeat --in-scope-zone domain.com
```

Then confirm `zones.json`'s zone set is exactly the 12 named domains; the
excluded zones appear in `manual-review.json` as `out_of_scope_zone` for the
audit trail. (If you don't use the allowlist, reconcile by hand and delete extra
zone objects from `zones.json` before planning.)

- 🎯 `zones.json` contains exactly the 12 named zones (allowlist applied): 〔 yes / no 〕
- ✍️ Zones excluded as `out_of_scope_zone` (name → why out of scope): 〔 list / none 〕

### 2.2 Resolve the manual-review report

Open `manual-review.json`. The converter (`convert_record_set`) **omits** every
manual-review record from `zones.json` — aliases, routing policies, CAA/SRV,
unsupported types, empty record sets — so Terraform will **not** create them.
Recording a *decision* is not enough: a decided-but-unimplemented record is a
DNS record that silently disappears at cutover.

**Blockers first.** `classify_manual_review` flags `BLOCKING_REVIEW_REASONS` —
**`invalid_mx` _and_ `empty_record_set`** — as malformed input. These are **not**
dispositionable: they must be fixed at source and re-exported until they no
longer appear. An `empty_record_set` marked "omitted" or "post-apply" would pass
this checklist while the classifier still reports a blocker — don't do that.

Everything else in `classify_manual_review`'s **`requires_action`** list is the
disposition checklist. Each such item needs a **recorded disposition** — one of:

1. **Fold into the reviewed Terraform plan** so `terraform apply` creates it
   (e.g. an alias → a `cloudflare_record` CNAME/origin). Confirm it shows as a
   planned *create* in §2.5.
2. **Schedule as a post-apply manual task** when the record needs a live zone
   that does not exist until the Day-3 apply — CAA/SRV structured `data` blocks,
   dashboard-only settings. Implemented and verified in **§3.2a**, before G3.
3. **Explicitly sign off for omission**, by name + who (e.g. a
   `private_hosted_zone` intentionally left behind).

> **Note on `ready_for_apply`.** `classify_manual_review` takes no sign-off
> input: it recomputes `requires_action` from every non-managed entry and sets
> `ready_for_apply = not requires_action`. So `ready_for_apply` is `true` **only
> when the export contains no non-managed review items at all** — record it, but
> it will (correctly) stay `false` whenever there is any intentional exclusion
> such as a private zone. **G2 does not require `ready_for_apply: true`;** it
> requires every `requires_action` item to carry a disposition (1–3 above), with
> the human sign-off recorded here since the classifier cannot represent it.
(Table of reasons/actions is in [`MIGRATION_RUNBOOK.md`](MIGRATION_RUNBOOK.md) §3.)

- ✍️ `ready_for_apply` (machine signal): 〔 true / false 〕 — false is fine if all items are dispositioned below
- 🎯 Blockers (`invalid_mx` + `empty_record_set`) count: 〔 __ 〕 → all fixed & re-exported to zero: 〔 yes / no 〕 (must be yes)
- 🎯 Every remaining `requires_action` item has a disposition (in-plan / post-apply / omitted): 〔 __ / __ 〕
- ✍️ Per-item disposition (item → 1 in-plan / 2 post-apply / 3 omitted-by + who): 〔 list 〕
- 🎯 Private hosted zones explicitly signed off for exclusion: 〔 yes / no / n-a 〕

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

- 🎯 Plan creates **exactly the 12 named in-scope zones** — no missing, no extra (§2.1a pruning done): 〔 yes / no 〕
- 🎯 Record count ≈ Day-1 baseline sum (✍️ record both): 〔 plan __ vs baseline __ 〕
- 🎯 **Zero unexpected destroys**: 〔 confirmed 〕

**Gate G2 (end Day 2):** plan shows **creates only** for **exactly the 12 named
in-scope zones** (extras pruned per §2.1a), count ≈ baseline, **both blocker
reasons (`invalid_mx` + `empty_record_set`) fixed to zero and re-exported**,
**and every remaining `requires_action` item carries a recorded disposition** — folded into the plan, scheduled as a §3.2a post-apply task, or
signed off for omission. (Records that need a live zone are *scheduled* here and
implemented after apply — not required to exist in Cloudflare at G2. Do **not**
gate on `ready_for_apply: true`; see the note in §2.2.) → 〔 PASS / HOLD 〕

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

### 3.2a Implement the scheduled post-apply manual records (before G3)

The apply in §3.2 created the `cloudflare_zone` resources, so the zones now
exist. Implement every manual-review item dispositioned as **"post-apply"** in
§2.2 (CAA/SRV `data` blocks, alias → CNAME/origin, dashboard-only settings) and
verify each one. Items dispositioned **"in-plan"** were already created by the
apply; items **"omitted"** are intentionally skipped.

- 🎯 Post-apply manual records implemented & verified: 〔 __ / __ 〕
- ✍️ Per-item: 〔 record → implemented + verified how 〕

### 3.3 Verify against the Cloudflare nameservers directly (before any registrar change)

**Verify _every_ migrated record per zone, not just the apex.** A zone can pass
an apex-only spot check while an auto-migrated subdomain A/AAAA/CNAME/TXT/NS
record is missing or wrong — and that broken hostname only surfaces after the
registrar cutover, when it is hardest to fix.

**Primary check — full per-zone verification.** Run the repo's
`verify_cloudflare_records` (agent tool, `migration/agent/tools.py`), which digs
**every unproxied entry in `zones.json`** against the zone's Cloudflare NS and
reports proxied entries separately as `skipped_proxied`.

The per-zone pass rule depends on whether the zone has proxied records:

- **Zone with no proxied records** → require **`fully_verified: true`** (from
  `verification_passed()`: at least one record verified, all verified records
  match, and `skipped_proxied` count is zero). Not a bare `all_match`, which is
  vacuously true for an all-proxied zone.
- **Zone with proxied records** → `verification_passed()` returns `false` **by
  design** (it fails whenever `skipped_proxied` is nonzero, and the tool has no
  attestation input), so `fully_verified` is unreachable and must **not** be the
  gate. Instead require the **composite**: every **unproxied** record verified by
  origin parity (the tool's `all_match` over the unproxied set) **and** every
  `skipped_proxied` record **attested** another way (Cloudflare dashboard /
  proxied-aware check), recorded per item below.

> Making a single machine signal cover proxied zones — extending
> `verify_cloudflare_records`/`verification_passed()` to accept a recorded
> attestation for `skipped_proxied` records — is a reasonable code follow-up, but
> this phase gates on the composite above and does not require that change.

**Manual spot check (apex + mail), in addition — not instead of:**

```bash
dig @<cloudflare-ns> example.com A +short
dig @<cloudflare-ns> example.com MX +short
dig @<cloudflare-ns> example.com TXT +short                 # SPF
dig @<cloudflare-ns> _dmarc.example.com TXT +short
dig @<cloudflare-ns> <selector>._domainkey.example.com TXT +short   # DKIM
```

A zone is "clean" only when **every** record in its `zones.json` entry is
accounted for — verified by origin parity, or explicitly attested if proxied.

- 🎯 Zones passing the per-zone rule (`fully_verified`, **or** unproxied-verified + proxied-attested): 〔 __ / 12 〕 (must be 12/12)
- ✍️ Proxied records attested per zone (record → how attested): 〔 list / n-a 〕

**Gate G3 (end Day 3):** reviewed PR merged; apply dispatched from that
SHA/tag and the fresh in-run plan re-confirmed at the approval gate; all §3.2a
post-apply manual records implemented & verified; **every migrated record** on
every zone verified per the §3.3 per-zone rule (`fully_verified`, or
unproxied-verified + proxied-attested) — not just apex/mail; **Route53 still
authoritative and rollback-capable — no record changes beyond the Day-1 TTL
reductions, and no registrar NS change**. → 〔 PASS / HOLD 〕

---

## Phase 1 exit

- [ ] All 12 zones exist in Cloudflare and pass the §3.3 per-zone verification rule (every migrated record verified or proxied-attested, not apex-only) on their Cloudflare NS.
- [ ] Route53 still authoritative and rollback-capable — only the Day-1 TTL reductions changed, no registrar NS change made.
- [ ] Outputs and verification recorded above.
- [ ] Cutover (Day 4) scheduled as a **separate** change — not part of this phase.

## Decision / deviation log

| Date | Decision or deviation | By |
| ---- | --------------------- | -- |
| 〔 〕 | 〔 〕 | 〔 〕 |
