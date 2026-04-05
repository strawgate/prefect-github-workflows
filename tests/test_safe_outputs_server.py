"""Unit tests for _record in safe_outputs_server.py."""

import json

from prefect_github_workflows.mcp import safe_outputs_server


def test_record_writes_ndjson(tmp_path, monkeypatch):
    out_path = tmp_path / "out.jsonl"
    monkeypatch.setattr(safe_outputs_server, "_output_path", out_path)
    payload = {"foo": 1, "bar": "baz"}
    action = "create_issue"
    msg = safe_outputs_server._record(action, payload)  # noqa: SLF001
    assert msg.startswith("Recorded: ")
    lines = out_path.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["action"] == action
    assert data["foo"] == 1
    assert data["bar"] == "baz"


def test_record_no_output_file(monkeypatch):
    monkeypatch.setattr(safe_outputs_server, "_output_path", None)
    msg = safe_outputs_server._record("create_issue", {"foo": 1})  # noqa: SLF001
    assert msg.startswith("ERROR: no output file")
