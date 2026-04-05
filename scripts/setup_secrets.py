#!/usr/bin/env python3
"""
One-time setup: create Prefect Cloud Secret blocks for all API keys.

Run:  python scripts/setup_secrets.py

This prompts interactively for each secret value and stores it encrypted
in Prefect Cloud.  Flow runs reference these via Jinja templating in
job_variables — the values never appear in deployment config or logs.

You can also create these in the Prefect Cloud UI under Blocks → Secret.
"""

from __future__ import annotations

import getpass
import sys


def main():
    try:
        from prefect.blocks.system import Secret
    except ImportError:
        print("Install prefect first:  pip install prefect")
        sys.exit(1)

    secrets = [
        {
            "name": "anthropic-api-key",
            "prompt": "Anthropic API key (sk-ant-...)",
            "required": True,
        },
        {
            "name": "copilot-github-token",
            "prompt": "GitHub PAT with Copilot Requests permission (ghp_...)",
            "required": False,
        },
        {
            "name": "github-clone-token",
            "prompt": "GitHub PAT with Contents:read for private repos (ghp_...)",
            "required": False,
        },
        {
            "name": "github-write-token",
            "prompt": "GitHub PAT with Issues:write for posting results (ghp_...)",
            "required": False,
        },
    ]

    print("\n══════════════════════════════════════════════════")
    print("  Prefect Cloud Secret Block Setup")
    print("══════════════════════════════════════════════════\n")
    print("Each secret is stored encrypted in Prefect Cloud.")
    print("Press Enter to skip optional secrets.\n")

    created = 0
    skipped = 0

    for s in secrets:
        label = "REQUIRED" if s["required"] else "optional"
        value = getpass.getpass(f"  [{label}] {s['prompt']}: ")

        if not value:
            if s["required"]:
                print(f"    ✗ {s['name']} is required.  Aborting.")
                sys.exit(1)
            else:
                print(f"    – Skipped {s['name']}")
                skipped += 1
                continue

        Secret(value=value).save(s["name"], overwrite=True)
        print(f"    ✓ Saved {s['name']}")
        created += 1

    print(f"\nDone: {created} created, {skipped} skipped.\n")


if __name__ == "__main__":
    main()
