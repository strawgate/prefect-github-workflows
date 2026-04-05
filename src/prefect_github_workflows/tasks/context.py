"""
Repository context generation with commit-hash-keyed caching.

Generates a compressed summary of the repo that is prepended to every agent's
prompt.  Cached by commit hash so it's computed once and shared across all
flow runs targeting the same commit.
"""

from __future__ import annotations

import contextlib
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from prefect import task

if TYPE_CHECKING:
    from prefect.context import TaskRunContext


def _commit_cache_key(_context: TaskRunContext, parameters: dict) -> str:
    """Cache key = commit hash.  Same commit → same context, always."""
    return f"repo-context-{parameters['commit_hash']}"


@task(
    cache_key_fn=_commit_cache_key,
    cache_expiration=timedelta(days=7),
    persist_result=True,
    retries=2,
    retry_delay_seconds=10,
    timeout_seconds=180,
)
def generate_repo_context(repo_path: str, commit_hash: str) -> str:
    """
    Build a tiered context document for the repository.

    Tier 1: File tree + structure (always fits, ~2-5K tokens)
    Tier 2: Compressed source via repomix with Tree-sitter (~30% of original)
    Tier 3: Recent git log for recency signal

    The result is cached by commit_hash — if another flow run asks for
    the same commit, this task returns instantly from cache.
    """
    sections: list[str] = []
    repo_name = Path(repo_path).name

    # ── Header ────────────────────────────────────────────────────────
    sections.append(f"# Repository Context: {repo_name}\n**Commit:** `{commit_hash}`\n")

    # ── Tier 1: File tree ─────────────────────────────────────────────
    tree = _file_tree(repo_path)
    if tree:
        sections.append(f"## File Tree\n\n```\n{tree}\n```")

    # ── Tier 2: Compressed source via repomix ─────────────────────────
    compressed = _repomix_compress(repo_path)
    if compressed:
        # Budget: ~500K chars ≈ 125K tokens, leaves room for the prompt
        if len(compressed) > 500_000:
            compressed = compressed[:500_000] + "\n\n[... truncated ...]"
        sections.append(f"## Compressed Source\n\n{compressed}")
    else:
        # Fallback: just the file tree + key files
        key_files = _read_key_files(repo_path)
        if key_files:
            sections.append(f"## Key Files\n\n{key_files}")

    # ── Tier 3: Recent git log ────────────────────────────────────────
    git_log = _recent_log(repo_path)
    if git_log:
        sections.append(f"## Recent Commits\n\n```\n{git_log}\n```")

    # ── Tier 4: Dependency manifest ───────────────────────────────────
    deps = _dependency_summary(repo_path)
    if deps:
        sections.append(f"## Dependencies\n\n```\n{deps}\n```")

    context = "\n\n---\n\n".join(sections)
    print(
        f"Context generated: {len(context):,} chars "
        f"(~{len(context) // 4:,} tokens) for {repo_name}@{commit_hash[:8]}"
    )
    return context


# ═══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _file_tree(repo_path: str, max_depth: int = 4) -> str | None:
    """Generate a file tree, excluding noise directories."""
    try:
        result = subprocess.run(
            [
                "find",
                ".",
                "-maxdepth",
                str(max_depth),
                "-not",
                "-path",
                "./.git/*",
                "-not",
                "-path",
                "./node_modules/*",
                "-not",
                "-path",
                "./.venv/*",
                "-not",
                "-path",
                "./target/*",
                "-not",
                "-path",
                "./__pycache__/*",
                "-not",
                "-path",
                "./dist/*",
                "-not",
                "-name",
                "*.pyc",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            lines = sorted(result.stdout.strip().split("\n"))
            return "\n".join(lines[:500])  # Cap at 500 entries
    except Exception:
        return None
    return None


def _repomix_compress(repo_path: str) -> str | None:
    """Use repomix --compress for Tree-sitter-based token reduction."""
    try:
        result = subprocess.run(
            [
                "npx",
                "repomix",
                "--compress",
                "--style",
                "markdown",
                "--stdout",
                "--ignore",
                ",".join(
                    [
                        "*.test.*",
                        "*.spec.*",
                        "*.lock",
                        "package-lock.json",
                        "node_modules/**",
                        "dist/**",
                        ".git/**",
                        "target/**",
                        "__pycache__/**",
                        ".venv/**",
                        "*.pyc",
                    ]
                ),
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return None


def _read_key_files(repo_path: str) -> str | None:
    """Fallback: read README, config files, entry points."""
    key_patterns = [
        "README.md",
        "README.rst",
        "README",
        "pyproject.toml",
        "Cargo.toml",
        "package.json",
        "go.mod",
        "Makefile",
        "Dockerfile",
        "src/main.rs",
        "src/lib.rs",
        "src/main.py",
        "src/__init__.py",
        "app.py",
        "main.py",
        "src/index.ts",
        "src/index.js",
    ]
    parts: list[str] = []
    for pattern in key_patterns:
        path = Path(repo_path) / pattern
        if path.is_file():
            with contextlib.suppress(OSError):
                content = path.read_text(errors="replace")[:20_000]
                parts.append(f"### {pattern}\n\n```\n{content}\n```")
    return "\n\n".join(parts) if parts else None


def _recent_log(repo_path: str, count: int = 20) -> str | None:
    """Recent git commits for recency context."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{count}", "--no-decorate"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        return None
    return None


def _dependency_summary(repo_path: str) -> str | None:
    """Extract a summary of the dependency manifest."""
    for manifest in [
        "pyproject.toml",
        "requirements.txt",
        "Cargo.toml",
        "package.json",
        "go.mod",
        "Gemfile",
    ]:
        path = Path(repo_path) / manifest
        if path.is_file():
            with contextlib.suppress(OSError):
                content = path.read_text(errors="replace")[:10_000]
                return f"# {manifest}\n{content}"
    return None
