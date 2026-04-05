"""Git clone/fetch task with local filesystem caching."""

from __future__ import annotations

import subprocess
from pathlib import Path

from prefect import task

from prefect_github_workflows.secrets import get_secret


@task(retries=2, retry_delay_seconds=5, timeout_seconds=120)
def clone_repo(repo_url: str, ref: str = "HEAD") -> tuple[str, str]:
    """
    Clone or update a repository and return (repo_path, commit_hash).

    Uses a persistent /tmp/repos cache — git-fetch is much faster than
    a fresh clone.  The Docker Compose volume mount keeps this across runs.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = Path("/tmp/repos") / repo_name

    # Build clone URL with token if available
    clone_url = repo_url
    token = get_secret("github-clone-token")
    if token and "github.com" in repo_url:
        clone_url = repo_url.replace(
            "https://github.com", f"https://x-access-token:{token}@github.com"
        )

    if (repo_path / ".git").exists():
        print(f"Updating existing clone: {repo_path}")
        subprocess.run(
            ["git", "fetch", "--all", "--prune"],
            cwd=repo_path,
            check=True,
            timeout=60,
        )
        subprocess.run(
            ["git", "reset", "--hard", f"origin/{_default_branch(str(repo_path))}"],
            cwd=repo_path,
            check=True,
            timeout=30,
        )
    else:
        print(f"Fresh clone: {repo_url} → {repo_path}")
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth=50", clone_url, str(repo_path)],
            check=True,
            timeout=90,
        )

    # Resolve commit hash
    commit_hash = (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            timeout=5,
        )
        .decode()
        .strip()
    )

    print(f"Repo ready: {repo_name} @ {commit_hash[:12]}")
    return str(repo_path), commit_hash


def _default_branch(repo_path: str) -> str:
    """Detect the default branch name (main or master)."""
    try:
        result = (
            subprocess.check_output(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return result.split("/")[-1]
    except subprocess.CalledProcessError:
        return "main"
