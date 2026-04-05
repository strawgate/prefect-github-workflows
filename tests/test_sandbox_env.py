"""Unit tests for build_sandbox_env in sandbox_env.py."""

from prefect_github_workflows.tasks.sandbox_env import build_sandbox_env


def test_system_allowlist(monkeypatch):
    monkeypatch.setenv("HOME", "/home/test")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = build_sandbox_env()
    assert env["HOME"] == "/home/test"
    assert env["PATH"] == "/usr/bin"


def test_secrets_blocked(monkeypatch):
    monkeypatch.setenv("GITHUB_WRITE_TOKEN", "should-not-leak")
    env = build_sandbox_env()
    assert "GITHUB_WRITE_TOKEN" not in env


def test_extras_merged():
    env = build_sandbox_env({"FOO": "bar", "PATH": "/bin"})
    assert env["FOO"] == "bar"
    assert env["PATH"] == "/bin"


def test_env_isolated(monkeypatch):
    monkeypatch.delenv("HOME", raising=False)
    env = build_sandbox_env()
    assert "HOME" not in env
