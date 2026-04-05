#!/usr/bin/env python3
"""
Deploy all prompt library profiles to a Docker work pool on Prefect Cloud.

This is the ALTERNATIVE to deploy.py's serve() approach:
  - deploy.py uses serve() → runs deployments in-process (simpler, good for dev)
  - This script uses .deploy() → pushes to a Docker work pool (production)

Run:  python scripts/deploy_to_workpool.py

Then start the worker separately:
  prefect worker start --pool github-workflows-pool --type docker
"""

from __future__ import annotations

# Importing library populates PROMPT_LIBRARY via register()
import prefect_github_workflows.prompts.library  # noqa: F401  # side-effect: registers profiles
from prefect_github_workflows.orchestrator import github_workflow_orchestrator
from prefect_github_workflows.prompts.registry import PROMPT_LIBRARY

WORK_POOL = "github-workflows-pool"
IMAGE = "prefect-github-workflows:latest"

JOB_VARIABLES = {
    "env": {
        "ANTHROPIC_API_KEY": "{{ prefect.blocks.secret.anthropic-api-key }}",
        "COPILOT_GITHUB_TOKEN": "{{ prefect.blocks.secret.copilot-github-token }}",
        "GITHUB_CLONE_TOKEN": "{{ prefect.blocks.secret.github-clone-token }}",
        "GITHUB_WRITE_TOKEN": "{{ prefect.blocks.secret.github-write-token }}",
    },
}


def main():
    print(f"\n{'═' * 60}")
    print(f"  Deploying {len(PROMPT_LIBRARY)} profiles to work pool: {WORK_POOL}")
    print(f"  Image: {IMAGE}")
    print(f"{'═' * 60}\n")

    for profile in PROMPT_LIBRARY:
        params = profile.deployment_parameters()
        params["profile_name"] = profile.name
        if profile.json_schema:
            params["json_schema"] = profile.json_schema

        deploy_kwargs = {
            "name": profile.name,
            "work_pool_name": WORK_POOL,
            "image": IMAGE,
            "parameters": params,
            "tags": profile.tags,
            "description": profile.description,
            "job_variables": JOB_VARIABLES,
            "build": False,  # Image is pre-built
            "push": False,  # Image is pre-pushed
        }

        if profile.cron:
            deploy_kwargs["cron"] = profile.cron

        github_workflow_orchestrator.deploy(**deploy_kwargs)

        schedule_info = f"cron={profile.cron}" if profile.cron else "manual"
        print(f"  ✓ {profile.name:<30} [{schedule_info}]")

    print(f"\n{'─' * 60}")
    print("  All deployments registered with Prefect Cloud.")
    print("  Start the worker:")
    print(f"    prefect worker start --pool {WORK_POOL} --type docker")
    print()


if __name__ == "__main__":
    main()
