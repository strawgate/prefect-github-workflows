"""GitHub Copilot CLI headless execution task.

Uses the Copilot CLI's `-p` (non-interactive prompt) mode with
`--output-format json` for structured output, mirroring the Claude Code
task's interface so the orchestrator can treat both engines uniformly.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from prefect_github_workflows.secrets import get_secret
from prefect_github_workflows.tasks.copilot_auth_proxy import start_auth_proxy
from prefect_github_workflows.tasks.sandbox_env import build_sandbox_env


def _check_copilot_available() -> str | None:
    """Return an error message if Copilot CLI is unavailable, else ``None``."""
    if not shutil.which("gh"):
        return "gh CLI not found on PATH"
    try:
        cp = subprocess.run(
            ["gh", "copilot", "--", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if cp.returncode != 0:
            return (
                "gh copilot not available. "
                "Upgrade gh or install: gh extension install github/gh-copilot"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "Failed to check gh copilot availability"
    return None


def parse_copilot_jsonl(stdout: str) -> dict:
    """Parse Copilot CLI JSONL stream into a structured result dict.

    Event types:
      assistant.message  → data.content (full response text)
      assistant.turn_end → marks end of a turn
      result             → sessionId, exitCode, usage stats
    """
    agent_messages: list[str] = []
    session_id = None
    num_turns = 0
    usage: dict = {}

    for raw_line in stdout.splitlines():
        stripped = raw_line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        with contextlib.suppress(json.JSONDecodeError):
            event = json.loads(stripped)
            event_type = event.get("type", "")

            if event_type == "assistant.message":
                content = (event.get("data") or {}).get("content", "")
                if content:
                    agent_messages.append(content)
            elif event_type == "result":
                session_id = event.get("sessionId")
                usage = event.get("usage") or {}
            elif event_type == "assistant.turn_end":
                num_turns += 1

    return {
        "content": "\n\n".join(agent_messages) if agent_messages else stdout.strip(),
        "session_id": session_id,
        "num_turns": num_turns or None,
        "duration_ms": usage.get("sessionDurationMs"),
        "api_duration_ms": usage.get("totalApiDurationMs"),
        "premium_requests": usage.get("premiumRequests"),
    }


def _build_copilot_env(model: str, proxy_port: int) -> dict[str, str]:
    """Build a sandboxed environment dict for the Copilot CLI subprocess.

    Uses the auth proxy instead of passing the real token.  The proxy
    injects the Bearer token on the upstream side, so the agent only
    sees ``COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:{port}``
    with no API key.

    Only allowlisted system vars plus Copilot-specific vars are included.
    Sensitive tokens (ANTHROPIC_API_KEY, GITHUB_WRITE_TOKEN, etc.) are
    explicitly excluded.
    """
    extras: dict[str, str] = {
        "COPILOT_MODEL": model,
        "COPILOT_PROVIDER_BASE_URL": f"http://127.0.0.1:{proxy_port}",
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_AGENT_RUNNER_TYPE": "STANDALONE",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_BUG_COMMAND": "1",
    }
    return build_sandbox_env(extras)


def run_copilot_cli(
    repo_path: str,
    prompt: str,
    context_doc: str,
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    mcp_config_path: str | None = None,
    model: str = "gpt-4.1",
) -> dict:
    """
    Run GitHub Copilot CLI in non-interactive (headless) mode.

    Uses -p for non-interactive execution, --allow-all to bypass all prompts,
    --no-ask-user for fully autonomous operation, and --output-format json
    for structured output.

    Returns a dict matching the Claude task's output shape so the orchestrator
    can treat both engines uniformly.
    """
    err = _check_copilot_available()
    if err:
        return _unavailable_result(err)

    # Resolve token and start auth proxy so the agent never sees the PAT
    gh_token = get_secret("copilot-github-token")
    if not gh_token:
        return _unavailable_result("COPILOT_GITHUB_TOKEN not set (check .env or Prefect secrets)")

    proxy_port, stop_proxy = start_auth_proxy(gh_token)

    # Write context to a temp file to pass as system prompt context
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix="ctx_", delete=False) as f:
        f.write("# Repository Context (pre-computed, do not re-scan the repo)\n\n")
        f.write(context_doc[:400_000])
        context_file = f.name

    try:
        cmd = [
            "gh",
            "copilot",
            "--",
            "-p",
            f"System context (read this first, it describes the repo you are "
            f"working in — the context file has full details):\n"
            f"Context file: {context_file}\n\n"
            f"Task:\n{prompt}",
            "--output-format",
            "json",
            "--allow-all",  # No permission prompts
            "--no-ask-user",  # Fully autonomous
            "--silent",  # No banner/stats noise
            "--disable-builtin-mcps",  # Block direct GitHub API access
            "--model",
            model,
        ]

        # Tool restrictions
        if allowed_tools:
            for tool_name in (t.strip() for t in allowed_tools.split(",")):
                if tool_name:
                    cmd.extend(["--allow-tool", tool_name])

        # MCP server config (safe-outputs server)
        if mcp_config_path:
            cmd.extend(["--additional-mcp-config", f"@{mcp_config_path}"])
            # Allow the safe-outputs MCP server tools
            cmd.extend(["--allow-tool", "safe-outputs"])

        # Resolve GitHub token — routed through local auth proxy (no PAT in env)
        env = _build_copilot_env(model, proxy_port)

        print(f"Running Copilot CLI: model={model}, tools={allowed_tools}, turns={max_turns}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=580,
            env=env,
        )

        if result.returncode != 0:
            stderr_preview = result.stderr[:1000] if result.stderr else "no stderr"
            return {
                "engine": "copilot",
                "model": model,
                "result": f"Copilot exited {result.returncode}: {stderr_preview}",
                "structured_output": None,
                "exit_code": result.returncode,
                "stderr": stderr_preview,
                "cost_usd": None,
                "session_id": None,
                "num_turns": None,
            }

        parsed = parse_copilot_jsonl(result.stdout)

        # Parse structured output if json_schema was requested
        structured_output = None
        if json_schema and parsed["content"]:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                structured_output = json.loads(parsed["content"])

        return {
            "engine": "copilot",
            "model": model,
            "result": parsed["content"],
            "structured_output": structured_output,
            "exit_code": result.returncode,
            "cost_usd": None,  # Copilot CLI uses premium requests, not USD
            "session_id": parsed["session_id"],
            "num_turns": parsed["num_turns"],
            "duration_ms": parsed["duration_ms"],
            "api_duration_ms": parsed["api_duration_ms"],
            "premium_requests": parsed["premium_requests"],
        }
    finally:
        stop_proxy()
        Path(context_file).unlink(missing_ok=True)


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
