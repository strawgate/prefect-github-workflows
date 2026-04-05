"""Execute safe-output actions recorded by the MCP server.

Reads the NDJSON file produced by safe_outputs_server and executes each
action against the GitHub REST API.  The agent never sees the write token —
only this module does.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from prefect_github_workflows.secrets import get_secret


def execute_safe_outputs(
    output_file: str | Path,
    repo_url: str,
) -> list[dict]:
    """Read recorded actions and execute them against GitHub.

    Returns a list of result dicts (one per action) with keys:
      action, success, url (on success), error (on failure)
    """
    path = Path(output_file)
    if not path.exists() or path.stat().st_size == 0:
        return []

    token = get_secret("github-write-token")
    if not token:
        print("No github-write-token configured — skipping output execution")
        return []

    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    base_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    results = []
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            results.append({"action": "unknown", "success": False, "error": "invalid JSON"})
            continue

        action = record.pop("action", "unknown")
        result = _dispatch(action, record, base_url, headers)
        results.append(result)

    return results


def _dispatch(
    action: str,
    payload: dict,
    base_url: str,
    headers: dict,
) -> dict:
    """Route an action to the correct GitHub API call."""
    handlers = {
        "create_issue": _create_issue,
        "add_issue_comment": _add_issue_comment,
        "create_pull_request_review": _create_review,
        "create_pull_request": _create_pull_request,
        "add_label": _add_label,
    }
    handler = handlers.get(action)
    if not handler:
        return {"action": action, "success": False, "error": f"unknown action: {action}"}
    try:
        return handler(payload, base_url, headers)
    except Exception as exc:
        return {"action": action, "success": False, "error": str(exc)}


def _ok(action: str, url: str = "") -> dict:
    return {"action": action, "success": True, "url": url}


def _fail(action: str, resp: httpx.Response) -> dict:
    return {
        "action": action,
        "success": False,
        "error": f"{resp.status_code}: {resp.text[:200]}",
    }


def _create_issue(payload: dict, base_url: str, headers: dict) -> dict:
    resp = httpx.post(
        f"{base_url}/issues",
        headers=headers,
        json={
            "title": payload["title"],
            "body": _truncate(payload.get("body", "")),
            "labels": payload.get("labels", []),
        },
        timeout=30,
    )
    if resp.status_code == 201:
        url = resp.json().get("html_url", "")
        print(f"Created issue: {url}")
        return _ok("create_issue", url)
    return _fail("create_issue", resp)


def _add_issue_comment(payload: dict, base_url: str, headers: dict) -> dict:
    issue_number = payload["issue_number"]
    resp = httpx.post(
        f"{base_url}/issues/{issue_number}/comments",
        headers=headers,
        json={"body": _truncate(payload.get("body", ""))},
        timeout=30,
    )
    if resp.status_code == 201:
        url = resp.json().get("html_url", "")
        print(f"Added comment on #{issue_number}: {url}")
        return _ok("add_issue_comment", url)
    return _fail("add_issue_comment", resp)


def _create_review(payload: dict, base_url: str, headers: dict) -> dict:
    pr_number = payload["pr_number"]
    body: dict = {
        "body": _truncate(payload.get("body", "")),
        "event": payload.get("event", "COMMENT"),
    }
    if payload.get("comments"):
        body["comments"] = payload["comments"]
    resp = httpx.post(
        f"{base_url}/pulls/{pr_number}/reviews",
        headers=headers,
        json=body,
        timeout=30,
    )
    if resp.status_code == 200:
        url = resp.json().get("html_url", "")
        print(f"Submitted review on PR #{pr_number}: {url}")
        return _ok("create_pull_request_review", url)
    return _fail("create_pull_request_review", resp)


def _create_pull_request(payload: dict, base_url: str, headers: dict) -> dict:
    resp = httpx.post(
        f"{base_url}/pulls",
        headers=headers,
        json={
            "title": payload["title"],
            "body": _truncate(payload.get("body", "")),
            "head": payload["head"],
            "base": payload.get("base", "main"),
        },
        timeout=30,
    )
    if resp.status_code == 201:
        url = resp.json().get("html_url", "")
        pr_number = resp.json().get("number")
        if payload.get("labels") and pr_number:
            httpx.post(
                f"{base_url}/issues/{pr_number}/labels",
                headers=headers,
                json={"labels": payload["labels"]},
                timeout=10,
            )
        print(f"Created PR: {url}")
        return _ok("create_pull_request", url)
    return _fail("create_pull_request", resp)


def _add_label(payload: dict, base_url: str, headers: dict) -> dict:
    issue_number = payload["issue_number"]
    resp = httpx.post(
        f"{base_url}/issues/{issue_number}/labels",
        headers=headers,
        json={"labels": payload.get("labels", [])},
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"Added labels to #{issue_number}")
        return _ok("add_label")
    return _fail("add_label", resp)


def _truncate(text: str, limit: int = 60_000) -> str:
    """Truncate text to GitHub's body limit."""
    if len(text) > limit:
        return text[:limit] + "\n\n*[truncated]*"
    return text
