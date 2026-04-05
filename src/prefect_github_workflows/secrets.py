"""Secret resolution: Prefect blocks → environment variables → None.

Allows the project to run with full Prefect Cloud/Server secret blocks,
or locally with plain environment variables (e.g. ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import os

# Mapping from Prefect block name → environment variable name.
_ENV_MAP: dict[str, str] = {
    "anthropic-api-key": "ANTHROPIC_API_KEY",
    "github-clone-token": "GITHUB_CLONE_TOKEN",
    "copilot-github-token": "COPILOT_GITHUB_TOKEN",
    "github-write-token": "GITHUB_WRITE_TOKEN",
}


def get_secret(block_name: str) -> str | None:
    """Resolve a secret by Prefect block name, falling back to env vars.

    Resolution order:
      1. Prefect Secret block (requires a running server or Cloud)
      2. Environment variable (see ``_ENV_MAP``)
      3. ``None``
    """
    # Try Prefect block first
    try:
        from prefect.blocks.system import Secret

        value = Secret.load(block_name).get()
        if value:
            return value
    except Exception:  # any Prefect infra error is non-fatal
        pass

    # Fall back to env var
    env_key = _ENV_MAP.get(block_name)
    if env_key:
        return os.environ.get(env_key)

    return None
