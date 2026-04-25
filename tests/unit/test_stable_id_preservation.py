"""
Preservation Property Tests — Unchanged Stages Produce Same Stable ID

These tests verify baseline behavior that MUST be preserved after the fix:
1. Stack-less stages return sanitized name (fallback path)
2. Explicit construct_id overrides everything
3. name property still returns the display name
4. Other properties (wave_name, enabled, description) are unaffected

All tests are EXPECTED TO PASS on UNFIXED code — they capture behavior to preserve.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

import re

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.configurations.pipeline_stage import PipelineStageConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stage(
    name: str,
    stacks: list[dict] | None = None,
    construct_id: str | None = None,
    wave: str | None = None,
    enabled: bool = True,
    description: str | None = None,
) -> PipelineStageConfig:
    """Create a minimal PipelineStageConfig."""
    stage_dict: dict = {"name": name, "enabled": enabled}
    if stacks is not None:
        stage_dict["stacks"] = stacks
    if construct_id is not None:
        stage_dict["construct_id"] = construct_id
    if wave is not None:
        stage_dict["wave"] = wave
    if description is not None:
        stage_dict["description"] = description
    workload: dict = {"name": "test-workload", "stacks": stacks or []}
    return PipelineStageConfig(stage=stage_dict, workload=workload)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Stage names: alphanumeric with hyphens, 2-20 chars
stage_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-]{1,19}", fullmatch=True)

# Construct IDs: alphanumeric with hyphens, 2-20 chars
construct_id_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-]{1,19}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property Test: Stack-less stages use sanitized name
# ---------------------------------------------------------------------------


class TestPreservationStacklessStages:
    """
    **Validates: Requirements 3.1, 3.2**

    Property 2a: For stages with NO stacks (build-only), stable_id must
    equal re.sub(r"[^a-zA-Z0-9-]", "", name) — the sanitized name fallback.
    This must pass on both unfixed and fixed code.
    """

    @given(name=stage_name_st)
    @settings(max_examples=100)
    def test_stackless_stage_stable_id_is_sanitized_name(self, name):
        """Stack-less stages: stable_id == sanitized name."""
        stage = _make_stage(name, stacks=[])
        expected = re.sub(r"[^a-zA-Z0-9-]", "", name)
        assert stage.stable_id == expected, (
            f"Stack-less stage stable_id mismatch: "
            f"name='{name}', expected='{expected}', got='{stage.stable_id}'"
        )


# ---------------------------------------------------------------------------
# Property Test: Explicit construct_id overrides everything (post-fix)
# ---------------------------------------------------------------------------


class TestPreservationExplicitConstructId:
    """
    **Validates: Requirements 3.2, 3.3**

    Property 2b: When construct_id is set in config, stable_id must return
    the sanitized construct_id regardless of name or stacks.

    """

    @given(name=stage_name_st, cid=construct_id_st)
    @settings(max_examples=100)
    def test_explicit_construct_id_overrides(self, name, cid):
        """Explicit construct_id always takes precedence."""
        stage = _make_stage(name, construct_id=cid)
        expected = re.sub(r"[^a-zA-Z0-9-]", "", cid)
        assert stage.stable_id == expected, (
            f"Explicit construct_id not used: "
            f"construct_id='{cid}', expected='{expected}', got='{stage.stable_id}'"
        )


# ---------------------------------------------------------------------------
# Example Tests: name property returns display name
# ---------------------------------------------------------------------------


class TestPreservationNameProperty:
    """
    **Validates: Requirements 3.4, 3.5**

    The name property must always return the raw stage name from config,
    regardless of stable_id logic.
    """

    def test_name_returns_raw_stage_name(self):
        """name property returns the original display name."""
        stage = _make_stage("compute")
        assert stage.name == "compute"

    def test_name_returns_renamed_stage(self):
        """name property returns the new name after rename."""
        stage = _make_stage("lambdas")
        assert stage.name == "lambdas"

    def test_name_with_special_chars(self):
        """name property returns name with special characters as-is."""
        stage = _make_stage("persistent-resources")
        assert stage.name == "persistent-resources"


# ---------------------------------------------------------------------------
# Example Tests: Other properties unaffected
# ---------------------------------------------------------------------------


class TestPreservationOtherProperties:
    """
    **Validates: Requirements 3.4, 3.5**

    wave_name, enabled, and description must be unaffected by stable_id changes.
    """

    def test_wave_name_preserved(self):
        """wave_name returns the configured wave."""
        stage = _make_stage("compute", wave="deploy-wave")
        assert stage.wave_name == "deploy-wave"

    def test_enabled_preserved(self):
        """enabled returns the configured value."""
        stage = _make_stage("compute", enabled=True)
        assert stage.enabled is True

    def test_disabled_preserved(self):
        """disabled stage returns False."""
        stage = _make_stage("compute", enabled=False)
        assert stage.enabled is False

    def test_description_preserved(self):
        """description returns the configured value."""
        stage = _make_stage("compute", description="Lambda functions")
        assert stage.description == "Lambda functions"

    def test_description_none_when_not_set(self):
        """description returns None when not configured."""
        stage = _make_stage("compute")
        assert stage.description is None
