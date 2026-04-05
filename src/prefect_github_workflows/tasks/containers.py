"""Run agent CLIs inside Docker containers.

Provides OS-level isolation for agent subprocesses:
  - Filesystem: only the cloned repo (read-only) and outputs dir are visible
  - Environment: only the engine's own auth token is injected
  - Process: agent cannot see/signal the orchestrator or other agents
  - Network: default Docker bridge (egress-only, no inbound listeners)

When ``use_docker=False`` in the orchestrator, this module is not used and
execution falls back to direct subprocess calls (for local development).
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from prefect_github_workflows.secrets import get_secret
from prefect_github_workflows.tasks.copilot import parse_copilot_jsonl

AGENT_IMAGE = "prefect-github-workflows-agent:latest"

# Fixed paths inside the container
_WS = "/workspace"
_CTX = "/inputs/context.md"
_MCP_CFG = "/inputs/mcp_config.json"
_OUTPUTS = "/outputs/safe_outputs.jsonl"
_MCP_SERVER = "/app/safe_outputs_server.py"


# ── Helpers ────────────────────────────────────────────────────────────


def _write_container_mcp_config() -> str:
    """Write a temp MCP config file with container-internal paths.

    Returns the host path of the temp file (to bind-mount into the container).
    """
    config = {
        "mcpServers": {
            "safe-outputs": {
                "command": "python",
                "args": [_MCP_SERVER, _OUTPUTS],
            }
        }
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="mcp_cfg_",
        delete=False,
    ) as f:
        json.dump(config, f)
        return f.name


def _write_context_file(context_doc: str) -> str:
    """Write context doc to a temp file and return the host path."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="ctx_",
        delete=False,
    ) as f:
        f.write("# Repository Context (pre-computed, do not re-scan the repo)\n\n")
        f.write(context_doc[:400_000])
        return f.name


def _docker_run(
    cmd: list[str],
    env: dict[str, str],
    mounts: list[tuple[str, str, str]],
    stdin: str | None = None,
    timeout: int = 580,
    image: str = AGENT_IMAGE,
) -> subprocess.CompletedProcess[str]:
    """Execute ``docker run`` with the given mounts and env.

    Parameters
    ----------
    cmd:
        Command + args to run inside the container.
    env:
        Environment variables to inject (each becomes ``-e K=V``).
    mounts:
        List of ``(host_path, container_path, mode)`` tuples.
        mode is ``"ro"`` or ``"rw"``.
    stdin:
        Optional string to pipe to the container's stdin.
    """
    docker_cmd: list[str] = [
        "docker",
        "run",
        "--rm",
        "--init",
    ]

    for key, value in env.items():
        docker_cmd.extend(["-e", f"{key}={value}"])

    for host_path, container_path, mode in mounts:
        docker_cmd.extend(["-v", f"{host_path}:{container_path}:{mode}"])

    if stdin is not None:
        docker_cmd.append("-i")

    docker_cmd.append(image)
    docker_cmd.extend(cmd)

    return subprocess.run(
        docker_cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ── Engine-specific builders ───────────────────────────────────────────


def _build_claude_cmd(
    allowed_tools: str,
    max_budget_usd: float,
    max_turns: int,
    json_schema: str | None,
) -> list[str]:
    """Build the ``claude`` CLI command for container execution."""
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--disable-slash-commands",
        "--no-chrome",
        "--append-system-prompt-file",
        _CTX,
        "--max-turns",
        str(max_turns),
    ]
    if max_budget_usd > 0:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    if allowed_tools:
        cmd.extend(["--allowed-tools", allowed_tools])
    if json_schema:
        cmd.extend(["--json-schema", json_schema])
    # MCP safe-outputs
    cmd.extend(["--mcp-config", _MCP_CFG])
    cmd.extend(["--allowed-tools", "mcp__safe-outputs"])
    return cmd


