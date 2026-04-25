"""
Bug Condition Exploration Tests — Stable ID Changes When Stage Is Renamed

These tests demonstrate that the current `PipelineStageConfig.stable_id`
derives the construct ID directly from the stage name. When a stage is
renamed but its stacks remain the same, `stable_id` changes — causing
CloudFormation logical ID drift, "already exists" errors, and potential
data loss from stateful resource recreation.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 2.1, 2.2
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.pipeline_stage import PipelineStageConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stage(name: str, stacks: list[dict] | None = None) -> PipelineStageConfig:
    """Create a minimal PipelineStageConfig with the given name and stacks."""
    stage_dict: dict = {"name": name, "enabled": True}
    if stacks is not None:
        stage_dict["stacks"] = stacks
    workload: dict = {"name": "test-workload", "stacks": stacks or []}
    return PipelineStageConfig(stage=stage_dict, workload=workload)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Stage names: alphanumeric with hyphens, 2-20 chars
stage_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-]{1,19}", fullmatch=True)

# A fixed stack list to use across all generated name pairs
_FIXED_STACKS = [
    {"name": "lambda-stack-a", "module": "lambda_stack", "enabled": True},
    {"name": "lambda-stack-b", "module": "lambda_stack", "enabled": True},
]


# ---------------------------------------------------------------------------
# Bug Condition Property Test
# ---------------------------------------------------------------------------


class TestBugConditionStableIdChangesOnRename:
    """
    **Validates: Requirements 1.1, 2.1, 2.2**

    Property 1: Bug Condition — For two stages with different names but
    identical stacks, stable_id MUST be the same.

    On unfixed code, stable_id = re.sub(r"[^a-zA-Z0-9-]", "", self.name),
    so different names produce different IDs. This test WILL FAIL, confirming
    the bug exists.
    """

    @given(
        name_a=stage_name_st,
        name_b=stage_name_st,
    )
    @settings(max_examples=100)
    def test_stable_id_same_for_different_names_same_stacks(self, name_a, name_b):
        """stable_id must be identical when only the stage name differs."""
        # Filter out cases where names sanitize to the same value
        sanitized_a = re.sub(r"[^a-zA-Z0-9-]", "", name_a)
        sanitized_b = re.sub(r"[^a-zA-Z0-9-]", "", name_b)
        if sanitized_a == sanitized_b:
            return  # Skip — not a rename scenario

        stage_a = _make_stage(name_a, stacks=_FIXED_STACKS)
        stage_b = _make_stage(name_b, stacks=_FIXED_STACKS)

        assert stage_a.stable_id == stage_b.stable_id, (
            f"Bug confirmed: stable_id differs when stage is renamed. "
            f"name_a='{name_a}' -> stable_id='{stage_a.stable_id}', "
            f"name_b='{name_b}' -> stable_id='{stage_b.stable_id}'. "
            f"Stacks are identical: {[s['name'] for s in _FIXED_STACKS]}"
        )
