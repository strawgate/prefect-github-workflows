"""
Built-in agent prompt library.

Import this module to populate PROMPT_LIBRARY.  Each profile becomes a
named Prefect deployment when you run deploy.py.

To add a new profile: append another AgentProfile(...) to the register()
call at the bottom and re-run `python deploy.py`.
"""

import json

from prefect_github_workflows.prompts.registry import AgentProfile, register

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
        prompt="""\
Perform a thorough security audit of this codebase.  Look for:

1. Injection vulnerabilities (SQL, command, template, XSS, path traversal)
2. Authentication & authorization flaws (broken access control, missing checks,
   hardcoded credentials, weak session management)
3. Cryptographic issues (weak algorithms, improper key handling, missing encryption)
4. Dependency risks (known CVEs if lockfile present, pinning issues)
5. Information leakage (verbose errors, debug endpoints, stack traces in responses)
6. Unsafe deserialization, SSRF, open redirects
7. Race conditions and TOCTOU bugs

For each finding provide the file, line number if possible, severity, and a
concrete remediation suggestion.  Output as structured JSON.""",
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
        prompt="""\
Scan this repository for leaked secrets, credentials, and sensitive data.  Check:

1. Hardcoded API keys, tokens, passwords in source files
2. .env files committed to the repo
3. Private keys (SSH, TLS, signing keys)
4. Database connection strings with embedded credentials
5. Cloud provider credentials (AWS, GCP, Azure)
6. Webhook URLs with embedded tokens
7. JWT secrets or signing keys
8. Files that should be in .gitignore but aren't

Also review .gitignore for completeness — flag common sensitive patterns that
are missing.  Output as structured JSON.""",
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
        prompt="""\
Hunt for bugs in this codebase.  Focus on:

1. Logic errors: off-by-one, incorrect boolean logic, wrong operator
2. Null/None/undefined handling: missing nil checks, unhandled optionals
3. Error handling: swallowed exceptions, missing error propagation, panics
4. Resource leaks: unclosed files/connections/handles, missing cleanup
5. Concurrency bugs: data races, deadlocks, missing synchronization
6. Type confusion: implicit conversions, wrong type assumptions
7. Edge cases: empty inputs, max values, Unicode, timezone issues
8. API contract violations: wrong HTTP methods, missing validation

Prioritize bugs that would cause runtime failures or data corruption over
style issues.  Output as structured JSON.""",
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
        prompt="""\
Perform a senior-engineer-level code review of this codebase.  Evaluate:

1. Code organization and module boundaries
2. Naming conventions and readability
3. DRY violations and copy-paste code
4. Overly complex functions (cyclomatic complexity)
5. Missing or incorrect type annotations
6. Dead code and unused imports
7. Anti-patterns specific to the language/framework in use
8. Performance anti-patterns (N+1 queries, unnecessary allocations, blocking I/O)

Be opinionated but fair.  Distinguish between "must fix" issues and "consider
improving" suggestions.  Output as structured JSON.""",
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
        prompt="""\
Analyze this codebase for performance issues.  Look for:

1. Hot path inefficiencies: unnecessary allocations, redundant computation
2. I/O patterns: synchronous calls that should be async, missing connection pooling
3. Database access: N+1 queries, missing indexes (from query patterns), large unbounded queries
4. Caching opportunities: repeated expensive computations, cache-friendly data structures
5. Memory usage: large data structures held in memory, missing streaming
6. Serialization overhead: inefficient formats, unnecessary marshalling
7. Startup time: heavy initialization, lazy-loadable components
8. Concurrency: sequential work that could be parallelized

For each issue, estimate the impact (latency, throughput, memory) and suggest
a concrete fix.  Output as structured JSON.""",
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
        prompt="""\
Review the documentation in this repository.  Evaluate:

1. README quality: does it explain what the project does, how to install,
   how to use, how to contribute?
2. API documentation: are public interfaces documented?  Are examples provided?
3. Inline comments: are complex algorithms explained?  Are "why" comments present
   where behavior is non-obvious?
4. Stale docs: do docs reference APIs, flags, or behaviors that no longer exist?
5. Missing docs: are there public modules/functions with no documentation?
6. Changelog/release notes: are they maintained?
7. Architecture docs: is there a high-level overview of the system?
8. Onboarding: could a new contributor get started from the docs alone?

Flag both missing documentation and documentation that is actively misleading.
Output as structured JSON.""",
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
        prompt="""\
Audit the public API surface of this project for documentation completeness.

For every public module, class, function, and method:
1. Does it have a docstring?
2. Does the docstring describe parameters and return values?
3. Are type annotations present and correct?
4. Are there usage examples in docstrings or a docs/ folder?
5. Are error/exception conditions documented?

Produce a file-by-file inventory of undocumented public API surface.
Output as structured JSON.""",
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
        prompt="""\
Analyze test coverage in this codebase WITHOUT running any tests.  For each
source module:

1. Identify the corresponding test file (if any)
2. Assess what is tested: happy paths? edge cases? error paths?
3. Identify what is NOT tested: untested public functions, missing edge cases
4. Flag test quality issues: tests that don't assert anything meaningful,
   overly mocked tests, flaky patterns (sleep, time-dependent, network calls)
5. Look for integration/e2e test gaps

Produce a module-by-module coverage map.  Output as structured JSON.""",
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
        prompt="""\
Review the test suite in this codebase for quality issues.

1. Empty or trivial tests: tests that pass but don't assert anything useful
2. Overmocking: tests that mock so much they don't test real behavior
3. Flaky patterns: time.sleep, hardcoded ports, network calls, order-dependent
4. Missing cleanup: tests that leave state behind (files, DB records, env vars)
5. Assertion quality: using assertEqual vs assertTrue, descriptive failure messages
6. Test organization: consistent naming, proper use of setup/teardown, fixtures
7. Missing negative tests: does the suite test that invalid input is rejected?
8. Test isolation: can tests run in parallel without interfering?

Output as structured JSON.""",
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
        prompt="""\
Evaluate the architecture of this codebase at a system level:

1. Module boundaries: are responsibilities clearly separated?
2. Dependency direction: do dependencies flow in a consistent direction?
   Are there circular dependencies?
3. Coupling: which modules are tightly coupled?  Would changes ripple?
4. Cohesion: do modules contain related functionality, or are they grab-bags?
5. Abstraction layers: are there clear interfaces between layers?
6. Configuration: is config cleanly separated from logic?
7. Error handling strategy: is there a consistent approach across the codebase?
8. Extension points: how easy is it to add new features without modifying
   existing code?

Think like a principal engineer evaluating whether this codebase will scale
as the team grows.  Output as structured JSON.""",
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
        prompt="""\
Audit the dependency tree of this project.

1. Parse the dependency manifest (package.json, Cargo.toml, pyproject.toml,
   go.mod, etc.)
2. Flag dependencies that appear unmaintained (no commits in 2+ years if detectable)
3. Look for dependency duplication (same functionality from multiple packages)
4. Check for overly broad version ranges that could introduce breaking changes
5. Identify dev dependencies that leaked into production deps
6. Flag large/heavy dependencies used for trivial functionality
7. Note any vendored/copied code that should be a proper dependency
8. Review license compatibility if a LICENSE file is present

Output as structured JSON.""",
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
        prompt="""\
Review the CI/CD configuration in this repository.  Check:

1. Pipeline files: .github/workflows/*.yml, .gitlab-ci.yml, Jenkinsfile, etc.
2. Security: are secrets handled correctly?  Are actions/images pinned by SHA?
3. Efficiency: are there unnecessary steps?  Is caching used effectively?
4. Reliability: are there retry mechanisms?  Timeout settings?
5. Coverage: does CI run tests, linting, type checking, security scans?
6. Branch protection: does the config enforce reviews before merge?
7. Build reproducibility: are builds deterministic?
8. Deployment safety: are there staging/canary steps before production?

Output as structured JSON.""",
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
        prompt="""\
Review all Dockerfiles and container configuration in this repository.

1. Base image: is it minimal?  Is it pinned to a specific digest/version?
2. Layer optimization: are layers ordered for maximum cache efficiency?
3. Security: does the container run as root?  Are unnecessary packages installed?
4. Secrets: are any secrets baked into the image or passed at build time?
5. Multi-stage builds: is the final image free of build tooling?
6. Health checks: are they defined?
7. .dockerignore: does it exclude unnecessary files?
8. Compose/K8s: review docker-compose.yml, Helm charts, K8s manifests for issues

Output as structured JSON.""",
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
        prompt="""\
Perform a Rust-specific code review.  Focus on:

1. Unsafe code: is every `unsafe` block justified?  Are invariants documented?
2. Error handling: is `?` used consistently?  Are error types well-designed?
3. Ownership patterns: unnecessary clones, Arc where Rc suffices, lifetime issues
4. Performance: unnecessary allocations, missing zero-copy patterns, iterator chains
   that could be more efficient
5. Concurrency: correct use of Send/Sync, Mutex vs RwLock choices, async pitfalls
6. API design: builder patterns, newtype wrappers, exhaustive enums
7. Clippy compliance: patterns that Clippy would flag
8. Feature flags: are they used appropriately?  Any dead features?

Output as structured JSON.""",
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
        prompt="""\
Perform a Python-specific code review.  Focus on:

1. Type annotations: completeness, correctness, use of modern syntax (3.10+)
2. Async patterns: mixing sync/async, blocking calls in async context
3. Packaging: pyproject.toml quality, dependency specification, entry points
4. Import hygiene: circular imports, star imports, lazy imports where appropriate
5. Exception handling: bare except, overly broad catches, exception chaining
6. Data classes vs attrs vs Pydantic: appropriate model choice
7. Testing patterns: pytest idioms, fixture usage, parametrize opportunities
8. Security: use of eval/exec, pickle, subprocess with shell=True

Output as structured JSON.""",
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
