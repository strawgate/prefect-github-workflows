"""Result aggregation and Prefect artifact publishing."""

from __future__ import annotations

import httpx
from prefect import task
from prefect.artifacts import create_markdown_artifact, create_table_artifact

from prefect_github_workflows.secrets import get_secret


@task(timeout_seconds=60)
def publish_results(
    results: list[dict],
    repo_url: str,
    commit_hash: str,
    prompt: str,
    profile_name: str = "custom",
    post_github_issue: bool = False,
) -> None:
    """
    Publish agent results as Prefect artifacts and optionally as a GitHub issue.

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

    # ── Optional: post as GitHub issue ────────────────────────────────
    if post_github_issue and any(r.get("result") for r in results):
        _post_github_issue(repo_url, profile_name, commit_hash, md)

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


def _post_github_issue(
    repo_url: str,
    profile_name: str,
    commit_hash: str,
    body: str,
) -> None:
    """Post findings as a GitHub issue (requires write-scoped PAT)."""
    token = get_secret("github-write-token")
    if not token:
        print("No github-write-token configured — skipping issue creation")
        return

    # Extract owner/repo from URL
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]

    # Truncate body to GitHub's limit
    if len(body) > 60_000:
        body = body[:60_000] + "\n\n*[truncated]*"

    resp = httpx.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": f"[{profile_name}] Agent audit @ {commit_hash[:8]}",
            "body": body,
            "labels": ["ai-audit", profile_name],
        },
        timeout=30,
    )

    if resp.status_code == 201:
        print(f"Created GitHub issue: {resp.json().get('html_url')}")
    else:
        print(f"Failed to create issue: {resp.status_code} {resp.text[:200]}")
