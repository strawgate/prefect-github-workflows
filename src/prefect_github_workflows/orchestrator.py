"""
Main orchestrator flow.

This is the single flow that all deployments point at.  Runtime parameters
(repo, prompt, engine, tools, budget) are set per-deployment via the prompt
library, and can be overridden per-run from the CLI/UI/API.
"""

from __future__ import annotations

from prefect import flow, unmapped

from prefect_github_workflows.tasks import (
    clone_repo,
    generate_repo_context,
    publish_results,
    run_agent,
)


@flow(
    name="prefect-github-workflows",
    log_prints=True,
    retries=1,
    retry_delay_seconds=30,
    persist_result=True,
)
def github_workflow_orchestrator(
    repo_url: str = "https://github.com/jlowin/fastmcp",
    prompt: str = "Review this codebase and report any issues.",
    engine: str = "both",  # "claude", "copilot", or "both"
    allowed_tools: str = "Read,Grep,Glob",
    max_budget_usd: float = 5.0,
    max_turns: int = 10,
    json_schema: str | None = None,
    mcp_config_path: str | None = None,
    profile_name: str = "custom",  # Set by deployment, used for artifact keys
    post_github_issue: bool = False,
) -> list[dict]:
    """
    Clone a repo, generate cached context, fan out to agent(s), publish results.

    Parameters can be set at three levels (highest priority wins):
      1. Per-run override (CLI --param, UI, API)
      2. Deployment defaults (from prompt library profiles)
      3. Flow defaults (above)
    """

    # ── Phase 1: Checkout ─────────────────────────────────────────────
    print(f"▸ Phase 1: Cloning {repo_url}")
    repo_path, commit_hash = clone_repo(repo_url)

    # ── Phase 2: Context generation (cached by commit hash) ───────────
    print(f"▸ Phase 2: Generating context for {commit_hash[:8]}")
    context_doc = generate_repo_context(repo_path, commit_hash)

    # ── Phase 3: Agent dispatch ───────────────────────────────────────
    engines_to_run = ["claude", "copilot"] if engine == "both" else [engine]
    print(f"▸ Phase 3: Dispatching to {engines_to_run}")

    futures = run_agent.map(
        engines_to_run,
        unmapped(repo_path),
        unmapped(prompt),
        unmapped(context_doc),
        unmapped(allowed_tools),
        unmapped(max_budget_usd),
        unmapped(max_turns),
        unmapped(json_schema),
        unmapped(mcp_config_path),
    )
    results = [f.result() for f in futures]

    # ── Phase 4: Reporting ────────────────────────────────────────────
    print("▸ Phase 4: Publishing results")
    publish_results(
        results=results,
        repo_url=repo_url,
        commit_hash=commit_hash,
        prompt=prompt,
        profile_name=profile_name,
        post_github_issue=post_github_issue,
    )

    # Summary
    for r in results:
        cost = f"${r.get('cost_usd', 0):.4f}" if r.get("cost_usd") else "N/A"
        print(f"  {r['engine']}: {len(r.get('result', '')):,} chars, cost={cost}")

    return results
