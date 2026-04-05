FROM prefecthq/prefect:3-python3.12

# ── System deps ──────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg && \
    # Node.js 20 (required by Claude Code CLI)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── uv (fast Python package manager) ────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── Claude Code CLI ─────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code@latest

# ── GitHub CLI + Copilot extension (experimental) ────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    gh extension install github/gh-copilot || true

# ── Repomix (repo context generation with Tree-sitter compression) ──
RUN npm install -g repomix@latest

# ── Python project ───────────────────────────────────────────────────
WORKDIR /opt/prefect
COPY pyproject.toml ./
COPY src/ src/
COPY deploy.py ./

# Install with uv (uses system Python from prefect image)
RUN uv pip install --system -e .

# ── MCP config (override at runtime via --mcp-config or volume mount)
COPY mcp-config.json /etc/claude/mcp-config.json

# ── Verify installations ────────────────────────────────────────────
RUN claude --version && \
    gh --version && \
    repomix --version && \
    python -c "import prefect; print(f'prefect {prefect.__version__}')" && \
    python -c "import prefect_github_workflows; print('package OK')"
