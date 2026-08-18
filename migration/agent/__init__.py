"""Agent-assisted migration tooling.

This subpackage adds an *optional* AI agent that orchestrates the deterministic
migration steps (export, validate, triage, plan-summary, DNS verification) to
reduce human toil and copy-paste errors during a cutover.

Safety boundary — read this before extending the tool set
--------------------------------------------------------
The agent is **capability-gated**: the two irreversible actions in a DNS
migration — running ``terraform apply`` against production Cloudflare and
switching registrar nameservers — are *deliberately not exposed as tools*. The
agent can prepare, validate, and verify everything up to a reviewable plan, but
it structurally cannot mutate production DNS because no such tool exists here.
Those steps stay behind the existing human-gated GitHub workflows
(``terraform-apply.yml`` + the protected ``production`` environment) and the
registrar. Do not add an "apply" or "cutover" tool to :mod:`migration.agent.tools`.

The pure analysis helpers in :mod:`migration.agent.analysis` have no third-party
dependencies and are unit-tested. The LLM harness in
:mod:`migration.agent.runner` requires the optional ``agent`` extra
(``pip install -e ".[agent]"``).
"""

from __future__ import annotations

__all__ = ["analysis"]
