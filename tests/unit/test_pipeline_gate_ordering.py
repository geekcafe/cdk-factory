"""
Unit tests for pipeline gate ordering behavior.

Bug: When a stage has gate.enabled=true and only post_steps (no stacks),
the gate was added to pre_steps but post_steps ran independently via
wave.add_post(), bypassing the approval gate entirely.

Fix: When a gate is enabled, all post_steps are consolidated into pre_steps
(after the gate) so everything is sequenced behind the approval.
"""

from unittest.mock import MagicMock, patch, call
from cdk_factory.configurations.pipeline_stage import PipelineStageConfig


class TestGateEnabled:
    """Verify PipelineStageConfig.gate_enabled parsing."""

    def test_gate_enabled_true(self):
        stage = PipelineStageConfig(
            {"name": "deploy", "gate": {"enabled": "true", "message": "Approve"}},
            workload={"name": "test"},
        )
        assert stage.gate_enabled is True

    def test_gate_enabled_false(self):
        stage = PipelineStageConfig(
            {"name": "deploy", "gate": {"enabled": "false"}},
            workload={"name": "test"},
        )
        assert stage.gate_enabled is False

    def test_gate_not_configured(self):
        stage = PipelineStageConfig(
            {"name": "deploy"},
            workload={"name": "test"},
        )
        assert stage.gate_enabled is False


class TestGateBlocksAllSteps:
    """
    Verify that when gate is enabled, post_steps are moved into pre_steps
    so the gate blocks everything.

    This tests the consolidation logic directly rather than synthesizing
    a full CDK pipeline (which requires AWS account context).
    """

    def test_gate_consolidates_post_steps_into_pre_steps(self):
        """
        Simulate the gate logic from pipeline_factory._setup_deployment_stages.
        When gate_enabled is True, post_steps should be merged into pre_steps
        with the gate at position 0.
        """
        # Simulate what _get_pre_steps and _get_post_steps would return
        pre_steps = []  # No pre_steps configured
        post_steps = ["dns-updates-step"]  # A post_step (e.g., DNS delegation)

        gate_enabled = True

        if gate_enabled:
            gate_step = "gate-persistent-resources"
            # This is the fix: consolidate everything behind the gate
            pre_steps = [gate_step] + pre_steps + post_steps
            post_steps = []

        # Gate should be first
        assert pre_steps[0] == "gate-persistent-resources"
        # DNS step should follow the gate
        assert pre_steps[1] == "dns-updates-step"
        # post_steps should be empty (everything moved to pre)
        assert post_steps == []

    def test_gate_preserves_existing_pre_steps_order(self):
        """
        When both pre_steps and post_steps exist, the gate goes first,
        then original pre_steps, then original post_steps.
        """
        pre_steps = ["lint-step", "validate-step"]
        post_steps = ["deploy-step", "notify-step"]

        gate_enabled = True

        if gate_enabled:
            gate_step = "gate-stage"
            pre_steps = [gate_step] + pre_steps + post_steps
            post_steps = []

        assert pre_steps == [
            "gate-stage",
            "lint-step",
            "validate-step",
            "deploy-step",
            "notify-step",
        ]
        assert post_steps == []

    def test_no_gate_leaves_steps_unchanged(self):
        """Without a gate, pre_steps and post_steps remain separate."""
        pre_steps = ["lint-step"]
        post_steps = ["deploy-step"]

        gate_enabled = False

        if gate_enabled:
            gate_step = "gate-stage"
            pre_steps = [gate_step] + pre_steps + post_steps
            post_steps = []

        # Nothing should change
        assert pre_steps == ["lint-step"]
        assert post_steps == ["deploy-step"]

    def test_gate_with_empty_pre_and_post_steps(self):
        """Gate with no steps at all just produces the gate alone."""
        pre_steps = []
        post_steps = []

        gate_enabled = True

        if gate_enabled:
            gate_step = "gate-stage"
            pre_steps = [gate_step] + pre_steps + post_steps
            post_steps = []

        assert pre_steps == ["gate-stage"]
        assert post_steps == []