def _build_claude_env(model: str, max_budget_usd: float) -> dict[str, str]:
    """Build env vars for Claude container."""
    tool_timeout_ms = str(min(int(max_budget_usd * 60_000), 300_000))
    env: dict[str, str] = {
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
        env["ANTHROPIC_API_KEY"] = api_key
    return env


def _build_copilot_cmd(
    prompt: str,
    allowed_tools: str,
    max_turns: int,
    json_schema: str | None,
    model: str,
) -> list[str]:
    """Build the ``gh copilot`` CLI command for container execution."""
    full_prompt = (
        f"System context (read this first, it describes the repo you are "
        f"working in — the context file has full details):\n"
        f"Context file: {_CTX}\n\n"
        f"Task:\n{prompt}"
    )
    cmd = [
        "gh",
        "copilot",
        "--",
        "-p",
        full_prompt,
        "--output-format",
        "json",
        "--allow-all",
        "--no-ask-user",
        "--silent",
        "--model",
        model,
    ]
    if allowed_tools:
        for tool_name in (t.strip() for t in allowed_tools.split(",")):
            if tool_name:
                cmd.extend(["--allow-tool", tool_name])
    # MCP safe-outputs
    cmd.extend(["--additional-mcp-config", f"@{_MCP_CFG}"])
    cmd.extend(["--allow-tool", "safe-outputs"])
    return cmd


def _build_copilot_env(model: str) -> dict[str, str]:
    """Build env vars for Copilot container."""
    env: dict[str, str] = {
        "COPILOT_MODEL": model,
        "COPILOT_AGENT_RUNNER_TYPE": "STANDALONE",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_BUG_COMMAND": "1",
    }
    gh_token = get_secret("copilot-github-token")
    if gh_token:
        env["COPILOT_GITHUB_TOKEN"] = gh_token
    return env


# ── Public API ─────────────────────────────────────────────────────────


def ensure_agent_image(image: str = AGENT_IMAGE) -> None:
    """Raise if the agent Docker image is not available locally."""
    if not shutil.which("docker"):
        msg = "docker CLI not found on PATH. Install Docker or use use_docker=False for local dev."
        raise RuntimeError(msg)
    cp = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        timeout=10,
    )
    if cp.returncode != 0:
        msg = (
            f"Agent image {image!r} not found. "
            f"Build it with: docker build -f Dockerfile.agent -t {image} ."
        )
        raise RuntimeError(msg)


def run_agent_in_container(
    engine: str,
    repo_path: str,
    prompt: str,
    context_doc: str,
    safe_outputs_file: str,
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    model: str | None = None,
    image: str = AGENT_IMAGE,
) -> dict:
    """Run an agent engine inside a Docker container.

    The container gets:
      - The cloned repo at /workspace (read-only)
      - A context document at /inputs/context.md (read-only)
      - The MCP config at /inputs/mcp_config.json (read-only)
      - The safe-outputs JSONL at /outputs/safe_outputs.jsonl (read-write)
      - Only the engine's own auth token as an env var

    Returns the same result dict shape as the direct subprocess functions.
    """
    # Resolve defaults
    if engine == "claude":
        model = model or "claude-sonnet-4-5-20250929"
    elif engine == "copilot":
        model = model or "gpt-4.1"
    else:
        msg = f"Unknown engine: {engine!r}.  Use 'claude' or 'copilot'."
        raise ValueError(msg)

    # Write temp files on the host to bind-mount
    ctx_file = _write_context_file(context_doc)
    mcp_cfg_file = _write_container_mcp_config()

    try:
        # Bind mounts: (host_path, container_path, mode)
        mounts = [
            (repo_path, _WS, "ro"),
            (ctx_file, _CTX, "ro"),
            (mcp_cfg_file, _MCP_CFG, "ro"),
            (safe_outputs_file, _OUTPUTS, "rw"),
        ]

        if engine == "claude":
            cmd = _build_claude_cmd(allowed_tools, max_budget_usd, max_turns, json_schema)
            env = _build_claude_env(model, max_budget_usd)
            stdin = prompt
        else:
            cmd = _build_copilot_cmd(prompt, allowed_tools, max_turns, json_schema, model)
            env = _build_copilot_env(model)
            stdin = None

        print(f"Running {engine} in container: model={model}, image={image}, turns={max_turns}")

        result = _docker_run(
            cmd=cmd,
            env=env,
            mounts=mounts,
            stdin=stdin,
            image=image,
        )

        # ── Parse output (same logic as direct subprocess path) ───────
        if engine == "claude":
            return _parse_claude_result(result, model, json_schema)
        return _parse_copilot_result(result, model, json_schema)

    finally:
        Path(ctx_file).unlink(missing_ok=True)
        Path(mcp_cfg_file).unlink(missing_ok=True)


def _parse_claude_result(
    result: subprocess.CompletedProcess[str],
    model: str,
    json_schema: str | None,
) -> dict:
    """Parse Claude CLI output from a container run."""
    if result.returncode != 0:
        stderr_preview = result.stderr[:1000] if result.stderr else "no stderr"
        raise RuntimeError(f"Claude Code exited {result.returncode}: {stderr_preview}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = {"result": result.stdout}

    result_text = output.get("result", result.stdout)

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


def _parse_copilot_result(
    result: subprocess.CompletedProcess[str],
    model: str,
    json_schema: str | None,
) -> dict:
    """Parse Copilot CLI JSONL output from a container run."""
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

    structured_output = None
    if json_schema and parsed["content"]:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            structured_output = json.loads(parsed["content"])

    return {
        "engine": "copilot",
        "model": model,
        "result": parsed["content"],
        "structured_output": structured_output,
        "exit_code": 0,
        "cost_usd": None,
        "session_id": parsed["session_id"],
        "num_turns": parsed["num_turns"],
        "duration_ms": parsed["duration_ms"],
        "stderr": result.stderr[:1000] if result.stderr else None,
    }
