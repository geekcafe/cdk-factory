"""
Preservation Property Tests — Warm-Up Orchestrator EventBridge Rule Fix

These tests verify that non-trigger config fields are preserved correctly through
LambdaFunctionConfig parsing. They establish a baseline on UNFIXED code to ensure
the fix does not introduce regressions.

Additionally, they verify that existing event-bridge configs (execution-aggregator)
continue to parse correctly.

These tests MUST PASS on unfixed code.

Validates: Requirements 3.1, 3.2, 3.3
"""

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.resources.lambda_triggers import LambdaTriggersConfig
from cdk_factory.configurations.deployment import DeploymentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Current (unfixed) warm-up-orchestrator.json config
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

# execution-aggregator.json config (working reference with triggers array)
EXECUTION_AGGREGATOR_CONFIG = {
    "name": "execution-aggregator",
    "description": "Metrics: Execution Metrics Aggregator - Collects execution status counts across all tenants and persists MetricsSnapshot records. Triggered by EventBridge on a 15-minute schedule.",
    "docker": {"image": True},
    "ecr": {
        "name": "acme/v3/acme-services",
        "use_existing": True,
        "region": "us-east-1",
        "account": "974817967438",
    },
    "image_config": {
        "command": [
            "aplos_nca_services.handlers.metrics.execution_aggregator.app.lambda_handler"
        ]
    },
    "add_common_layer": "false",
    "timeout": 180,
    "triggers": [
        {
            "name": "execution_metrics_aggregator_schedule",
            "resource_type": "event-bridge",
            "schedule": {"rate": {"type": "minutes", "duration": 15}},
        }
    ],
    "permissions": [
        {"dynamodb": "read", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
        {"dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
    ],
}


def _make_deployment_config() -> DeploymentConfig:
    """Create a minimal DeploymentConfig for testing."""
    workload = {"name": "test-workload", "devops": {"name": "test-devops"}}
    deployment = {"name": "test", "environment": "test", "mode": "direct"}
    return DeploymentConfig(workload=workload, deployment=deployment)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate valid triggers arrays with event-bridge entries
rate_type_st = st.sampled_from(["minutes", "hours", "days"])
rate_duration_st = st.integers(min_value=1, max_value=1440)

trigger_entry_st = st.builds(
    lambda name_suffix, rate_type, duration: {
        "name": f"warm_up_orchestrator_{name_suffix}",
        "resource_type": "event-bridge",
        "schedule": {"rate": {"type": rate_type, "duration": duration}},
    },
    name_suffix=st.sampled_from(["schedule", "timer", "cron", "periodic"]),
    rate_type=rate_type_st,
    duration=rate_duration_st,
)

triggers_array_st = st.lists(trigger_entry_st, min_size=1, max_size=3)


# ---------------------------------------------------------------------------
# Preservation Tests
# ---------------------------------------------------------------------------


class TestWarmupPreservationProperties:
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 2: Preservation — Non-Trigger Config Fields Unchanged

    Verifies that non-trigger fields (name, description, timeout, permissions,
    environment_variables, docker, ecr, image_config, add_common_layer) are
    correctly preserved through LambdaFunctionConfig parsing regardless of
    whether a triggers array is present.
    """

    def test_baseline_name_preserved(self):
        """Verify warm-up-orchestrator name is correctly parsed from config.

        **Validates: Requirements 3.2, 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.name == "warm-up-orchestrator"

    def test_baseline_timeout_preserved(self):
        """Verify warm-up-orchestrator timeout is correctly parsed from config.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        # timeout returns aws_cdk.Duration, check the to_seconds value
        assert function_config.timeout.to_seconds() == 60

    def test_baseline_permissions_preserved(self):
        """Verify warm-up-orchestrator permissions are correctly parsed from config.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_permissions = [
            {"dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
            {
                "parameter_store": "read",
                "path": "/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/ecr/*",
            },
            {"lambda": "invoke", "function": "*"},
        ]
        assert function_config.permissions == expected_permissions

    def test_baseline_environment_variables_preserved(self):
        """Verify warm-up-orchestrator environment_variables are correctly parsed.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_env_vars = [
            {
                "name": "SSM_DOCKER_LAMBDAS_PATH",
                "value": "{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}",
            }
        ]
        assert function_config.environment_variables == expected_env_vars

    def test_baseline_add_common_layer_preserved(self):
        """Verify add_common_layer is correctly parsed as False from 'false' string.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.add_common_layer is False

    @given(triggers=triggers_array_st)
    @settings(max_examples=50)
    def test_property_adding_triggers_preserves_name(self, triggers):
        """Property: Adding a triggers array does NOT alter the parsed name.

        **Validates: Requirements 3.2, 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        # Remove the top-level schedule and add a triggers array
        config.pop("schedule", None)
        config["triggers"] = triggers

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.name == "warm-up-orchestrator"

    @given(triggers=triggers_array_st)
    @settings(max_examples=50)
    def test_property_adding_triggers_preserves_timeout(self, triggers):
        """Property: Adding a triggers array does NOT alter the parsed timeout.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        config.pop("schedule", None)
        config["triggers"] = triggers

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.timeout.to_seconds() == 60

    @given(triggers=triggers_array_st)
    @settings(max_examples=50)
    def test_property_adding_triggers_preserves_permissions(self, triggers):
        """Property: Adding a triggers array does NOT alter the parsed permissions.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        config.pop("schedule", None)
        config["triggers"] = triggers

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_permissions = [
            {"dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}"},
            {
                "parameter_store": "read",
                "path": "/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/ecr/*",
            },
            {"lambda": "invoke", "function": "*"},
        ]
        assert function_config.permissions == expected_permissions

    @given(triggers=triggers_array_st)
    @settings(max_examples=50)
    def test_property_adding_triggers_preserves_environment_variables(self, triggers):
        """Property: Adding a triggers array does NOT alter the parsed env vars.

        **Validates: Requirements 3.3**
        """
        config = copy.deepcopy(WARMUP_ORCHESTRATOR_CONFIG)
        config.pop("schedule", None)
        config["triggers"] = triggers

        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_env_vars = [
            {
                "name": "SSM_DOCKER_LAMBDAS_PATH",
                "value": "{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}",
            }
        ]
        assert function_config.environment_variables == expected_env_vars


class TestExecutionAggregatorPreservation:
    """
    **Validates: Requirements 3.1**

    Additional Preservation Check — Existing event-bridge configs are unaffected.

    Verifies that execution-aggregator.json (which already uses the correct
    triggers array format) continues to parse correctly through LambdaFunctionConfig.
    """

    def test_execution_aggregator_triggers_parsed_correctly(self):
        """Verify execution-aggregator triggers are parsed with correct resource_type.

        **Validates: Requirements 3.1**
        """
        config = copy.deepcopy(EXECUTION_AGGREGATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert len(function_config.triggers) == 1
        assert function_config.triggers[0].resource_type == "event-bridge"

    def test_execution_aggregator_trigger_name(self):
        """Verify execution-aggregator trigger name is parsed correctly.

        **Validates: Requirements 3.1**
        """
        config = copy.deepcopy(EXECUTION_AGGREGATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert (
            function_config.triggers[0].name == "execution_metrics_aggregator_schedule"
        )

    def test_execution_aggregator_trigger_schedule(self):
        """Verify execution-aggregator trigger schedule is parsed correctly.

        **Validates: Requirements 3.1**
        """
        config = copy.deepcopy(EXECUTION_AGGREGATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        expected_schedule = {"rate": {"type": "minutes", "duration": 15}}
        assert function_config.triggers[0].schedule == expected_schedule

    def test_execution_aggregator_name_preserved(self):
        """Verify execution-aggregator name is correctly parsed.

        **Validates: Requirements 3.1**
        """
        config = copy.deepcopy(EXECUTION_AGGREGATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.name == "execution-aggregator"

    def test_execution_aggregator_timeout_preserved(self):
        """Verify execution-aggregator timeout is correctly parsed.

        **Validates: Requirements 3.1**
        """
        config = copy.deepcopy(EXECUTION_AGGREGATOR_CONFIG)
        deployment = _make_deployment_config()
        function_config = LambdaFunctionConfig(config=config, deployment=deployment)

        assert function_config.timeout.to_seconds() == 180
