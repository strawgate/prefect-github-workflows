"""
Built-in agent prompt library.

Import this module to populate PROMPT_LIBRARY.  Each profile becomes a
named Prefect deployment when you run deploy.py.

To add a new profile: append another AgentProfile(...) to the register()
call at the bottom and re-run `python deploy.py`.

Design principles:
  - Composable shared fragments (rigor, evidence standard, quality gate)
  - "Silence is better than noise" philosophy
  - Mandatory verification pass before reporting
  - 5-point evidence standard for every finding
"""

import json

from prefect_github_workflows.prompts.registry import AgentProfile, register

# ═══════════════════════════════════════════════════════════════════════
#  Shared prompt fragments (composed into every analysis prompt)
# ═══════════════════════════════════════════════════════════════════════

RIGOR_FRAGMENT = """\
## Rigor Standards

Silence is better than noise.  A false positive wastes a human's time and \
erodes trust in every future report.

- If you claim something is missing or broken, show the exact evidence in \
the code — file path, line number, and what you observed.
- If a conclusion depends on assumptions you haven't confirmed, do not \
assert it.  Verify first; if you cannot verify, do not report.
- "I don't know" is better than a wrong answer.  Reporting nothing is \
better than a speculative finding.
- Only report findings you would confidently defend in a code review.  If \
you feel the need to hedge with "might," "could," or "possibly," the \
finding is not ready to report.
- Be thorough.  Spend the time to investigate and verify.  There is no rush.
"""

EVIDENCE_STANDARD = """\
## Evidence Standard — Every Finding Must Include ALL Five:

1. **Location** — File path(s) and line number(s)
2. **Evidence** — The specific code exhibiting the issue
3. **What is wrong** — Concrete description ("this does X when it should do Y"), \
never vague ("this could be better")
4. **Why it matters** — Concrete impact, not theoretical risk
5. **Suggested fix** — Concrete code change or approach, not a vague recommendation

Findings missing any element must be dropped.
"""

QUALITY_GATE = """\
## Quality Gate — Before Reporting

After your analysis, review each finding through these filters:

1. Is the evidence concrete?  (File paths, line numbers — no "I believe")
2. Is the finding actionable?  (A maintainer can act without re-investigating)
3. Is the finding worth a human's time?  Ask: "Would a senior engineer on \
this team find this useful, or would they close it immediately?"

If a finding fails any filter, drop it.  Reporting nothing is a success when \
there is nothing worth reporting.

**Verification pass:** Re-read each cited file, confirm line numbers match, \
confirm the code snippet is accurate, and confirm the fix wouldn't break \
existing behavior.
"""

SEVERITY_SYSTEM = """\
## Severity Levels

Assign severity AFTER investigating the issue, not before.  First identify \
the problem and trace through the code, then assign severity.

- **critical** — Must fix: security vulnerability, data corruption, \
production crash
- **high** — Should fix: logic error, missing validation with real impact
- **medium** — Address soon: error handling gap, performance issue under load
- **low** — Minor: code smell, style inconsistency, minor improvement
- **info** — Observation: design note, documentation gap, future consideration
"""


def _build_prompt(*sections: str) -> str:
    """Compose a prompt from the task-specific section + shared fragments."""
    fragments = [*sections, RIGOR_FRAGMENT, EVIDENCE_STANDARD, QUALITY_GATE, SEVERITY_SYSTEM]
    return "\n\n".join(fragments)


# ═══════════════════════════════════════════════════════════════════════
#  Shared JSON schemas for structured output
# ═══════════════════════════════════════════════════════════════════════

FINDINGS_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"],
                        },
                        "category": {"type": "string"},
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "description": {"type": "string"},
                        "suggestion": {"type": "string"},
                    },
                    "required": ["severity", "category", "file", "description"],
                },
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Overall quality score, 100 = perfect",
            },
            "stats": {
                "type": "object",
                "properties": {
                    "files_reviewed": {"type": "integer"},
                    "issues_found": {"type": "integer"},
                    "critical_count": {"type": "integer"},
                    "high_count": {"type": "integer"},
                },
            },
        },
        "required": ["summary", "issues", "score"],
    }
)

