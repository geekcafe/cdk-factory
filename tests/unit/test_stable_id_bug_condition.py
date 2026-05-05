"""
Bug Condition Exploration Tests — Stable ID Changes When Stacks Are Added/Removed

These tests demonstrate that the `PipelineStageConfig.stable_id` must NOT
change when stacks are added to or removed from a stage. The stage construct
ID is part of every CloudFormation logical ID for resources within the stage.
If it changes, all existing resources get new logical IDs and CloudFormation
tries to recreate them — causing "already exists" errors and potential data loss.

The fix uses the stage name as the stable_id (immune to stack list changes).
Stage renames are handled via explicit `construct_id` override.

Validates: Requirements 1.1, 2.1, 2.2
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
) -> PipelineStageConfig:
    """Create a minimal PipelineStageConfig with the given name and stacks."""
    stage_dict: dict = {"name": name, "enabled": True}
    if stacks is not None:
        stage_dict["stacks"] = stacks
    if construct_id is not None:
        stage_dict["construct_id"] = construct_id
    workload: dict = {"name": "test-workload", "stacks": stacks or []}
    return PipelineStageConfig(stage=stage_dict, workload=workload)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Stage names: alphanumeric with hyphens, 2-20 chars
stage_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-]{1,19}", fullmatch=True)

# Stack configs: simple dicts with unique names
stack_config_st = st.fixed_dictionaries(
    {
        "name": st.from_regex(r"[a-z][a-z0-9\-]{2,15}", fullmatch=True),
        "module": st.just("lambda_stack"),
        "enabled": st.just(True),
    }
)


# ---------------------------------------------------------------------------
# Bug Condition Property Test: Adding stacks must not change stable_id
# ---------------------------------------------------------------------------


class TestBugConditionStableIdChangesOnStackAddition:
    """
    **Validates: Requirements 1.1, 2.1, 2.2**

    Property 1: Bug Condition — Adding a stack to a stage MUST NOT change
    the stable_id. The stable_id must depend only on the stage name (or
    explicit construct_id), never on the stack list.

    On the old hash-based code, adding a stack changed the hash and broke
    all existing resources. This test confirms the fix works.
    """

    @given(
        name=stage_name_st,
        original_stacks=st.lists(stack_config_st, min_size=1, max_size=5),
        new_stack=stack_config_st,
    )
    @settings(max_examples=100)
    def test_stable_id_unchanged_when_stack_added(
        self, name, original_stacks, new_stack
    ):
        """stable_id must be identical before and after adding a stack."""
        # Ensure new_stack name doesn't collide with existing
        existing_names = {s["name"] for s in original_stacks}
        assume(new_stack["name"] not in existing_names)

        stage_before = _make_stage(name, stacks=original_stacks)
        stage_after = _make_stage(name, stacks=original_stacks + [new_stack])

        assert stage_before.stable_id == stage_after.stable_id, (
            f"Bug: stable_id changed when stack was added to stage '{name}'. "
            f"Before: '{stage_before.stable_id}', After: '{stage_after.stable_id}'. "
            f"Added stack: '{new_stack['name']}'"
        )

    @given(
        name=stage_name_st,
        stacks=st.lists(stack_config_st, min_size=2, max_size=5),
    )
    @settings(max_examples=100)
    def test_stable_id_unchanged_when_stack_removed(self, name, stacks):
        """stable_id must be identical before and after removing a stack."""
        # Ensure unique stack names
        seen = set()
        unique_stacks = []
        for s in stacks:
            if s["name"] not in seen:
                seen.add(s["name"])
                unique_stacks.append(s)
        assume(len(unique_stacks) >= 2)

        stage_before = _make_stage(name, stacks=unique_stacks)
        stage_after = _make_stage(name, stacks=unique_stacks[:-1])

        assert stage_before.stable_id == stage_after.stable_id, (
            f"Bug: stable_id changed when stack was removed from stage '{name}'. "
            f"Before: '{stage_before.stable_id}', After: '{stage_after.stable_id}'. "
            f"Removed stack: '{unique_stacks[-1]['name']}'"
        )


# ---------------------------------------------------------------------------
# Property Test: Stage rename with construct_id override is safe
# ---------------------------------------------------------------------------


class TestStageRenameWithConstructIdOverride:
    """
    **Validates: Requirements 2.1, 2.2**

    Property 2: When a stage is renamed, using construct_id to pin the old
    identity ensures stable_id doesn't change.
    """

    @given(
        old_name=stage_name_st,
        new_name=stage_name_st,
    )
    @settings(max_examples=100)
    def test_construct_id_preserves_identity_across_rename(self, old_name, new_name):
        """construct_id override keeps stable_id constant across renames."""
        assume(old_name != new_name)

        # Original stage
        stage_old = _make_stage(old_name, stacks=[])

        # Renamed stage with construct_id pinned to old name
        old_stable_id = stage_old.stable_id
        stage_new = _make_stage(new_name, stacks=[], construct_id=old_stable_id)

        assert stage_new.stable_id == old_stable_id, (
            f"construct_id override failed: "
            f"old_name='{old_name}', new_name='{new_name}', "
            f"expected='{old_stable_id}', got='{stage_new.stable_id}'"
        )
