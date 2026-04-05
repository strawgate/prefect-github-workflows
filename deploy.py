"""
Deploy all prompt library profiles as named Prefect deployments.

Run:  uv run python deploy.py
Then: prefect worker start --pool github-workflows-pool --type docker

Each profile in src/prefect_github_workflows/prompts/library.py becomes a
deployment like:
  prefect-github-workflows/security-audit
  prefect-github-workflows/bug-hunt
  prefect-github-workflows/test-coverage-audit
  ...
"""

from __future__ import annotations

import sys

from prefect import serve

# Importing library populates PROMPT_LIBRARY via register()
import prefect_github_workflows.prompts.library  # noqa: F401  # side-effect: registers profiles
from prefect_github_workflows.orchestrator import github_workflow_orchestrator
from prefect_github_workflows.prompts.registry import PROMPT_LIBRARY

# ── Note ──────────────────────────────────────────────────────────────
# This script uses serve() — deployments run in-process (good for dev).
# For production Docker work-pool deployments with secret injection,
# see scripts/deploy_to_workpool.py instead.


def create_deployments() -> list:
    """Build a Prefect deployment for each prompt library profile."""
    deployments = []

    for profile in PROMPT_LIBRARY:
        params = profile.deployment_parameters()
        params["profile_name"] = profile.name

        # Attach JSON schema if the profile defines one
        if profile.json_schema:
            params["json_schema"] = profile.json_schema

        deployment = github_workflow_orchestrator.to_deployment(
            name=profile.name,
            parameters=params,
            tags=profile.tags,
            description=profile.description,
            **({"cron": profile.cron} if profile.cron else {}),
        )
        deployments.append(deployment)
        print(
            f"  ✓ {profile.name:<30} "
            f"engine={profile.engine:<8} "
            f"budget=${profile.max_budget_usd:<6.2f} "
            f"turns={profile.max_turns:<3} "
            f"{'cron=' + profile.cron if profile.cron else ''}"
        )

    return deployments


def main():
    print(f"\n{'═' * 60}")
    print(f"  Deploying {len(PROMPT_LIBRARY)} agent profiles")
    print(f"{'═' * 60}\n")

    deployments = create_deployments()

    if not deployments:
        print("No profiles found in PROMPT_LIBRARY.  Check library.py.")
        sys.exit(1)

    print(f"\n{'─' * 60}")
    print(f"  Starting serve loop ({len(deployments)} deployments)")
    print("  Ctrl+C to stop\n")

    # serve() registers all deployments with Prefect Cloud and starts
    # polling for runs.  For work-pool-based execution, you'd instead
    # use .deploy() per profile and run a separate worker.
    serve(*deployments)


if __name__ == "__main__":
    main()
