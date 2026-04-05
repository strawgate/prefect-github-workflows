# Developing

Build, test, and contribute to prefect-github-workflows.

## Setup

```bash
git clone https://github.com/strawgate/prefect-github-workflows.git
cd prefect-github-workflows
make setup   # installs project + dev deps via uv
```

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/). Docker is needed for production mode but optional for local dev.

## Project structure

```
src/prefect_github_workflows/
├── orchestrator.py          # Main Prefect flow (5 phases)
├── secrets.py               # Secret resolution: Prefect blocks → env vars
├── tasks/
│   ├── clone.py             # Git clone/fetch with /tmp/repos caching
│   ├── context.py           # Tiered repo context generation (repomix)
│   ├── dispatch.py          # Routes to Docker or subprocess execution
│   ├── copilot.py           # Copilot CLI wrapper + JSONL parser
│   ├── claude.py            # Claude Code CLI wrapper
│   ├── reporting.py         # Prefect artifact publishing
│   ├── sandbox_env.py       # Env-var allowlist for subprocess mode
│   └── containers.py        # Docker container runner for agents
├── mcp/
│   ├── safe_outputs_server.py  # Stdio MCP server (records agent actions)
│   ├── execute_outputs.py      # Reads NDJSON → executes against GitHub API
│   └── config.py               # Generates MCP config JSON for CLIs
└── prompts/
    ├── library.py           # 16 audit profiles with shared fragments
    └── registry.py          # AgentProfile dataclass + register()
```

### Flow phases

The orchestrator runs five sequential phases:

1. **Clone** — `clone_repo()` shallow-clones or fetches into `/tmp/repos/<name>`
2. **Context** — `generate_repo_context()` builds a tiered markdown document (file tree, compressed source via repomix, git log, dependency manifest). Cached by commit hash for 7 days.
3. **Dispatch** — `run_agent()` fans out to one or both engines. Each agent gets:
   - The repo (read-only in Docker mode)
   - The context document as a system prompt
   - A safe-outputs MCP server that records tool calls to NDJSON
4. **Execute outputs** — `execute_safe_outputs()` reads the NDJSON file and POSTs to the GitHub REST API using `github-write-token`
5. **Publish** — `publish_results()` creates Prefect Cloud artifacts (markdown report + comparison table)

### Execution modes

| Mode | Flag | How agents run | When to use |
|------|------|---------------|-------------|
| Subprocess | `use_docker=False` (default) | Direct `subprocess.run()` with allowlisted env | Local development |
| Docker | `use_docker=True` | `docker run` with read-only mounts | Production, CI |

In subprocess mode, `sandbox_env.py` filters environment variables so agents only see their own auth token plus safe system vars (PATH, HOME, locale, TLS certs, etc.).

In Docker mode, agents run in an isolated container (`Dockerfile.agent`) with the repo bind-mounted read-only, no access to the host filesystem, and only their engine's auth token injected.

### Safe-outputs pattern

Agents never get GitHub write tokens. Instead:

1. The orchestrator starts an MCP server (`safe_outputs_server.py`) alongside the agent
2. The agent calls tools like `create_issue`, `add_comment`, `create_pull_request_review`
3. These calls are recorded as JSON lines to a temp file — nothing is executed
4. After the agent exits, the orchestrator reads the file and executes actions via the GitHub REST API

This gives the orchestrator full control over what actually gets posted.

## Secrets

Four secrets, resolved via Prefect Cloud blocks first, then environment variables:

| Block name | Env var | Purpose | Required |
|-----------|---------|---------|----------|
| `anthropic-api-key` | `ANTHROPIC_API_KEY` | Claude Code API access | For Claude engine |
| `copilot-github-token` | `COPILOT_GITHUB_TOKEN` | GitHub PAT with Copilot scope | For Copilot engine |
| `github-clone-token` | `GITHUB_CLONE_TOKEN` | GitHub PAT with Contents:read | For private repos |
| `github-write-token` | `GITHUB_WRITE_TOKEN` | GitHub PAT with Issues:write | For posting results |

Interactive setup: `python scripts/setup_secrets.py`

For local dev, create a `.env` file (gitignored):

```bash
ANTHROPIC_API_KEY=sk-...
COPILOT_GITHUB_TOKEN=ghp_...
GITHUB_CLONE_TOKEN=ghp_...
GITHUB_WRITE_TOKEN=ghp_...
```

Then source it: `set -a && source .env && set +a`

## Build commands

```bash
make setup           # Install project + dev deps
make build           # Build orchestrator Docker image
make build-agent     # Build agent sandbox Docker image
make deploy          # Deploy all profiles via serve() (local dev)
make deploy-workpool # Deploy to Prefect Cloud Docker work pool
make worker          # Start Prefect worker
make worker-compose  # Start worker via docker-compose
```

## Quality checks

```bash
make lint            # ruff check + format check
make fmt             # Auto-format with ruff
make typecheck       # Type-check with ty
make test            # Run pytest
make check           # All of the above
```

CI runs lint + typecheck + test on Python 3.12 and 3.13 for every push and PR.

## Adding a new audit profile

1. Open `src/prefect_github_workflows/prompts/library.py`
2. Add a new `AgentProfile(...)` to the `register()` call:

```python
register(
    AgentProfile(
        name="my-new-audit",
        description="Check for XSS vulnerabilities",
        prompt=_build_prompt("Scan for cross-site scripting..."),
        engine="claude",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=3.0,
        max_turns=10,
        tags=["security"],
    ),
)
```

3. Re-deploy: `make deploy` (local) or `make deploy-workpool` (production)

### Shared prompt fragments

Profiles use four shared fragments (defined at the top of `library.py`):

- **RIGOR_FRAGMENT** — instructions for thorough analysis
- **EVIDENCE_STANDARD** — "cite specific files and line numbers"
- **QUALITY_GATE** — "if nothing found, say so rather than inventing issues"
- **SEVERITY_SYSTEM** — Critical / High / Medium / Low definitions

`_build_prompt(task_specific_text)` automatically appends all four.

## Docker images

| Image | Dockerfile | Purpose |
|-------|-----------|---------|
| `prefect-github-workflows:latest` | `Dockerfile` | Orchestrator + Prefect worker |
| `prefect-github-workflows-agent:latest` | `Dockerfile.agent` | Agent sandbox (CLIs + MCP SDK only) |

The agent image is intentionally minimal — no Prefect, no httpx, no orchestrator code. It contains:
- Claude Code CLI (npm)
- GitHub CLI + Copilot extension
- Python 3.12 + MCP SDK
- The safe-outputs MCP server script

## Running locally (no Docker)

```bash
set -a && source .env && set +a

uv run python -c "
from prefect_github_workflows.orchestrator import github_workflow_orchestrator

results = github_workflow_orchestrator(
    repo_url='https://github.com/some/repo',
    prompt='Review this codebase.',
    engine='copilot',
    max_turns=5,
    use_docker=False,  # subprocess mode (default)
)
"
```

## Running with Docker isolation

```bash
make build-agent

uv run python -c "
from prefect_github_workflows.orchestrator import github_workflow_orchestrator

results = github_workflow_orchestrator(
    repo_url='https://github.com/some/repo',
    prompt='Review this codebase.',
    engine='copilot',
    max_turns=5,
    use_docker=True,
)
"
```
