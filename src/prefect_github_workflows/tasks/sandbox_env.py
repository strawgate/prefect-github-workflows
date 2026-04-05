"""Build a minimal, allowlisted environment for agent subprocesses.

Agents are sandboxed: they must NOT see tokens they don't need.
In particular, ``GITHUB_WRITE_TOKEN`` (used only by the orchestrator to
execute safe-outputs) must never leak to the agent.  Similarly, each
engine should only receive its own authentication credential.

The allowlist covers the minimal set of system variables that CLIs
need to function (locale, PATH, HOME, TLS, XDG, temp dirs).
"""

from __future__ import annotations

import os

# System env vars that are safe (and often required) for subprocesses.
_SYSTEM_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Identity / shell basics
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "PATH",
        "TMPDIR",
        "TEMP",
        "TMP",
        # Locale
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_COLLATE",
        # XDG standard dirs (config, cache, data, state)
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        # TLS certificate paths (needed for HTTPS calls)
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        # Container / CI hints
        "CI",
        "CODESPACES",
        "GITHUB_ACTIONS",
        # Proxy (agent may need to reach APIs through corporate proxy)
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        # Terminal / color
        "NO_COLOR",
        "FORCE_COLOR",
        "COLORTERM",
        "TERM_PROGRAM",
    }
)


def build_sandbox_env(extras: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal env dict with only allowlisted system variables.

    Parameters
    ----------
    extras:
        Engine-specific variables to inject (e.g. ``ANTHROPIC_API_KEY``).
        These are merged on top of the allowlisted system vars.
    """
    env: dict[str, str] = {}
    for key in _SYSTEM_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val

    if extras:
        env.update(extras)

    return env
