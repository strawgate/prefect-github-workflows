"""
Agent prompt profile registry.

Each profile defines a reusable audit/task that can be deployed as a named
Prefect deployment.  Add new profiles in library.py — they auto-register
as deployments when you run deploy.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentProfile:
    """A reusable agent task definition."""

    # ── Identity ──────────────────────────────────────────────────────
    name: str  # Deployment name, e.g. "security-audit"
    description: str  # Human-readable purpose

    # ── Prompt ────────────────────────────────────────────────────────
    prompt: str  # The instruction sent to the agent
    json_schema: str | None = None  # Optional JSON schema for structured output

    # ── Engine settings ───────────────────────────────────────────────
    engine: str = "both"  # "claude", "copilot", or "both"
    allowed_tools: str = "Read,Grep,Glob"  # Claude Code tool allowlist
    max_budget_usd: float = 5.0
    max_turns: int = 10

    # ── Scheduling ────────────────────────────────────────────────────
    cron: str | None = None  # e.g. "0 2 * * 1" for weekly Monday 2am
    tags: list[str] = field(default_factory=list)

    def deployment_parameters(self) -> dict:
        """Return the parameter dict for Prefect deployment creation."""
        return {
            "prompt": self.prompt,
            "engine": self.engine,
            "allowed_tools": self.allowed_tools,
            "max_budget_usd": self.max_budget_usd,
            "max_turns": self.max_turns,
        }


# Populated by library.py at import time
PROMPT_LIBRARY: list[AgentProfile] = []


def register(*profiles: AgentProfile) -> None:
    """Add profiles to the global registry."""
    PROMPT_LIBRARY.extend(profiles)
