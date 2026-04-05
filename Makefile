.PHONY: setup build build-agent deploy deploy-workpool worker run lint fmt typecheck test clean help

IMAGE       := prefect-github-workflows:latest
AGENT_IMAGE := prefect-github-workflows-agent:latest
POOL  := github-workflows-pool
SRC   := src/prefect_github_workflows

# ── First-time setup ─────────────────────────────────────────────────

setup: ## Install project and dev deps with uv
	uv sync --all-extras
	@echo "Run 'python scripts/setup_secrets.py' to configure Prefect secrets."

# ── Docker ────────────────────────────────────────────────────────────

build: ## Build the worker Docker image
	docker build -t $(IMAGE) .

build-agent: ## Build the agent sandbox Docker image
	docker build -f Dockerfile.agent -t $(AGENT_IMAGE) .

# ── Deployment ────────────────────────────────────────────────────────

deploy: ## Deploy all profiles via serve() (dev mode, runs in-process)
	uv run python deploy.py

deploy-workpool: ## Deploy all profiles to Docker work pool (production)
	uv run python scripts/deploy_to_workpool.py

# ── Worker ────────────────────────────────────────────────────────────

worker: ## Start the Prefect worker (polls Cloud, spawns Docker containers)
	prefect worker start --pool $(POOL) --type docker

worker-compose: ## Start worker via Docker Compose
	docker compose up -d

# ── Ad-hoc runs ───────────────────────────────────────────────────────

run: ## Run a quick security audit against fastmcp (example)
	prefect deployment run 'prefect-github-workflows/security-audit' \
		--param repo_url=https://github.com/jlowin/fastmcp

run-custom: ## Run a custom prompt (set REPO and PROMPT env vars)
	prefect deployment run 'prefect-github-workflows/custom' \
		--param repo_url=$(REPO) \
		--param prompt="$(PROMPT)"

# ── Quality ───────────────────────────────────────────────────────────

lint: ## Lint with ruff
	uv run ruff check $(SRC) deploy.py scripts/ tests/
	uv run ruff format --check $(SRC) deploy.py scripts/ tests/

fmt: ## Auto-format with ruff
	uv run ruff check --fix $(SRC) deploy.py scripts/ tests/
	uv run ruff format $(SRC) deploy.py scripts/ tests/

typecheck: ## Type-check with ty
	uv run ty check $(SRC)

test: ## Run tests with pytest
	uv run pytest

check: lint typecheck test ## Run all checks (lint + typecheck + test)

clean: ## Remove cached repos and temp files
	rm -rf /tmp/repos/*
	find . -type d -name __pycache__ -exec rm -rf {} +

help: ## Show this help
	@grep -E '^[a-z_-]+:.*## ' Makefile | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
