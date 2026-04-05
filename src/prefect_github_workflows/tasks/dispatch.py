"""Agent dispatch — routes to the appropriate CLI task by engine name."""

from __future__ import annotations

from prefect import task

from prefect_github_workflows.tasks.claude import run_claude_code
from prefect_github_workflows.tasks.copilot import run_copilot_cli


@task(retries=0, timeout_seconds=650)
def run_agent(
    engine: str,
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    mcp_config_path: str | None = None,
) -> dict:
    """
    Route to the correct agent engine.

    Called via .map() from the orchestrator flow — one invocation per engine.
    When engine="both", the flow maps over ["claude", "copilot"] so they
    run concurrently.

    Note: This calls the engine functions directly (not as Prefect tasks)
    to avoid nested task issues.  The outer @task decorator on run_agent
    handles retry/timeout/tracking for the entire agent run.
    """
    if engine == "claude":
        return run_claude_code.fn(
            repo_path=repo_path,
            prompt=prompt,
            context_doc=context_doc,
            allowed_tools=allowed_tools,
            max_budget_usd=max_budget_usd,
            max_turns=max_turns,
            json_schema=json_schema,
            mcp_config_path=mcp_config_path,
        )
    if engine == "copilot":
        return run_copilot_cli.fn(
            repo_path=repo_path,
            prompt=prompt,
            context_doc=context_doc,
            allowed_tools=allowed_tools,
            max_budget_usd=max_budget_usd,
            max_turns=max_turns,
            json_schema=json_schema,
            mcp_config_path=mcp_config_path,
        )
    raise ValueError(f"Unknown engine: {engine!r}.  Use 'claude' or 'copilot'.")
