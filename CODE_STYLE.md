# Code Style

Subjective style preferences for code reviewers. Enforced lints live in `pyproject.toml` under `[tool.ruff]` — this file covers what linters can't catch.

## Naming

- **Task files:** verb-noun, e.g. `clone.py`, `dispatch.py`, `reporting.py`
- **Builder helpers:** `_build_<thing>_<part>()`, e.g. `_build_copilot_env()`, `_build_claude_cmd()`
- **Parser helpers:** `_parse_<format>_<thing>()`, e.g. `_parse_copilot_jsonl()`, `_parse_claude_result()`
- **Private helpers:** prefix with `_`, e.g. `_unavailable_result()`, `_record()`
- **Constants:** `UPPER_SNAKE`, e.g. `AGENT_IMAGE`, `_SYSTEM_ALLOWLIST`
- **OK/fail result builders:** `_ok(action, url)` / `_fail(action, error)` for uniform return shapes

## Function signatures

- Use `str | None` (not `Optional[str]`) — we target Python 3.12+
- Prefer keyword arguments with defaults for optional params
- Task return dicts should include `engine` as the first key for easy identification

## Docstrings

- Module-level docstrings: explain what the module does and any non-obvious design decisions
- Function docstrings: one-line summary, then a blank line, then details if needed
- Skip docstrings on trivial private helpers (`_ok`, `_fail`, etc.)
- Use NumPy-style parameter docs only in public API functions when the params aren't self-explanatory

## Error handling

- CLI wrappers should never crash the flow for expected failures (agent timeout, bad exit code)
- Return an error dict with meaningful `result` text and `exit_code != 0`
- Raise `RuntimeError` only for truly unexpected failures (binary not found, JSON parse of expected output)
- Use `contextlib.suppress()` over bare `try/except` for known-ignorable errors (e.g. JSON parse of optional structured output)

## Imports

- Group: stdlib → third-party → local, separated by blank lines
- `from __future__ import annotations` at the top of every module
- Prefer importing the function, not the module: `from prefect import task` not `import prefect`

## Comments

- Explain *why*, not *what* — the code should be readable on its own
- Use `# ── Section Name ──` banners sparingly, only for major sections in long files
- Inline comments on the same line only for non-obvious CLI flags or magic values

## PR conventions

- One logical change per commit
- Commit message: imperative mood, e.g. "Add Docker container isolation for agents"
- If a change touches both claude.py and copilot.py, they should stay symmetric — same return dict shape, same error handling pattern
