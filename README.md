# prefect-github-workflows

Prefect Cloud–orchestrated AI agent sandbox for running Claude Code and GitHub Copilot CLI
against arbitrary GitHub repositories on a schedule, with shared cached context.

## Architecture

```
Prefect Cloud (schedules, secrets, artifacts, UI)
        │
        ▼
  Docker Worker (polls for runs)
        │
        ▼
  ┌─────────────────────────────────────────┐
  │  Flow Run Container                     │
  │                                         │
  │  1. git clone / fetch                   │
  │  2. generate repo context (cached by    │
  │     commit hash — shared across runs)   │
  │  3. fan out to agent(s):                │
  │     ├─ Claude Code CLI (--print)        │
  │     └─ Copilot CLI (-p --allow-all)     │
  │  4. aggregate results → artifacts       │
  └─────────────────────────────────────────┘
```

## Prerequisites

- Prefect Cloud account (https://app.prefect.cloud)
- Docker on the worker host
- API keys: Anthropic, GitHub PAT (read-only), Copilot-scoped PAT
- (Optional) S3 bucket for cross-run result persistence

## Quick start

```bash
# 1. Install Prefect and authenticate
pip install prefect prefect-docker
prefect cloud login

# 2. Create secrets in Prefect Cloud
python scripts/setup_secrets.py

# 3. Create Docker work pool (or do it in the UI)
prefect work-pool create --type docker github-workflows-pool

# 4. Build the worker image
docker build -t prefect-github-workflows:latest .

# 5. Deploy all prompt profiles
python deploy.py

# 6. Start the worker
prefect worker start --pool github-workflows-pool --type docker
```

## Running audits

```bash
# Trigger a specific profile against a repo
prefect deployment run 'prefect-github-workflows/security-audit' \
  --param repo_url=https://github.com/jlowin/fastmcp

# Run with a custom prompt (uses the "custom" deployment)
prefect deployment run 'prefect-github-workflows/custom' \
  --param repo_url=https://github.com/jlowin/fastmcp \
  --param prompt="Find all uses of eval() and assess risk"

# Batch audit from the Python SDK
python -c "
from prefect.deployments import run_deployment
for repo in ['org/repo1', 'org/repo2']:
    run_deployment('prefect-github-workflows/security-audit',
                   parameters={'repo_url': f'https://github.com/{repo}'},
                   timeout=0)
"
```

## Prompt library

See `src/prefect_github_workflows/prompts/library.py` for all built-in audit profiles. Each profile specifies:

- `name`: deployment name and artifact key prefix
- `prompt`: the natural-language instruction
- `allowed_tools`: Claude Code tool restrictions (Copilot gets equivalent mapping)
- `max_budget_usd` / `max_turns`: cost and iteration caps
- `engine`: claude, copilot, or both
- `tags`: for filtering in the Prefect UI
- `cron`: optional default schedule

Add new profiles by appending to `PROMPT_LIBRARY` and re-running `python deploy.py`.

## MCP server configuration

Drop a JSON file at `mcp-config.json` to connect custom MCP servers:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@myorg/mcp-server"],
      "env": { "API_KEY": "${MY_MCP_KEY}" }
    }
  }
}
```

The Dockerfile bakes this in at `/etc/claude/mcp-config.json`. Pass
`--mcp-config` via the flow's `mcp_config_path` parameter to override at runtime.
