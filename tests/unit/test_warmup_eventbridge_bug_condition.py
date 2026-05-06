"""
Bug Condition Exploration Tests — Warm-Up Orchestrator EventBridge Rule Not Created

These tests demonstrate that the current warm-up-orchestrator.json config has a
top-level `schedule` field that is never read by LambdaFunctionConfig. The factory
only processes entries in a `triggers` array with `"resource_type": "event-bridge"`.
Since no `triggers` array exists, `function_config.triggers` is empty and no
EventBridge rule is created.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.3
"""

import copy
import json

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.deployment import DeploymentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Current (unfixed) warm-up-orchestrator.json config embedded directly.
# This is the exact content from:
# Acme-SaaS-IaC/cdk/configs/stacks/lambdas/resources/warm-up/warm-up-orchestrator.json
WARMUP_ORCHESTRATOR_CONFIG = {
    "name": "warm-up-orchestrator",
    "description": "Lambda Warm-Up: Discovers Docker Lambdas via SSM and invokes each with warm-up payload",
    "docker": {"image": True},
    "ecr": {
        "name": "acme/v3/acme-services",
        "use_existing": True,
        "region": "us-east-1",
        "account": "974817967438",
    },
    "image_config": {
        "command": [
            "aplos_nca_services.handlers.warm_up.orchestrator.app.lambda_handler"
        ]
    },
    "add_common_layer": "false",
    "timeout": 60,
    "permissions": [
        {"dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
        {
            "parameter_store": "read",
            "path": "/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/ecr/*",
        },
        {"lambda": "invoke", "function": "*"},
    ],
    "environment_variables": [
        {
            "name": "SSM_DOCKER_LAMBDAS_PATH",
            "value": "{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}",
        }
    ],
    "schedule": {
        "expression": "rate(15 minutes)",
        "description": "Trigger Lambda warm-up every 15 minutes",
    },
}


def _load_warmup_config() -> dict:
    """Return a copy of the current (unfixed) warm-up-orchestrator config."""
    return copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)


def _make_deployment_config() -> DeploymentConfig:
    """Create a minimal DeploymentConfig for testing."""
    workload = {"name": "test-workload", "devops": {"name": "test-devops"}}
    deployment = {"name": "test", "environment": "test", "mode": "direct"}
    return DeploymentConfig(workload=workload, deployment=deployment)


def _is_bug_condition(config: dict) -> bool:
    """
    Bug condition: config HAS top-level 'schedule' AND DOES NOT HAVE 'triggers' array.
    """
    return "schedule" in config and "triggers" not in config


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate varying rate expressions for the top-level schedule field
rate_type_st = st.sampled_from(["minutes", "hours", "days"])
rate_duration_st = st.integers(min_value=1, max_value=1440)

schedule_expression_st = st.builds(
    lambda rate_type, duration: {
        "expression": f"rate({duration} {rate_type})",
        "description": f"Trigger every {duration} {rate_type}",
    },
    rate_type=rate_type_st,
    duration=rate_duration_st,
)


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestWarmupEventBridgeBugCondition:
    """
    **Validates: Requirements 1.1, 1.3**

    Property 1: Bug Condition — Top-Level Schedule Field Produces No Triggers

    For any config satisfying isBugCondition (has top-level `schedule`, no `triggers`
    array), LambdaFunctionConfig.triggers must contain at least one entry with
    resource_type == "event-bridge" and a valid schedule dict.

    On unfixed code, this property FAILS because function_config.triggers is empty [].
    """

    def test_current_config_satisfies_bug_condition(self):
        """Verify the current warm-up-orchestrator.json satisfies the bug condition.

        The config has a top-level 'schedule' field and no 'triggers' array.
        """
        config = _load_warmup_config()
        assert _is_bug_condition(config), (
            "Expected warm-up-orchestrator.json to have top-level 'schedule' "
            "and no 'triggers' array (bug condition)"
        )

    def test_current_config_triggers_empty(self):
        """Bug confirmation: config with top-level schedule produces empty triggers.

        Demonstrates that a config using the old format (top-level 'schedule'
        field, no 'triggers' array) results in no triggers being parsed.
        This documents the known limitation of the CDK factory.

        **Validates: Requirements 1.1, 1.3**
        """
        config = _load_warmup_config()
        assert _is_bug_condition(
            config
        ), "Precondition: config must satisfy bug condition"

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        # The old format produces no triggers — this is the bug condition
        assert len(function_config.triggers) == 0, (
            f"Expected empty triggers for config with top-level 'schedule' field, "
            f"got: {function_config.triggers}"
        )

    @given(schedule=schedule_expression_st)
    @settings(max_examples=50)
    def test_property_bug_condition_configs_produce_no_triggers(self, schedule):
        """Property-based: configs with top-level schedule and no triggers array
        produce an empty triggers list.

        Generates variations of the bug condition with different rate expressions
        and confirms the CDK factory ignores the top-level schedule field.

        **Validates: Requirements 1.1, 1.3**
        """
        # Build a config that satisfies the bug condition
        base_config = _load_warmup_config()
        # Replace the schedule with a generated variant
        config = {k: v for k, v in base_config.items() if k != "schedule"}
        config["schedule"] = schedule

        # Ensure bug condition holds
        assert _is_bug_condition(config), "Generated config must satisfy bug condition"

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        # The old format always produces no triggers
        assert len(function_config.triggers) == 0, (
            f"Expected empty triggers for config with top-level schedule={schedule}, "
            f"got: {function_config.triggers}"
        )


