"""
Unit tests for Lambda Stack SSM export path generation.
Covers namespace mode, legacy mode, Docker lambdas, and disabled/no-config scenarios.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestLambdaSSMExports:
    """Test Lambda Stack SSM export path generation."""

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

    # ── Task 1.1: Namespace mode tests ──

    def test_lambda_ssm_namespace_arn(self, app, deployment_config, workload_config):
        """Verify namespace SSM path for Lambda ARN."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "namespace": "my-ns"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ns-arn",
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
            {"Name": "/my-ns/lambda/test-function/arn"},
        )

    def test_lambda_ssm_namespace_function_name(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for Lambda function-name."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "namespace": "my-ns"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ns-fname",
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
            {"Name": "/my-ns/lambda/test-function/function-name"},
        )

    def test_lambda_ssm_namespace_docker_arn(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for Docker Lambda ARN."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "namespace": "my-ns"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "docker": {"file": "Dockerfile"},
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ns-docker-arn",
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
            {"Name": "/my-ns/docker-lambdas/test-function/arn"},
        )

    def test_lambda_ssm_namespace_docker_function_name(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for Docker Lambda function-name."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "namespace": "my-ns"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "docker": {"file": "Dockerfile"},
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ns-docker-fname",
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
            {"Name": "/my-ns/docker-lambdas/test-function/function-name"},
        )

    # ── Task 1.2: Legacy mode and disabled tests ──

    def test_lambda_ssm_legacy_arn(self, app, deployment_config, workload_config):
        """Verify legacy SSM path for Lambda ARN."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "workload": "wl", "environment": "dev"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-legacy-arn",
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
            {"Name": "/wl/dev/lambda/test-function/arn"},
        )

    def test_lambda_ssm_legacy_docker_arn(
        self, app, deployment_config, workload_config
    ):
        """Verify legacy SSM path for Docker Lambda ARN."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": True, "workload": "wl", "environment": "dev"},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "docker": {"file": "Dockerfile"},
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-legacy-docker-arn",
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
            {"Name": "/wl/dev/docker-lambdas/test-function/arn"},
        )

    def test_lambda_ssm_disabled(self, app, deployment_config, workload_config):
        """Verify zero SSM parameters when SSM is disabled."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "ssm": {"auto_export": False},
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ssm-disabled",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        template.resource_count_is("AWS::SSM::Parameter", 0)

    def test_lambda_ssm_no_config(self, app, deployment_config, workload_config):
        """Verify zero SSM parameters when no SSM block is present."""
        stack_dict = {
            "name": "test-lambda-stack",
            "auto_export": True,
            "resources": [
                {
                    "name": "test-function",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="test-ssm-no-config",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        template.resource_count_is("AWS::SSM::Parameter", 0)
