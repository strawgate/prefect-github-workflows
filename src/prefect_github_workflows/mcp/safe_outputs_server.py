"""Safe-outputs MCP server.

A lightweight stdio MCP server that exposes GitHub-like tools (create_issue,
add_comment, create_review, etc.) but never actually talks to GitHub.  Each
tool call is recorded as a JSON line in an output file.  The orchestrator
reads that file after the agent finishes and decides what to execute.

Usage (by the orchestrator — not run directly):
    python -m prefect_github_workflows.mcp.safe_outputs_server /tmp/outputs.jsonl

Both Claude Code (--mcp-config) and Copilot CLI (--additional-mcp-config)
can launch this as a stdio MCP server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Output file path (passed as first CLI argument) ────────────────────
_output_path: Path | None = None


def _record(action: str, payload: dict) -> str:
    """Append a JSON line to the output file and return a confirmation."""
    if _output_path is None:
        return "ERROR: no output file configured"
    with _output_path.open("a") as f:
        f.write(json.dumps({"action": action, **payload}) + "\n")
    return f"Recorded: {action}"


# ── MCP Server ─────────────────────────────────────────────────────────
server = Server("safe-outputs")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_issue",
            description=(
                "Create a GitHub issue in the target repository. "
                "Use this to report findings, suggest improvements, or flag problems."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Issue title (concise, descriptive)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body in GitHub-flavored Markdown",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply (e.g. ['bug', 'documentation'])",
                        "default": [],
                    },
                },
                "required": ["title", "body"],
            },
        ),
        Tool(
            name="add_issue_comment",
            description="Add a comment to an existing GitHub issue or pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_number": {
                        "type": "integer",
                        "description": "The issue or PR number to comment on",
                    },
                    "body": {
                        "type": "string",
                        "description": "Comment body in GitHub-flavored Markdown",
                    },
                },
                "required": ["issue_number", "body"],
            },
        ),
        Tool(
            name="create_pull_request_review",
            description=(
                "Submit a review on a pull request. "
                "Use event='COMMENT' for general feedback, "
                "'REQUEST_CHANGES' for blocking issues, "
                "'APPROVE' to approve."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pr_number": {
                        "type": "integer",
                        "description": "The pull request number",
                    },
                    "body": {
                        "type": "string",
                        "description": "Review summary in Markdown",
                    },
                    "event": {
                        "type": "string",
                        "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                        "description": "Review action",
                    },
                    "comments": {
                        "type": "array",
                        "description": "Inline review comments",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "File path relative to repo root",
                                },
                                "line": {
                                    "type": "integer",
                                    "description": "Line number in the diff",
                                },
                                "body": {
                                    "type": "string",
                                    "description": "Comment text",
                                },
                            },
                            "required": ["path", "line", "body"],
                        },
                        "default": [],
                    },
                },
                "required": ["pr_number", "body", "event"],
            },
        ),
        Tool(
            name="create_pull_request",
            description=(
                "Create a pull request. The agent should have already "
                "committed and pushed changes to a branch."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "PR title",
                    },
                    "body": {
                        "type": "string",
                        "description": "PR description in Markdown",
                    },
                    "head": {
                        "type": "string",
                        "description": "Branch name with the changes",
                    },
                    "base": {
                        "type": "string",
                        "description": "Target branch (e.g. 'main')",
                        "default": "main",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply",
                        "default": [],
                    },
                },
                "required": ["title", "body", "head"],
            },
        ),
        Tool(
            name="add_label",
            description="Add labels to an existing issue or pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue or PR number",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to add",
                    },
                },
                "required": ["issue_number", "labels"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    result = _record(name, arguments)
    return [TextContent(type="text", text=result)]


async def main() -> None:
    global _output_path  # noqa: PLW0603
    if len(sys.argv) < 2:
        print(
            "Usage: python -m prefect_github_workflows.mcp.safe_outputs_server <output.jsonl>",
            file=sys.stderr,
        )
        sys.exit(1)
    _output_path = Path(sys.argv[1])
    # Ensure the file exists (empty)
    _output_path.touch()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
