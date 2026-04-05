"""Tests for the dispatch module."""

import pytest

from prefect_github_workflows.tasks.dispatch import run_agent


def test_unknown_engine_raises():
    """Dispatch should raise ValueError for unknown engine names."""
    with pytest.raises(ValueError, match="Unknown engine"):
        run_agent.fn(
            engine="unknown",
            repo_path="/tmp",
            prompt="test",
            context_doc="test context",
        )
