"""Tests for the prompt registry and library."""

from prefect_github_workflows.prompts.registry import PROMPT_LIBRARY, AgentProfile, register


def test_agent_profile_deployment_parameters():
    profile = AgentProfile(
        name="test-profile",
        description="A test profile",
        prompt="Review this code",
        engine="claude",
        allowed_tools="Read,Grep",
        max_budget_usd=2.0,
        max_turns=5,
    )
    params = profile.deployment_parameters()
    assert params["prompt"] == "Review this code"
    assert params["engine"] == "claude"
    assert params["allowed_tools"] == "Read,Grep"
    assert params["max_budget_usd"] == 2.0
    assert params["max_turns"] == 5


def test_agent_profile_defaults():
    profile = AgentProfile(
        name="minimal",
        description="Minimal profile",
        prompt="Do something",
    )
    assert profile.engine == "both"
    assert profile.allowed_tools == "Read,Grep,Glob"
    assert profile.max_budget_usd == 5.0
    assert profile.max_turns == 10
    assert profile.cron is None
    assert profile.tags == []
    assert profile.json_schema is None


def test_prompt_library_populated():
    """The library module should register profiles on import."""
    # Force import of library to trigger registration
    import prefect_github_workflows.prompts.library  # noqa: F401

    assert len(PROMPT_LIBRARY) > 0
    names = [p.name for p in PROMPT_LIBRARY]
    assert "security-audit" in names
    assert "bug-hunt" in names


def test_register_adds_profiles():
    initial_count = len(PROMPT_LIBRARY)
    test_profile = AgentProfile(
        name="test-transient",
        description="Transient test profile",
        prompt="Test prompt",
    )
    register(test_profile)
    assert len(PROMPT_LIBRARY) == initial_count + 1
    # Clean up
    PROMPT_LIBRARY.pop()


def test_all_profiles_have_required_fields():
    """Every registered profile should have non-empty name, description, prompt."""
    import prefect_github_workflows.prompts.library  # noqa: F401

    for profile in PROMPT_LIBRARY:
        assert profile.name, "Profile has empty name"
        assert profile.description, f"Profile {profile.name} has empty description"
        assert profile.prompt, f"Profile {profile.name} has empty prompt"
        assert profile.engine in ("claude", "copilot", "both"), (
            f"Profile {profile.name} has invalid engine: {profile.engine}"
        )
        assert profile.max_budget_usd > 0, f"Profile {profile.name} has non-positive budget"
        assert profile.max_turns > 0, f"Profile {profile.name} has non-positive max_turns"
