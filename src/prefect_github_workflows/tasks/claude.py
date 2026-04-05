"""Claude Code CLI headless execution task."""

from __future__ import annotations

import contextlib
import json
import subprocess
import tempfile
from pathlib import Path

from prefect import task

from prefect_github_workflows.secrets import get_secret
from prefect_github_workflows.tasks.sandbox_env import build_sandbox_env


@task(retries=1, retry_delay_seconds=15, timeout_seconds=600)
def run_claude_code(
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    mcp_config_path: str | None = None,
    model: str = "claude-sonnet-4-5-20250929",
) -> dict:
    """
    Run Claude Code CLI in non-interactive (headless) mode.

    Uses ``--print`` for non-interactive execution, ``--permission-mode
    bypassPermissions`` to skip all permission prompts, and
    ``--append-system-prompt-file`` to inject the cached repo context.

    The CLI's `--output-format json` returns a JSON object with fields:
      result, cost_usd, total_cost_usd, session_id, num_turns,
      is_error, duration_ms, duration_api_ms

    When --json-schema is used, the `result` field contains the
    JSON-validated structured output.

    Returns a dict with: engine, result, cost_usd, session_id, model, num_turns
    """
    # Write context to a temp file for --append-system-prompt-file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix="ctx_", delete=False) as f:
        f.write("# Repository Context (pre-computed, do not re-scan the repo)\n\n")
        f.write(context_doc[:400_000])  # Leave headroom for the prompt itself
        context_file = f.name

    try:
        cmd = [
            "claude",
            "--print",  # Non-interactive
            "--output-format",
            "json",  # Structured JSON output
            "--permission-mode",
            "bypassPermissions",  # No prompts (headless mode)
            "--disable-slash-commands",  # Security hardening
            "--no-chrome",  # No Chrome integration
            "--append-system-prompt-file",
            context_file,
            "--max-turns",
            str(max_turns),
        ]

        # Budget cap
        if max_budget_usd > 0:
            cmd.extend(["--max-budget-usd", str(max_budget_usd)])

        # Tool restrictions (permission allowlist — listed tools auto-approved)
        if allowed_tools:
            cmd.extend(["--allowed-tools", allowed_tools])

        # Structured output schema
        if json_schema:
            cmd.extend(["--json-schema", json_schema])

        mcp_path = Path(mcp_config_path or "/etc/claude/mcp-config.json")
        if mcp_path.is_file():
            cmd.extend(["--mcp-config", str(mcp_path)])
            # Allow the safe-outputs MCP server tools
            cmd.extend(["--allowed-tools", "mcp__safe-outputs"])

        # Build sandboxed env — only allowlisted system vars plus
        # Claude-specific vars.  Sensitive tokens (COPILOT_GITHUB_TOKEN,
        # GITHUB_WRITE_TOKEN, GITHUB_CLONE_TOKEN, etc.) are excluded.
        tool_timeout_ms = str(min(int(max_budget_usd * 60_000), 300_000))
        extras: dict[str, str] = {
            "ANTHROPIC_MODEL": model,
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "DISABLE_BUG_COMMAND": "1",
            "MCP_TIMEOUT": "30000",
            "BASH_DEFAULT_TIMEOUT_MS": tool_timeout_ms,
            "BASH_MAX_TIMEOUT_MS": tool_timeout_ms,
        }
        api_key = get_secret("anthropic-api-key")
        if api_key:
            extras["ANTHROPIC_API_KEY"] = api_key
        env = build_sandbox_env(extras)

        print(
            f"Running Claude Code: model={model}, budget=${max_budget_usd}, "
            f"tools={allowed_tools}, turns={max_turns}"
        )

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=580,
            env=env,
        )

        if result.returncode != 0:
            stderr_preview = result.stderr[:1000] if result.stderr else "no stderr"
            raise RuntimeError(f"Claude Code exited {result.returncode}: {stderr_preview}")

        # Parse JSON output from --output-format json
        # Expected fields: result, cost_usd, total_cost_usd, session_id,
        #   num_turns, is_error, duration_ms, duration_api_ms
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            # If JSON parsing fails, treat stdout as plain text
            output = {"result": result.stdout}

        result_text = output.get("result", result.stdout)

        # When --json-schema is used, the result field contains validated JSON.
        # Try to parse it so downstream reporting can extract structured findings.
        structured_output = None
        if json_schema and result_text:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                structured_output = json.loads(result_text)

        return {
            "engine": "claude",
            "model": model,
            "result": result_text,
            "structured_output": structured_output,
            "cost_usd": output.get("total_cost_usd") or output.get("cost_usd", 0),
            "session_id": output.get("session_id"),
            "num_turns": output.get("num_turns"),
            "duration_ms": output.get("duration_ms"),
            "is_error": output.get("is_error", False),
        }

    finally:
        Path(context_file).unlink(missing_ok=True)
