"""Result aggregation and Prefect artifact publishing."""

from __future__ import annotations

from prefect import task
from prefect.artifacts import create_markdown_artifact, create_table_artifact


@task(timeout_seconds=60)
def publish_results(
    results: list[dict],
    repo_url: str,
    commit_hash: str,
    prompt: str,
    profile_name: str = "custom",
) -> None:
    """
    Publish agent results as Prefect artifacts.

    GitHub interactions (issues, comments, reviews) are handled by the
    safe-outputs MCP server and execute_outputs — not here.

    Artifacts are versioned by commit hash so you can track how findings
    evolve over time in the Prefect Cloud UI.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1]

    # ── Markdown artifact: narrative report ────────────────────────────
    md = _build_markdown_report(results, repo_url, commit_hash, prompt)
    create_markdown_artifact(
        key=f"{profile_name}-{repo_name}",
        markdown=md,
        description=f"{profile_name} | {repo_name} @ {commit_hash[:8]}",
    )

    # ── Table artifact: engine comparison ─────────────────────────────
    table_data = []
    for r in results:
        table_data.append(
            {
                "Engine": r.get("engine", "?"),
                "Model": r.get("model", "?"),
                "Cost": f"${r['cost_usd']:.4f}" if r.get("cost_usd") else "N/A",
                "Turns": str(r.get("num_turns", "?")),
                "Status": "✅" if r.get("result") else "❌",
                "Output Length": f"{len(r.get('result', '')):,} chars",
            }
        )

    if table_data:
        create_table_artifact(
            key=f"{profile_name}-{repo_name}-comparison",
            table=table_data,
            description=f"Engine comparison: {profile_name} | {repo_name}",
        )

    # ── Structured findings table (if JSON schema was used) ───────────
    all_issues = []
    for r in results:
        structured = r.get("structured_output")
        if isinstance(structured, dict) and "issues" in structured:
            for issue in structured["issues"]:
                all_issues.append(
                    {
                        "Engine": r.get("engine", "?"),
                        "Severity": issue.get("severity", "?"),
                        "Category": issue.get("category", "?"),
                        "File": issue.get("file", "?"),
                        "Description": issue.get("description", "?")[:200],
                    }
                )

    if all_issues:
        create_table_artifact(
            key=f"{profile_name}-{repo_name}-findings",
            table=all_issues,
            description=f"Findings: {profile_name} | {repo_name}",
        )

    print(f"Published {len(results)} result(s) as artifacts for {repo_name}")


def _build_markdown_report(
    results: list[dict],
    repo_url: str,
    commit_hash: str,
    prompt: str,
) -> str:
    """Build a markdown report from agent results."""
    lines = [
        f"# Agent Report: {repo_url.rsplit('/', maxsplit=1)[-1]}",
        "",
        f"**Repository:** [{repo_url}]({repo_url})",
        f"**Commit:** `{commit_hash[:12]}`",
        f"**Prompt:** {prompt[:300]}",
        "",
        "---",
        "",
    ]

    for r in results:
        engine = r.get("engine", "unknown")
        model = r.get("model", "unknown")
        lines.append(f"## {engine.title()} ({model})")
        lines.append("")

        # Cost info
        if r.get("cost_usd"):
            lines.append(f"**Cost:** ${r['cost_usd']:.4f}")
        if r.get("num_turns"):
            lines.append(f"**Turns:** {r['num_turns']}")
        lines.append("")

        # Structured output summary
        structured = r.get("structured_output")
        if isinstance(structured, dict):
            if "score" in structured:
                lines.append(f"**Score:** {structured['score']}/100")
            if "summary" in structured:
                lines.append(f"\n{structured['summary']}\n")
            if "issues" in structured:
                lines.append(f"**Issues found:** {len(structured['issues'])}")
                for issue in structured["issues"][:20]:
                    sev = issue.get("severity", "?")
                    desc = issue.get("description", "")[:200]
                    file = issue.get("file", "?")
                    lines.append(f"- **[{sev.upper()}]** `{file}`: {desc}")
                if len(structured["issues"]) > 20:
                    lines.append(f"- *... and {len(structured['issues']) - 20} more*")
        else:
            # Plain text result
            result_text = r.get("result", "No output")
            lines.append(result_text[:5000])
            if len(r.get("result", "")) > 5000:
                lines.append("\n*[output truncated]*")

        lines.extend(["", "---", ""])

    return "\n".join(lines)
