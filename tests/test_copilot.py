"""Unit tests for parse_copilot_jsonl in copilot.py."""

from prefect_github_workflows.tasks.copilot import parse_copilot_jsonl


def test_parse_copilot_jsonl_basic():
    # ruff: noqa: E501
    jsonl = (
        '{"type": "assistant.message", "data": {"content": "Hello world."}}\n'
        '{"type": "assistant.turn_end"}\n'
        '{"type": "result", "sessionId": "abc123", "usage": {"sessionDurationMs": 1234, "totalApiDurationMs": 567, "premiumRequests": 1}}'
    )
    result = parse_copilot_jsonl(jsonl)
    assert result["content"] == "Hello world."
    assert result["session_id"] == "abc123"
    assert result["num_turns"] == 1
    assert result["duration_ms"] == 1234
    assert result["api_duration_ms"] == 567
    assert result["premium_requests"] == 1


def test_parse_copilot_jsonl_multiple_turns():
    jsonl = """
    {"type": "assistant.message", "data": {"content": "First."}}
    {"type": "assistant.turn_end"}
    {"type": "assistant.message", "data": {"content": "Second."}}
    {"type": "assistant.turn_end"}
    {"type": "result", "sessionId": "xyz789", "usage": {"sessionDurationMs": 2222}}
    """
    result = parse_copilot_jsonl(jsonl)
    assert result["content"] == "First.\n\nSecond."
    assert result["session_id"] == "xyz789"
    assert result["num_turns"] == 2
    assert result["duration_ms"] == 2222


def test_parse_copilot_jsonl_ignores_invalid_lines():
    jsonl = 'not json\n{"type": "assistant.message", "data": {"content": "Hi"}}\n'
    result = parse_copilot_jsonl(jsonl)
    assert result["content"] == "Hi"


def test_parse_copilot_jsonl_empty():
    result = parse_copilot_jsonl("")
    assert result["content"] == ""
    assert result["session_id"] is None
    assert result["num_turns"] is None


def test_parse_copilot_jsonl_no_messages():
    jsonl = '{"type": "result", "sessionId": "id"}'
    result = parse_copilot_jsonl(jsonl)
    assert result["content"] == jsonl.strip()
    assert result["session_id"] == "id"
