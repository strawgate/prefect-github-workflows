# Agent Instructions

Instructions for AI coding agents working in this repository.

## Quick reference

- **Build & check:** `make check` (runs lint + typecheck + test)
- **Lint:** `make lint` — uses ruff with 40+ rule categories
- **Format:** `make fmt` — auto-format with ruff
- **Test:** `make test` — pytest
- **Structure:** `src/prefect_github_workflows/` — see [DEVELOPING.md](DEVELOPING.md) for layout

## Key files

| Area | Start here |
|------|-----------|
| Flow orchestration | `src/prefect_github_workflows/orchestrator.py` |
| Agent CLI wrappers | `src/prefect_github_workflows/tasks/claude.py`, `tasks/copilot.py` |
| Agent dispatch | `src/prefect_github_workflows/tasks/dispatch.py` |
| Docker isolation | `src/prefect_github_workflows/tasks/containers.py` |
| Safe-outputs MCP | `src/prefect_github_workflows/mcp/safe_outputs_server.py` |
| Output execution | `src/prefect_github_workflows/mcp/execute_outputs.py` |
| Prompt library | `src/prefect_github_workflows/prompts/library.py` |
| Secrets | `src/prefect_github_workflows/secrets.py` |

## Rules

### Architecture invariants

1. **Agents never get write tokens.** The `GITHUB_WRITE_TOKEN` is used only by `execute_outputs.py` in the orchestrator. Never pass it to agent subprocesses or containers.

2. **Agents run sandboxed.** In subprocess mode, `sandbox_env.py` allowlists env vars. In Docker mode, the repo is mounted read-only. Each engine only receives its own auth token.

3. **Safe-outputs is the only way agents produce GitHub actions.** Agents call MCP tools (create_issue, add_comment, etc.) which record to NDJSON. The orchestrator executes them post-run.

4. **Task functions return uniform dicts.** Both `run_claude_code` and `run_copilot_cli` return the same shape: `engine`, `model`, `result`, `structured_output`, `exit_code`/`cost_usd`, `session_id`, `num_turns`.

5. **No nested Prefect tasks.** `dispatch.py` calls engine functions via `.fn()` to avoid nesting. Only `run_agent` has the `@task` decorator.

### Code patterns

- **Secrets:** Always use `get_secret("block-name")`, never read env vars directly for credentials
- **Subprocess env:** Always use `build_sandbox_env(extras)` from `sandbox_env.py`, never `{**os.environ}`
- **Error returns vs exceptions:** CLI wrappers return error dicts (exit_code != 0) for expected failures; raise `RuntimeError` only for unexpected failures
- **Temp files:** Use `tempfile.NamedTemporaryFile(delete=False)` and clean up in `finally` blocks

### Style

- See [CODE_STYLE.md](CODE_STYLE.md) for naming and formatting conventions
- Ruff enforces most rules — run `make lint` before committing
- Line length limit: 100 characters
- Target: Python 3.12+

### What not to do

- Do not add `GITHUB_WRITE_TOKEN` or `GITHUB_CLONE_TOKEN` to agent env dicts
- Do not use `--dangerously-skip-permissions` (old flag) — use `--permission-mode bypassPermissions`
- Do not import from `flows/` — that directory is legacy; all code lives in `src/prefect_github_workflows/`
- Do not add Prefect `@task` decorators inside engine functions (claude.py, copilot.py) — they're called via `.fn()` from dispatch
