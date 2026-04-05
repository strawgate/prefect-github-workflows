# prefect-github-workflows

Run AI agent audits against any GitHub repository on a schedule. Claude Code and GitHub Copilot CLI analyze your codebase for security issues, bugs, stale docs, test gaps, and more — orchestrated by Prefect Cloud.

Results are published as Prefect artifacts and optionally posted back to GitHub as issues or PR reviews.

## How it works

1. **Clone** the target repo (cached locally so repeated runs are fast)
2. **Generate context** — file tree, compressed source, git log, dependency manifest
3. **Dispatch** to one or both AI agents with a focused prompt
4. **Collect outputs** — agents record actions (create issue, add comment, etc.) to a safe-outputs file
5. **Execute** — the orchestrator applies those actions to GitHub after the agent finishes
6. **Publish** — results appear as Prefect Cloud artifacts

Agents never get write tokens. They run in sandboxed environments (Docker containers in production) with read-only repo access and a fake MCP server that records their intended actions.

## Prerequisites

- Python ≥ 3.12
- [Prefect Cloud](https://app.prefect.cloud) account
- Docker (for production; optional for local dev)
- API keys: Anthropic (for Claude), GitHub PAT (for Copilot), and optionally a write-scoped PAT for posting results

## Quick start

```bash
# Install
git clone https://github.com/strawgate/prefect-github-workflows.git
cd prefect-github-workflows
make setup          # installs with uv

# Configure secrets (interactive)
python scripts/setup_secrets.py

# Or use environment variables
export ANTHROPIC_API_KEY=sk-...
export COPILOT_GITHUB_TOKEN=ghp_...
export GITHUB_CLONE_TOKEN=ghp_...      # optional, for private repos
export GITHUB_WRITE_TOKEN=ghp_...      # optional, for posting issues/reviews

# Deploy and run locally
make deploy         # starts Prefect serve() with all profiles
```

## Running audits

```bash
# Trigger a built-in profile
prefect deployment run 'prefect-github-workflows/security-audit' \
  --param repo_url=https://github.com/jlowin/fastmcp

# Custom prompt
prefect deployment run 'prefect-github-workflows/custom' \
  --param repo_url=https://github.com/jlowin/fastmcp \
  --param prompt="Find all uses of eval() and assess risk"

# Batch audit from Python
from prefect.deployments import run_deployment
for repo in ['org/repo1', 'org/repo2']:
    run_deployment(
        'prefect-github-workflows/security-audit',
        parameters={'repo_url': f'https://github.com/{repo}'},
        timeout=0,
    )
```

## Prompt library

16 built-in audit profiles, each with calibrated budgets and turn limits:

| Profile | Engine | What it checks |
|---------|--------|---------------|
| security-audit | both | Injection, auth, crypto, dependency vulnerabilities |
| secrets-scan | claude | Hardcoded secrets, API keys, leaked credentials |
| bug-hunt | both | Logic errors, null handling, edge cases |
| code-review | both | Style, patterns, naming, complexity |
| perf-review | claude | Hot paths, I/O patterns, allocations |
| docs-review | both | README accuracy, API docs, stale content |
| api-docs-audit | claude | Public API surface documentation |
| test-coverage-audit | both | Untested modules and missing scenarios |
| test-quality | claude | Mocking practices, flakiness, assertions |
| architecture-review | both | Coupling, cohesion, module boundaries |
| dependency-audit | claude | Outdated, unmaintained, duplicate deps |
| ci-review | claude | Pipeline efficiency, caching, security |
| dockerfile-review | claude | Base images, layer optimization, security |
| rust-audit | claude | Unsafe code, error handling, performance |
| python-audit | claude | Typing, async patterns, packaging |
| custom | both | Your own prompt |

Add new profiles in `src/prefect_github_workflows/prompts/library.py` and re-run `make deploy`.

## Production deployment

```bash
# Build images
make build          # orchestrator image
make build-agent    # agent sandbox image

# Deploy to Prefect Cloud work pool
make deploy-workpool

# Start the worker
make worker
```

See [DEVELOPING.md](DEVELOPING.md) for full build, test, and contribution instructions.