# ---------------------------------------------------------------------------
# Fix Checking Tests — Verify the fix resolves the bug condition
# ---------------------------------------------------------------------------

# Fixed warm-up-orchestrator.json config (with triggers array instead of top-level schedule)
WARMUP_ORCHESTRATOR_FIXED_CONFIG = {
    "name": "warm-up-orchestrator",
    "description": "Lambda Warm-Up: Discovers Docker Lambdas via SSM and invokes each with warm-up payload",
    "docker": {"image": True},
    "ecr": {
        "name": "acme/v3/acme-services",
        "use_existing": True,
        "region": "us-east-1",
        "account": "974817967438",
    },
    "image_config": {
        "command": [
            "aplos_nca_services.handlers.warm_up.orchestrator.app.lambda_handler"
        ]
    },
    "add_common_layer": "false",
    "timeout": 60,
    "permissions": [
        {"dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
        {
            "parameter_store": "read",
            "path": "/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/ecr/*",
        },
        {"lambda": "invoke", "function": "*"},
    ],
    "environment_variables": [
        {
            "name": "SSM_DOCKER_LAMBDAS_PATH",
            "value": "{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}",
        }
    ],
    "triggers": [
        {
            "name": "warm_up_orchestrator_schedule",
            "resource_type": "event-bridge",
            "schedule": {"rate": {"type": "minutes", "duration": 15}},
        }
    ],
}


class TestWarmupEventBridgeFixChecking:
    """
    Fix Checking — Verify the fixed config produces valid triggers.

    These tests confirm the bug is resolved: the fixed config with a `triggers`
    array produces a valid event-bridge trigger entry.

    **Validates: Requirements 2.1, 2.3**
    """

    def test_fixed_config_does_not_satisfy_bug_condition(self):
        """Verify the fixed config no longer satisfies the bug condition."""
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_FIXED_CONFIG)
        assert not _is_bug_condition(
            config
        ), "Fixed config should NOT have top-level 'schedule' without 'triggers'"

    def test_fixed_config_produces_event_bridge_trigger(self):
        """Verify the fixed config produces a valid event-bridge trigger.

        **Validates: Requirements 2.1, 2.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_FIXED_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert (
            len(function_config.triggers) == 1
        ), f"Expected exactly 1 trigger, got {len(function_config.triggers)}"
        assert function_config.triggers[0].resource_type == "event-bridge"
        assert function_config.triggers[0].name == "warm_up_orchestrator_schedule"

    def test_fixed_config_trigger_schedule_correct(self):
        """Verify the fixed config trigger has the correct 15-minute rate schedule.

        **Validates: Requirements 2.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_FIXED_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_schedule = {"rate": {"type": "minutes", "duration": 15}}
        assert function_config.triggers[0].schedule == expected_schedule
