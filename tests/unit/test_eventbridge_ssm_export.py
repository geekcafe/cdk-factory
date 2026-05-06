"""
Unit tests for EventBridge Rule SSM export functionality.

Verifies that the Lambda Stack correctly exports EventBridge rule names and ARNs
to SSM Parameter Store when auto_export is enabled, and skips export when disabled
or when triggers lack a name field.

Validates: Requirements 1.1, 1.2, 1.4, 1.5
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template, Match

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestEventBridgeSSMExport:
    """Test EventBridge rule SSM export from Lambda Stack."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
            "devops": {"ci_cd": {"auto_export": True}},
        }
        deployment_dict = {
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
            "devops": {"ci_cd": {"auto_export": True}},
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        config_dict = {
            "name": "test-workload",
            "description": "Test workload",
            "devops": {"ci_cd": {"auto_export": True}},
        }
        return WorkloadConfig(config=config_dict)

    def _build_stack_config(self, ssm_config: dict, triggers: list) -> StackConfig:
        """Helper to build a StackConfig with EventBridge triggers."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": ssm_config,
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": triggers,
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        return StackConfig(stack=stack_dict, workload=workload_dict)

    # ── Test: SSM parameters created for rule-name and rule-arn ──

    def test_eventbridge_ssm_rule_name_parameter_created(
        self, app, deployment_config, workload_config
    ):
        """Verify SSM parameter for EventBridge rule-name is created when auto_export is enabled.

        Validates: Requirements 1.1
        """
        ssm_config = {"auto_export": True, "namespace": "my-app/dev/lambda"}
        triggers = [
            {
                "name": "warm_up_orchestrator_schedule",
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-rule-name",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/warm-up-orchestrator-schedule/rule-name",
            },
        )

    def test_eventbridge_ssm_rule_arn_parameter_created(
        self, app, deployment_config, workload_config
    ):
        """Verify SSM parameter for EventBridge rule-arn is created when auto_export is enabled.

        Validates: Requirements 1.2
        """
        ssm_config = {"auto_export": True, "namespace": "my-app/dev/lambda"}
        triggers = [
            {
                "name": "warm_up_orchestrator_schedule",
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-rule-arn",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/warm-up-orchestrator-schedule/rule-arn",
            },
        )

    # ── Test: SSM parameter paths follow expected pattern ──

    def test_eventbridge_ssm_path_follows_namespace_pattern(
        self, app, deployment_config, workload_config
    ):
        """Verify SSM paths follow /{namespace}/event-bridge/{trigger-name}/rule-name pattern.

        Validates: Requirements 1.1, 1.2
        """
        ssm_config = {"auto_export": True, "namespace": "acme-saas/dev/lambda"}
        triggers = [
            {
                "name": "execution_metrics_aggregator_schedule",
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-path-pattern",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify rule-name path
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/acme-saas/dev/lambda/event-bridge/execution-metrics-aggregator-schedule/rule-name",
            },
        )

        # Verify rule-arn path
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/acme-saas/dev/lambda/event-bridge/execution-metrics-aggregator-schedule/rule-arn",
            },
        )

    # ── Test: Parameters use Standard tier ──

    def test_eventbridge_ssm_parameters_use_standard_tier(
        self, app, deployment_config, workload_config
    ):
        """Verify EventBridge SSM parameters use Standard tier.

        Validates: Requirements 1.4 (5.4 in design)
        """
        ssm_config = {"auto_export": True, "namespace": "my-app/dev/lambda"}
        triggers = [
            {
                "name": "warm_up_orchestrator_schedule",
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-tier",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Verify rule-name uses Standard tier
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/warm-up-orchestrator-schedule/rule-name",
                "Tier": "Standard",
            },
        )

        # Verify rule-arn uses Standard tier
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/warm-up-orchestrator-schedule/rule-arn",
                "Tier": "Standard",
            },
        )

    # ── Test: No EventBridge SSM parameters when auto_export is False ──

    def test_no_eventbridge_ssm_when_auto_export_disabled(
        self, app, deployment_config, workload_config
    ):
        """Verify no EventBridge SSM parameters when auto_export is False.

        Validates: Requirements 1.4
        """
        ssm_config = {"auto_export": False}
        triggers = [
            {
                "name": "warm_up_orchestrator_schedule",
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-disabled",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Should have zero SSM parameters (no Lambda ARN exports either since auto_export is False)
        template.resource_count_is("AWS::SSM::Parameter", 0)

    # ── Test: Skip behavior when trigger has no name field ──

    def test_no_eventbridge_ssm_when_trigger_has_no_name(
        self, app, deployment_config, workload_config
    ):
        """Verify no EventBridge SSM parameters when trigger has no name field.

        Validates: Requirements 1.5
        """
        ssm_config = {"auto_export": True, "namespace": "my-app/dev/lambda"}
        triggers = [
            {
                "resource_type": "event-bridge",
                "schedule": {"rate": {"type": "minutes", "duration": 15}},
            }
        ]
        stack_config = self._build_stack_config(ssm_config, triggers)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-no-trigger-name",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Should only have Lambda ARN/function-name SSM params, no EventBridge ones
        # Lambda exports: arn + function-name = 2 params
        # EventBridge exports: 0 (trigger has no name)
        template.resource_count_is("AWS::SSM::Parameter", 2)

    def test_mixed_triggers_only_named_get_ssm_export(
        self, app, deployment_config, workload_config
    ):
        """Verify only named triggers get SSM export, unnamed ones are skipped.

        Validates: Requirements 1.1, 1.5
        """
        ssm_config = {"auto_export": True, "namespace": "my-app/dev/lambda"}
        # Two resources: one with named trigger, one without
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": ssm_config,
            "resources": [
                {
                    "name": "function-with-named-trigger",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [
                        {
                            "name": "my_schedule",
                            "resource_type": "event-bridge",
                            "schedule": {"rate": {"type": "minutes", "duration": 5}},
                        }
                    ],
                    "sqs": {"queues": []},
                    "schedule": None,
                },
                {
                    "name": "function-with-unnamed-trigger",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [
                        {
                            "resource_type": "event-bridge",
                            "schedule": {"rate": {"type": "hours", "duration": 1}},
                        }
                    ],
                    "sqs": {"queues": []},
                    "schedule": None,
                },
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-eb-ssm-mixed-triggers",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # Named trigger should have SSM params
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/my-schedule/rule-name",
            },
        )
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/dev/lambda/event-bridge/my-schedule/rule-arn",
            },
        )

        # Total SSM params: 2 Lambda ARN exports (arn + function-name) * 2 functions = 4
        # Plus 2 EventBridge exports (rule-name + rule-arn) for the named trigger = 2
        # Total = 6
        template.resource_count_is("AWS::SSM::Parameter", 6)
