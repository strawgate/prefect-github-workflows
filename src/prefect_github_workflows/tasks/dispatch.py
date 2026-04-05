"""Agent dispatch — routes to the appropriate CLI task by engine name."""

from __future__ import annotations

import tempfile
from pathlib import Path

from prefect import task

from prefect_github_workflows.mcp.config import create_mcp_config
from prefect_github_workflows.tasks.claude import run_claude_code
from prefect_github_workflows.tasks.containers import (
    ensure_agent_image,
    run_agent_in_container,
)
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
    use_docker: bool = False,
) -> dict:
    """
    Route to the correct agent engine.

    Called via .map() from the orchestrator flow — one invocation per engine.
    When engine="both", the flow maps over ["claude", "copilot"] so they
    run concurrently.

    When ``use_docker=True``, the agent runs inside an isolated Docker
    container with:
      - The cloned repo mounted read-only
      - Only the engine's own auth token
      - Safe-outputs JSONL mounted read-write for the orchestrator to read

    When ``use_docker=False`` (default, for local dev), the agent runs as
    a direct subprocess with env-var sandboxing via ``sandbox_env.py``.

    Note: The engine functions are plain functions (not Prefect tasks)
    to avoid nested task issues.  The outer @task decorator on run_agent
    handles retry/timeout/tracking for the entire agent run.
    """
    # Create temp file for safe-outputs
    with tempfile.NamedTemporaryFile(suffix=".jsonl", prefix="safe_outputs_", delete=False) as f:
        output_path = f.name

    if use_docker:
        return _run_in_docker(
            engine=engine,
            repo_path=repo_path,
            prompt=prompt,
            context_doc=context_doc,
            allowed_tools=allowed_tools,
            max_budget_usd=max_budget_usd,
            max_turns=max_turns,
            json_schema=json_schema,
            safe_outputs_file=output_path,
        )

    return _run_subprocess(
        engine=engine,
        repo_path=repo_path,
        prompt=prompt,
        context_doc=context_doc,
        allowed_tools=allowed_tools,
        max_budget_usd=max_budget_usd,
        max_turns=max_turns,
        json_schema=json_schema,
        mcp_config_path=mcp_config_path,
        safe_outputs_file=output_path,
    )


def _run_in_docker(
    engine: str,
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str,
    max_budget_usd: float,
    max_turns: int,
    json_schema: str | None,
    safe_outputs_file: str,
) -> dict:
    """Run agent inside a Docker container (production path)."""
    ensure_agent_image()
    result = run_agent_in_container(
        engine=engine,
        repo_path=repo_path,
        prompt=prompt,
        context_doc=context_doc,
        safe_outputs_file=safe_outputs_file,
        allowed_tools=allowed_tools,
        max_budget_usd=max_budget_usd,
        max_turns=max_turns,
        json_schema=json_schema,
    )
    result["safe_outputs_file"] = safe_outputs_file
    return result


def _run_subprocess(
    engine: str,
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str,
    max_budget_usd: float,
    max_turns: int,
    json_schema: str | None,
    mcp_config_path: str | None,
    safe_outputs_file: str,
) -> dict:
    """Run agent as a direct subprocess (local dev path)."""
    # Generate MCP config pointing to our safe-outputs server
    mcp_config = create_mcp_config(safe_outputs_file)

    # If caller also provided an MCP config, we use ours (safe-outputs
    # takes priority; the caller's config can be merged in the future)
    effective_mcp_config = mcp_config_path or mcp_config

    try:
        if engine == "claude":
            result = run_claude_code(
                repo_path=repo_path,
                prompt=prompt,
                context_doc=context_doc,
                allowed_tools=allowed_tools,
                max_budget_usd=max_budget_usd,
                max_turns=max_turns,
                json_schema=json_schema,
                mcp_config_path=effective_mcp_config,
            )
        elif engine == "copilot":
            result = run_copilot_cli(
                repo_path=repo_path,
                prompt=prompt,
                context_doc=context_doc,
                allowed_tools=allowed_tools,
                max_budget_usd=max_budget_usd,
                max_turns=max_turns,
                json_schema=json_schema,
                mcp_config_path=effective_mcp_config,
            )
        else:
            raise ValueError(f"Unknown engine: {engine!r}.  Use 'claude' or 'copilot'.")

        result["safe_outputs_file"] = safe_outputs_file
        return result

    finally:
        # Clean up MCP config (but NOT the outputs file — orchestrator needs it)
        Path(mcp_config).unlink(missing_ok=True)