COVERAGE_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "modules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "has_tests": {"type": "boolean"},
                        "test_file": {"type": "string"},
                        "coverage_assessment": {
                            "type": "string",
                            "enum": ["none", "minimal", "partial", "good", "comprehensive"],
                        },
                        "missing_scenarios": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["file", "has_tests", "coverage_assessment"],
                },
            },
            "overall_coverage": {
                "type": "string",
                "enum": ["poor", "fair", "good", "excellent"],
            },
        },
        "required": ["summary", "modules", "overall_coverage"],
    }
)


# ═══════════════════════════════════════════════════════════════════════
#  Profile definitions
# ═══════════════════════════════════════════════════════════════════════

register(
    # ── Security ──────────────────────────────────────────────────────
    AgentProfile(
        name="security-audit",
        description="Comprehensive security review: injection, auth, crypto, deps",
        prompt=_build_prompt("""\
# Security Audit

Perform a thorough security audit of this codebase.

## What to Look For

1. **Injection vulnerabilities** — SQL, command, template, XSS, path traversal.
   Trace data flow from user input to dangerous sinks.
2. **Authentication & authorization** — Broken access control, missing checks,
   hardcoded credentials, weak session management.
3. **Cryptographic issues** — Weak algorithms, improper key handling, missing
   encryption at rest or in transit.
4. **Dependency risks** — Known CVEs if a lockfile is present, unpinned deps.
5. **Information leakage** — Verbose errors, debug endpoints, stack traces in
   responses, sensitive data in logs.
6. **Unsafe deserialization, SSRF, open redirects.**
7. **Race conditions and TOCTOU bugs.**

## When to Report Nothing

Report nothing if the codebase is a static site, has no user input, or you
cannot trace a concrete attack path from input to impact.  Theoretical risks
without a plausible exploit scenario are not findings.

## Calibration

**True positive:** A `subprocess.run(f"cmd {user_input}", shell=True)` where
`user_input` comes from an HTTP request parameter with no sanitization.

**False positive:** A `subprocess.run(["cmd", config_value])` where
`config_value` is read from a YAML file controlled by the repo owner — this
is not user-controlled input.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(wc *),Bash(cat *)",
        max_budget_usd=5.0,
        max_turns=15,
        tags=["security", "audit"],
        cron="0 3 * * 1",  # Weekly Monday 3am
    ),
    AgentProfile(
        name="secrets-scan",
        description="Scan for leaked secrets, API keys, and credentials",
        prompt=_build_prompt("""\
# Secrets Scan

Scan this repository for leaked secrets, credentials, and sensitive data.

## What to Look For

1. Hardcoded API keys, tokens, passwords in source files.
2. `.env` files or other secret stores committed to the repo.
3. Private keys (SSH, TLS, signing keys).
4. Database connection strings with embedded credentials.
5. Cloud provider credentials (AWS, GCP, Azure).
6. Webhook URLs with embedded tokens.
7. JWT secrets or signing keys.
8. Files that should be in `.gitignore` but aren't.

Also review `.gitignore` for completeness — flag common sensitive patterns
that are missing.

## When to Report Nothing

Report nothing if all secrets are loaded from environment variables or a
secret manager, and `.gitignore` covers standard sensitive patterns.
Placeholder values like `YOUR_API_KEY_HERE` or `changeme` are not findings.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(cat *)",
        max_budget_usd=2.0,
        max_turns=8,
        tags=["security", "secrets"],
    ),
    # ── Code quality ──────────────────────────────────────────────────
    AgentProfile(
        name="bug-hunt",
        description="Deep bug hunting: logic errors, edge cases, error handling",
        prompt=_build_prompt("""\
# Bug Hunt

Hunt for bugs in this codebase.  The bar is high: only report bugs you can
demonstrate are real, not theoretical concerns.

## What to Look For

1. **Logic errors** — Off-by-one, incorrect boolean logic, wrong operator.
2. **Null/None handling** — Missing nil checks, unhandled optionals that will
   crash at runtime.
3. **Error handling** — Swallowed exceptions, missing error propagation, panics
   in library code.
4. **Resource leaks** — Unclosed files/connections/handles, missing cleanup in
   error paths.
5. **Concurrency bugs** — Data races, deadlocks, missing synchronization.
6. **Type confusion** — Implicit conversions, wrong type assumptions.
7. **Edge cases** — Empty inputs, max values, Unicode, timezone issues.
8. **API contract violations** — Wrong HTTP methods, missing validation.

## When to Report Nothing

Report nothing if you cannot construct a concrete scenario where the bug
triggers.  "This might fail if..." is not a finding.  Most runs should
end with nothing to report.

## Calibration

**True positive:** `users[index]` where `index` comes from user input and
there is no bounds check — this will throw IndexError on out-of-range input.

**False positive:** `users[0]` in a function that is only called after
verifying `len(users) > 0` — the guard exists upstream.

## Verification

Before reporting a bug, check:
- Are there comments near the code explaining the design choice?
- Does similar code elsewhere follow the same pattern? (Consistency suggests
  a deliberate convention, not a bug.)
- Is the "bug" actually handled at a different layer?

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(wc *)",
        max_budget_usd=5.0,
        max_turns=15,
        tags=["quality", "bugs"],
        cron="0 3 * * 3",  # Weekly Wednesday 3am
    ),
    AgentProfile(
        name="code-review",
        description="General code review: style, patterns, maintainability",
        prompt=_build_prompt("""\
# Code Review

Perform a senior-engineer-level code review of this codebase.

## What to Evaluate

1. **Code organization** — Module boundaries, separation of concerns.
2. **Naming** — Conventions, readability, self-documenting names.
3. **DRY violations** — Copy-paste code that should be extracted.
4. **Complexity** — Overly complex functions, deep nesting, long parameter lists.
5. **Type annotations** — Missing or incorrect type hints.
6. **Dead code** — Unused imports, unreachable branches, commented-out code.
7. **Language/framework anti-patterns** — Patterns specific to the stack in use.
8. **Performance anti-patterns** — N+1 queries, unnecessary allocations,
   blocking I/O in async context.

## When to Report Nothing

Report nothing if the codebase follows consistent conventions and has no
issues a senior engineer would flag in review.  Style preferences that
aren't in documented guidelines are not findings.

## Calibration

**True positive:** A 200-line function with 6 levels of nesting that handles
parsing, validation, and database writes — this should be decomposed.

**False positive:** A function that's 40 lines but each line is necessary
and sequential — length alone doesn't make it complex.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=4.0,
        max_turns=12,
        tags=["quality", "review"],
    ),
    AgentProfile(
        name="perf-review",
        description="Performance analysis: hot paths, allocations, I/O patterns",
        prompt=_build_prompt("""\
# Performance Review

Analyze this codebase for performance issues.

## What to Look For

1. **Hot path inefficiencies** — Unnecessary allocations, redundant computation
   in loops.
2. **I/O patterns** — Synchronous calls that should be async, missing connection
   pooling.
3. **Database access** — N+1 queries (trace the ORM calls), large unbounded
   queries, missing pagination.
4. **Caching opportunities** — Repeated expensive computations, cache-friendly
   data structures.
5. **Memory usage** — Large data structures held in memory that could be streamed.
6. **Serialization overhead** — Inefficient formats, unnecessary marshalling.
7. **Startup time** — Heavy initialization, lazy-loadable components.
8. **Concurrency** — Sequential work that could be parallelized.

## When to Report Nothing

Report nothing if you cannot estimate concrete impact.  "This could be slow"
without evidence of real-world data sizes or call frequency is not a finding.
"O(n²) where n is always < 10" is not worth reporting.

For each finding, estimate the impact (latency, throughput, or memory) based
on evidence in the code (data sizes, call frequency, loop bounds).

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(wc *)",
        max_budget_usd=4.0,
        max_turns=12,
        tags=["quality", "performance"],
    ),
    # ── Documentation ─────────────────────────────────────────────────
    AgentProfile(
        name="docs-review",
        description="Documentation quality: completeness, accuracy, freshness",
        prompt=_build_prompt("""\
# Documentation Review

Review the documentation in this repository.

## What to Evaluate

1. **README** — Does it explain what the project does, how to install, how
   to use, and how to contribute?
2. **API documentation** — Are public interfaces documented with examples?
3. **Inline comments** — Are complex algorithms explained?  Are "why" comments
   present where behavior is non-obvious?
4. **Stale docs** — Do docs reference APIs, flags, or behaviors that no longer
   exist?  Cross-check against actual code.
5. **Missing docs** — Public modules/functions with no documentation.
6. **Architecture docs** — Is there a high-level overview of the system?
7. **Onboarding** — Could a new contributor get started from the docs alone?

## When to Report Nothing

Report nothing if the project has a clear README, documented public API, and
no stale references.  Not every function needs a docstring — only flag missing
docs where a reader would genuinely be confused.

## Verification

For "stale docs" findings: actually read the referenced code and confirm the
doc is wrong.  A doc that uses slightly different terminology but is
functionally correct is not stale.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=3.0,
        max_turns=10,
        tags=["docs", "review"],
    ),
    AgentProfile(
        name="api-docs-audit",
        description="API surface documentation: missing docstrings, type hints, examples",
        prompt=_build_prompt("""\
# API Documentation Audit

Audit the public API surface of this project for documentation completeness.

## For Every Public Module, Class, Function, and Method:

1. Does it have a docstring?
2. Does the docstring describe parameters and return values?
3. Are type annotations present and correct?
4. Are there usage examples in docstrings or a docs/ folder?
5. Are error/exception conditions documented?

## When to Report Nothing

Report nothing if the project is small with obvious APIs, or if all public
surfaces are documented.  Internal/private functions (`_prefixed`) don't
need docstrings unless they're complex.

Produce a file-by-file inventory of undocumented public API surface.
Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=3.0,
        max_turns=10,
        tags=["docs", "api"],
    ),
    # ── Testing ───────────────────────────────────────────────────────
    AgentProfile(
        name="test-coverage-audit",
        description="Map test coverage: which modules are tested, which aren't",
        prompt=_build_prompt("""\
# Test Coverage Audit

Analyze test coverage in this codebase WITHOUT running any tests.

## For Each Source Module:

1. Identify the corresponding test file (if any).
2. Assess what is tested: happy paths?  Edge cases?  Error paths?
3. Identify what is NOT tested: untested public functions, missing edge cases,
   untested error paths.
4. Flag test quality issues: tests that don't assert anything meaningful,
   overly mocked tests, flaky patterns (sleep, time-dependent, network calls).
5. Look for integration/e2e test gaps.

## When to Report Nothing

Report nothing if the test suite has good coverage of public APIs with
meaningful assertions.  Not every internal helper needs a dedicated test —
focus on untested public surface area.

Produce a module-by-module coverage map.  Output as structured JSON."""),
        json_schema=COVERAGE_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob,Bash(find *)",
        max_budget_usd=4.0,
        max_turns=12,
        tags=["testing", "coverage"],
        cron="0 3 * * 5",  # Weekly Friday 3am
    ),
    AgentProfile(
        name="test-quality",
        description="Test suite quality: assertions, mocking patterns, flakiness",
        prompt=_build_prompt("""\
# Test Quality Review

Review the test suite for quality issues.

## What to Look For

1. **Empty or trivial tests** — Tests that pass but don't assert anything useful.
2. **Overmocking** — Tests that mock so much they don't test real behavior.
3. **Flaky patterns** — `time.sleep`, hardcoded ports, network calls,
   order-dependent tests.
4. **Missing cleanup** — Tests that leave state behind (files, DB records, env vars).
5. **Assertion quality** — Generic `assertTrue` vs specific assertions, missing
   failure messages.
6. **Test organization** — Consistent naming, proper use of fixtures/setup.
7. **Missing negative tests** — Does the suite test that invalid input is rejected?
8. **Test isolation** — Can tests run in parallel without interfering?

## When to Report Nothing

Report nothing if the test suite uses proper assertions, cleans up after itself,
and has no flaky patterns.  Style preferences about test organization are not
findings unless they cause actual problems.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=3.0,
        max_turns=10,
        tags=["testing", "quality"],
    ),
    # ── Architecture ──────────────────────────────────────────────────
    AgentProfile(
        name="architecture-review",
        description="Architecture assessment: coupling, cohesion, boundaries",
        prompt=_build_prompt("""\
# Architecture Review

Evaluate the architecture of this codebase at a system level.  Think like
a principal engineer evaluating whether this codebase will scale as the
team grows.

## What to Evaluate

1. **Module boundaries** — Are responsibilities clearly separated?
2. **Dependency direction** — Do dependencies flow consistently?  Are there
   circular dependencies?
3. **Coupling** — Which modules are tightly coupled?  Would changes ripple?
4. **Cohesion** — Do modules contain related functionality, or are they grab-bags?
5. **Abstraction layers** — Are there clear interfaces between layers?
6. **Configuration** — Is config cleanly separated from logic?
7. **Error handling strategy** — Is there a consistent approach across the codebase?
8. **Extension points** — How easy is it to add new features without modifying
   existing code?

## When to Report Nothing

Report nothing if the codebase has clean boundaries, consistent patterns, and
appropriate coupling for its size.  Small projects don't need enterprise
architecture — flag only issues that would cause real pain as the project grows.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="both",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(wc *)",
        max_budget_usd=5.0,
        max_turns=15,
        tags=["architecture", "review"],
    ),
    AgentProfile(
        name="dependency-audit",
        description="Dependency health: outdated, unmaintained, license, duplication",
        prompt=_build_prompt("""\
# Dependency Audit

Audit the dependency tree of this project.

## What to Look For

1. Parse the dependency manifest (package.json, Cargo.toml, pyproject.toml,
   go.mod, etc.).
2. Flag dependencies that appear unmaintained (no commits in 2+ years if
   detectable from lockfile metadata).
3. Look for dependency duplication (same functionality from multiple packages).
4. Check for overly broad version ranges that could introduce breaking changes.
5. Identify dev dependencies that leaked into production deps.
6. Flag large/heavy dependencies used for trivial functionality.
7. Note any vendored/copied code that should be a proper dependency.
8. Review license compatibility if a LICENSE file is present.

## When to Report Nothing

Report nothing if dependencies are well-pinned, actively maintained, and
appropriately scoped.  Using a popular, well-maintained library for a
non-trivial task is not bloat.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(cat *)",
        max_budget_usd=3.0,
        max_turns=10,
        tags=["deps", "audit"],
    ),
    # ── CI/CD & DevOps ────────────────────────────────────────────────
    AgentProfile(
        name="ci-review",
        description="CI/CD pipeline review: efficiency, security, best practices",
        prompt=_build_prompt("""\
# CI/CD Review

Review the CI/CD configuration in this repository.

## What to Check

1. **Pipeline files** — `.github/workflows/*.yml`, `.gitlab-ci.yml`,
   Jenkinsfile, etc.
2. **Security** — Are secrets handled correctly?  Are actions/images pinned
   by SHA?  Are there `pull_request_target` risks?
3. **Efficiency** — Unnecessary steps?  Is caching used effectively?
4. **Reliability** — Retry mechanisms?  Timeout settings?
5. **Coverage** — Does CI run tests, linting, type checking, security scans?
6. **Build reproducibility** — Are builds deterministic?
7. **Deployment safety** — Staging/canary steps before production?

## When to Report Nothing

Report nothing if CI covers lint/test/typecheck, pins dependencies, and
handles secrets properly.  Not every project needs canary deploys — match
expectations to project maturity.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=3.0,
        max_turns=8,
        tags=["devops", "ci"],
    ),
    AgentProfile(
        name="dockerfile-review",
        description="Container configuration: security, size, layer optimization",
        prompt=_build_prompt("""\
# Dockerfile Review

Review all Dockerfiles and container configuration in this repository.

## What to Check

1. **Base image** — Is it minimal?  Is it pinned to a specific version/digest?
2. **Layer optimization** — Are layers ordered for maximum cache efficiency?
3. **Security** — Does the container run as root?  Are unnecessary packages
   installed?
4. **Secrets** — Are any secrets baked into the image at build time?
5. **Multi-stage builds** — Is the final image free of build tooling?
6. **Health checks** — Are they defined?
7. **`.dockerignore`** — Does it exclude unnecessary files?
8. **Compose/K8s** — Review docker-compose.yml, Helm charts, K8s manifests.

## When to Report Nothing

Report nothing if Dockerfiles follow best practices for the stack.  Not every
image needs to be 50MB — flag only issues that affect security, build time,
or operational reliability.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=2.0,
        max_turns=8,
        tags=["devops", "docker"],
    ),
    # ── Language-specific ─────────────────────────────────────────────
    AgentProfile(
        name="rust-audit",
        description="Rust-specific review: unsafe, error handling, performance",
        prompt=_build_prompt("""\
# Rust Audit

Perform a Rust-specific code review.

## What to Focus On

1. **Unsafe code** — Is every `unsafe` block justified?  Are invariants
   documented?  Can any be replaced with safe abstractions?
2. **Error handling** — Is `?` used consistently?  Are error types well-designed
   with context via `thiserror`/`anyhow`?
3. **Ownership patterns** — Unnecessary `.clone()`, `Arc` where `Rc` suffices,
   lifetime issues.
4. **Performance** — Unnecessary allocations, missing zero-copy patterns,
   iterator chains that could be more efficient.
5. **Concurrency** — Correct use of `Send`/`Sync`, `Mutex` vs `RwLock`
   choices, async pitfalls.
6. **API design** — Builder patterns, newtype wrappers, exhaustive enums.
7. **Clippy compliance** — Patterns that Clippy would flag.
8. **Feature flags** — Are they used appropriately?  Any dead features?

## When to Report Nothing

Report nothing if the code follows Rust idioms, has justified unsafe blocks,
and handles errors consistently.  A `.clone()` in non-hot-path code is not
worth reporting.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob,Bash(find *),Bash(cargo metadata *)",
        max_budget_usd=5.0,
        max_turns=15,
        tags=["rust", "audit"],
    ),
    AgentProfile(
        name="python-audit",
        description="Python-specific review: typing, async, packaging, patterns",
        prompt=_build_prompt("""\
# Python Audit

Perform a Python-specific code review.

## What to Focus On

1. **Type annotations** — Completeness, correctness, use of modern syntax (3.10+).
2. **Async patterns** — Mixing sync/async, blocking calls in async context.
3. **Packaging** — pyproject.toml quality, dependency specification, entry points.
4. **Import hygiene** — Circular imports, star imports, lazy imports where needed.
5. **Exception handling** — Bare `except`, overly broad catches, exception chaining.
6. **Data modeling** — Appropriate choice of dataclasses vs attrs vs Pydantic.
7. **Testing patterns** — pytest idioms, fixture usage, parametrize opportunities.
8. **Security** — Use of `eval`/`exec`, `pickle`, `subprocess` with `shell=True`.

## When to Report Nothing

Report nothing if the code follows Python best practices for its version target
and framework.  Missing type hints on internal helpers in a small project is
not worth reporting.

Output as structured JSON."""),
        json_schema=FINDINGS_SCHEMA,
        engine="claude",
        allowed_tools="Read,Grep,Glob,Bash(find *)",
        max_budget_usd=4.0,
        max_turns=12,
        tags=["python", "audit"],
    ),
    # ── Custom (user provides prompt at runtime) ──────────────────────
    AgentProfile(
        name="custom",
        description="Custom prompt — supply your own prompt at runtime",
        prompt="(override this with --param prompt='...' at trigger time)",
        engine="both",
        allowed_tools="Read,Grep,Glob",
        max_budget_usd=5.0,
        max_turns=10,
        tags=["custom"],
    ),
)
