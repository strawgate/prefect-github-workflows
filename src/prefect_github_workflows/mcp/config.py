"""Generate MCP config for the safe-outputs server.

Creates a temporary JSON config file that both Claude Code and Copilot CLI
can use to launch our safe-outputs MCP server as a stdio subprocess.
"""

from __future__ import annotations

import json
import sys
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def create_mcp_config(output_file: str | Path) -> str:
    """Create a temp MCP config JSON and return its path.

    The config tells the CLI to launch our safe-outputs server as a stdio
    MCP server, passing the output file path as an argument.
    """
    config = {
        "mcpServers": {
            "safe-outputs": {
                "command": sys.executable,
                "args": [
                    "-m",
                    "prefect_github_workflows.mcp.safe_outputs_server",
                    str(output_file),
                ],
            }
        }
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="mcp_config_",
        delete=False,
    ) as f:
        json.dump(config, f)
        return f.name
