"""Tests for context generation helpers."""

import tempfile
from pathlib import Path

from prefect_github_workflows.tasks.context import _dependency_summary, _file_tree, _read_key_files


def test_file_tree_excludes_git():
    """File tree should exclude .git directory contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / ".git" / "objects").mkdir(parents=True)
        (Path(tmpdir) / "src").mkdir()
        (Path(tmpdir) / "src" / "main.py").write_text("print('hello')")

        tree = _file_tree(tmpdir)
        assert tree is not None
        # .git contents (objects, refs, etc.) should be excluded
        assert ".git/objects" not in tree
        assert "src/main.py" in tree or "src" in tree


def test_read_key_files_finds_readme():
    """Key files reader should find README.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "README.md").write_text("# Test Project\nThis is a test.")

        result = _read_key_files(tmpdir)
        assert result is not None
        assert "Test Project" in result


def test_read_key_files_returns_none_for_empty():
    """Key files reader should return None for empty directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _read_key_files(tmpdir)
        assert result is None


def test_dependency_summary_finds_pyproject():
    """Dependency summary should read pyproject.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "pyproject.toml").write_text('[project]\nname = "test"\n')

        result = _dependency_summary(tmpdir)
        assert result is not None
        assert "pyproject.toml" in result
        assert "test" in result
