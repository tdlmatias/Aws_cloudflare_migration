"""LLM harness that drives the migration tools with the Anthropic Tool Runner.

This is the only part of the agent that requires the ``agent`` extra
(``pip install -e ".[agent]"``) and an Anthropic API key. The agentic loop is
handled by the SDK's beta tool runner; we only supply the curated, capability-
gated tools and the safety-first system prompt.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from migration.agent.prompt import SYSTEM_PROMPT
from migration.agent.tools import ALL_TOOLS

# Default model. Override with MIGRATION_AGENT_MODEL. `or` (not a get default)
# so an env var exported as an empty string — as CI does when the repo variable
# is unset — still falls back to the default instead of sending a blank model.
DEFAULT_MODEL = os.environ.get("MIGRATION_AGENT_MODEL") or "claude-opus-5"


def run_agent(
    task: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16000,
    on_message: Any = None,
) -> str:
    """Run the agent to completion on ``task`` and return the final text.

    :param task: the natural-language instruction, e.g. "Run the export and tell
        me if we're safe to plan."
    :param on_message: optional callback invoked with each streamed
        ``BetaMessage`` for progress display.
    """
    import anthropic

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        messages=[{"role": "user", "content": task}],
    )

    final_text = ""
    for message in runner:
        if on_message is not None:
            on_message(message)
        for block in message.content:
            if block.type == "text":
                final_text = block.text
    return final_text


def iter_tool_calls(message: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(tool_name, tool_input)`` for each tool call in a message.

    Convenience for progress display; keeps the CLI free of SDK block details.
    """
    for block in message.content:
        if block.type == "tool_use":
            tool_input = block.input if isinstance(block.input, dict) else {}
            yield block.name, dict(tool_input)
