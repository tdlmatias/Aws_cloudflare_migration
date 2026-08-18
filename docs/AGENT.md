# Migration Agent

An optional AI assistant that orchestrates the deterministic migration steps to
reduce human toil and copy-paste error during a cutover. It runs the read-only,
verifiable work and produces a go/no-go report; it does **not** perform the
irreversible steps.

## Safety boundary (read this first)

The agent is **capability-gated**, not just prompt-gated. The two irreversible
actions in a DNS migration —

1. `terraform apply` against production Cloudflare, and
2. switching registrar nameservers —

are **deliberately not exposed as tools**. The agent literally has no function to
call that could apply Terraform or touch the registrar, so it cannot mutate
production DNS even if instructed to. Those steps stay behind the existing
human-gated controls: the protected `terraform-apply` GitHub workflow (typed
`confirm=apply` + `production` environment reviewer) and the registrar itself.

> Do not add an "apply" or "cutover" tool to `migration/agent/tools.py`. Doing so
> would remove the guarantee that this agent cannot break production.

## What the agent can do

| Tool | Purpose |
| ---- | ------- |
| `run_route53_export` | Run the read-only Route53 export; report zone/record counts |
| `validate_zones_document` | Validate `zones.json` against the bundled JSON Schema |
| `summarize_manual_review` | Classify `manual-review.json`; flag blockers (`invalid_mx`, `empty_record_set`) |
| `diff_record_counts` | Compare the export against a pre-migration baseline; flag missing zones / big drops |
| `summarize_terraform_plan` | Summarise `terraform show -json` output; surface any destroy/replace |
| `verify_cloudflare_records` | `dig` each intended record on a Cloudflare NS and compare to `zones.json` |

The error-prone logic behind these tools lives in
`migration/agent/analysis.py` — pure functions with no third-party dependency,
covered by `tests/test_agent_analysis.py`. The LLM harness
(`migration/agent/runner.py`) uses the Anthropic SDK's tool runner to drive the
agentic loop over exactly this tool set.

## Install

```bash
pip install -e ".[agent]"     # adds the anthropic SDK
```

Authentication: set `ANTHROPIC_API_KEY`, or use an `ant auth login` profile. The
export tool additionally needs the AWS CLI authenticated with read-only Route53
access (same as `scripts/export_route53.sh`); `verify_cloudflare_records` needs
`dig`.

## Run locally

```bash
# Default task: export → validate → triage → go/no-go
python -m migration.agent

# Or give it a specific instruction
python -m migration.agent "Verify example.com resolves correctly on dana.ns.cloudflare.com."
```

Tool calls are printed to stderr as they happen; the final report goes to stdout.
Choose the model with `MIGRATION_AGENT_MODEL` (default `claude-opus-5`).

## Run in CI

The `Migration Agent` workflow (`.github/workflows/agent.yml`, `workflow_dispatch`)
runs the agent in the `export` environment using the same read-only AWS OIDC role
as the export workflow, and publishes the report to the job summary and an
artifact. It requires an `ANTHROPIC_API_KEY` secret in that environment. Because
the agent has no apply/cutover tool, this workflow cannot change production DNS.

## Where it fits in the runbook

The agent automates steps 2–5 and 8 of `MIGRATION_RUNBOOK.md` (export, triage,
validate, plan-summary, DNS verification) and reports against the go/no-go gates
in `CUTOVER_PLAN.md`. The human still performs step 7 (protected apply) and step 9
(registrar cutover).
