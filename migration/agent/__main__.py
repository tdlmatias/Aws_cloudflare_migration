"""CLI entry point for the migration agent.

Usage:
    python -m migration.agent "Run the export and tell me if we're safe to plan."
    python -m migration.agent            # uses a sensible default task

Requires the optional ``agent`` extra and an Anthropic API key
(``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile). The agent can prepare
and verify the migration but cannot apply it or change nameservers — those stay
human-gated.
"""

from __future__ import annotations

import sys

DEFAULT_TASK = (
    "Run the Route53 export, validate the result, triage the manual-review "
    "report, and tell me whether we are safe to produce a Terraform plan. "
    "Finish with a clear go/no-go and the next human action."
)


def _print_progress(message: object) -> None:
    from migration.agent.runner import iter_tool_calls

    for name, tool_input in iter_tool_calls(message):
        args = ", ".join(f"{k}={v!r}" for k, v in tool_input.items())
        print(f"  → {name}({args})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    task = " ".join(argv).strip() or DEFAULT_TASK

    try:
        from migration.agent.runner import run_agent
    except ImportError:
        print(
            "error: the migration agent requires the 'agent' extra. Install it "
            'with: pip install -e ".[agent]"',
            file=sys.stderr,
        )
        return 1

    try:
        final = run_agent(task, on_message=_print_progress)
    except Exception as exc:  # surface auth/network/API errors cleanly to the CLI
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
