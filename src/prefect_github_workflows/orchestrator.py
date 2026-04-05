"""
Main orchestrator flow.

This is the single flow that all deployments point at.  Runtime parameters
(repo, prompt, engine, tools, budget) are set per-deployment via the prompt
library, and can be overridden per-run from the CLI/UI/API.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, unmapped

from prefect_github_workflows.mcp.execute_outputs import execute_safe_outputs
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
    execute_outputs: bool = True,
    use_docker: bool = False,
) -> list[dict]:
    """
    Clone a repo, generate cached context, fan out to agent(s), publish results.

    Agents are given a safe-outputs MCP server with tools like create_issue,
    add_comment, and create_pull_request_review.  Calls are recorded to a
    temp file and executed by the orchestrator after the agent finishes
    (when execute_outputs=True).

    When ``use_docker=True``, each agent runs inside an isolated Docker
    container with read-only repo access and only its own auth token.
    When ``False`` (default), agents run as direct subprocesses with
    env-var sandboxing — suitable for local development.

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
        unmapped(use_docker),
    )
    results = [f.result() for f in futures]

    # ── Phase 4: Execute safe-outputs ─────────────────────────────────
    if execute_outputs:
        print("▸ Phase 4: Executing safe-outputs")
        for r in results:
            output_file = r.pop("safe_outputs_file", None)
            if output_file:
                try:
                    actions = execute_safe_outputs(output_file, repo_url)
                    r["executed_actions"] = actions
                    ok = sum(1 for a in actions if a.get("success"))
                    print(f"  {r['engine']}: executed {ok}/{len(actions)} actions")
                finally:
                    Path(output_file).unlink(missing_ok=True)
    else:
        print("▸ Phase 4: Skipping output execution (dry run)")
        for r in results:
            r.pop("safe_outputs_file", None)

    # ── Phase 5: Reporting ────────────────────────────────────────────
    print("▸ Phase 5: Publishing artifacts")
    publish_results(
        results=results,
        repo_url=repo_url,
        commit_hash=commit_hash,
        prompt=prompt,
        profile_name=profile_name,
    )

    # Summary
    for r in results:
        cost = f"${r.get('cost_usd', 0):.4f}" if r.get("cost_usd") else "N/A"
        print(f"  {r['engine']}: {len(r.get('result', '')):,} chars, cost={cost}")

    return results
