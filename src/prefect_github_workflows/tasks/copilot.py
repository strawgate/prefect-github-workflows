"""GitHub Copilot CLI headless execution task.

NOTE: This integration is EXPERIMENTAL. GitHub Copilot does not currently offer
a fully headless agentic CLI comparable to Claude Code's `--print` mode.
The `gh copilot` extension (via GitHub CLI) provides `suggest` and `explain`
subcommands but no autonomous code analysis mode.

This task is a placeholder that will need updating when/if GitHub ships
a headless Copilot agent CLI.  For now, it attempts to run `gh copilot`
and fails gracefully if unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from prefect import task

from prefect_github_workflows.secrets import get_secret


@task(retries=0, retry_delay_seconds=15, timeout_seconds=600)
def run_copilot_cli(
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    mcp_config_path: str | None = None,
    model: str = "gpt-4o",
) -> dict:
    """
    Run GitHub Copilot CLI (experimental / placeholder).

    Currently attempts to use `gh copilot suggest` as a best-effort
    integration.  Returns a structured dict matching the Claude task's
    output shape so the orchestrator can treat both engines uniformly.

    If `gh copilot` is not available, returns an error result rather
    than crashing the flow.
    """
    # Check if gh CLI with copilot extension is available
    gh_path = shutil.which("gh")
    if not gh_path:
        return _unavailable_result("gh CLI not found on PATH")

    # Verify copilot extension is installed
    try:
        ext_check = subprocess.run(
            ["gh", "extension", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "copilot" not in ext_check.stdout.lower():
            return _unavailable_result(
                "gh copilot extension not installed. "
                "Install with: gh extension install github/gh-copilot"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return _unavailable_result("Failed to check gh extensions")

    # Resolve GitHub token
    env = {**os.environ}
    gh_token = get_secret("copilot-github-token")
    if gh_token:
        env["GITHUB_TOKEN"] = gh_token

    # Build prompt with context prefix (truncated — Copilot context is smaller)
    context_prefix = context_doc[:100_000]
    full_prompt = f"Repository context:\n{context_prefix}\n\nTask:\n{prompt}"

    print(f"Running Copilot CLI (experimental): model={model}, turns={max_turns}")

    # Use gh copilot suggest as a best-effort approach
    # This is a placeholder — real headless agentic mode TBD
    try:
        result = subprocess.run(
            ["gh", "copilot", "suggest", "-t", "shell", full_prompt],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=580,
            env=env,
        )

        output_text = result.stdout.strip()

        return {
            "engine": "copilot",
            "model": model,
            "result": output_text or "(no output — Copilot headless mode is experimental)",
            "structured_output": None,
            "exit_code": result.returncode,
            "stderr": result.stderr[:1000] if result.stderr else None,
            "cost_usd": None,
            "session_id": None,
            "num_turns": None,
        }
    except subprocess.TimeoutExpired:
        return _unavailable_result("Copilot CLI timed out")


def _unavailable_result(reason: str) -> dict:
    """Return a graceful error result when Copilot is not available."""
    print(f"Copilot CLI unavailable: {reason}")
    return {
        "engine": "copilot",
        "model": "n/a",
        "result": f"Copilot engine skipped: {reason}",
        "structured_output": None,
        "exit_code": -1,
        "stderr": reason,
        "cost_usd": None,
        "session_id": None,
        "num_turns": None,
    }
