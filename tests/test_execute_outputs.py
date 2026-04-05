"""Unit tests for execute_outputs.py."""

import json

import pytest

from prefect_github_workflows.mcp import execute_outputs


def make_action_line(action, payload):
    d = {"action": action}
    d.update(payload)
    return json.dumps(d)


def write_ndjson(tmp_path, lines):
    p = tmp_path / "actions.jsonl"
    p.write_text("\n".join(lines))
    return p


@pytest.mark.parametrize(
    ("action", "handler"),
    [
        ("create_issue", "_create_issue"),
        ("add_issue_comment", "_add_issue_comment"),
        ("create_pull_request_review", "_create_review"),
        ("create_pull_request", "_create_pull_request"),
        ("add_label", "_add_label"),
    ],
)
def test_execute_safe_outputs_dispatch(monkeypatch, tmp_path, action, handler):
    # Patch secret and handler
    monkeypatch.setattr(execute_outputs, "get_secret", lambda k: "tok")
    called = {}

    def fake_handler(payload, base_url, headers):
        called["called"] = (payload, base_url, headers)
        return {"action": action, "success": True, "url": "http://x"}

    monkeypatch.setattr(execute_outputs, handler, fake_handler)
    ndjson = [make_action_line(action, {"foo": "bar"})]
    p = write_ndjson(tmp_path, ndjson)
    results = execute_outputs.execute_safe_outputs(str(p), "https://github.com/org/repo")
    assert results[0]["action"] == action
    assert results[0]["success"]
    assert called["called"][0]["foo"] == "bar"


def test_execute_safe_outputs_invalid_json(monkeypatch, tmp_path):
    monkeypatch.setattr(execute_outputs, "get_secret", lambda k: "tok")
    p = write_ndjson(tmp_path, ["not json"])
    results = execute_outputs.execute_safe_outputs(str(p), "https://github.com/org/repo")
    assert not results[0]["success"]
    assert results[0]["error"] == "invalid JSON"


def test_execute_safe_outputs_no_token(monkeypatch, tmp_path):
    monkeypatch.setattr(execute_outputs, "get_secret", lambda k: None)
    p = write_ndjson(tmp_path, [make_action_line("create_issue", {"foo": "bar"})])
    results = execute_outputs.execute_safe_outputs(str(p), "https://github.com/org/repo")
    assert results == []


def test_execute_safe_outputs_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(execute_outputs, "get_secret", lambda k: "tok")
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    results = execute_outputs.execute_safe_outputs(str(p), "https://github.com/org/repo")
    assert results == []


def test_execute_safe_outputs_unknown_action(monkeypatch, tmp_path):
    monkeypatch.setattr(execute_outputs, "get_secret", lambda k: "tok")
    ndjson = [make_action_line("not_a_real_action", {"foo": 1})]
    p = write_ndjson(tmp_path, ndjson)
    results = execute_outputs.execute_safe_outputs(str(p), "https://github.com/org/repo")
    assert not results[0]["success"]
    assert "unknown action" in results[0]["error"]
