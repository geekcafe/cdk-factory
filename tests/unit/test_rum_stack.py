"""
Unit tests for the RUM Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.rum.rum_stack import RumStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestRumStack:
    """Test RUM Stack with real CDK synthesis"""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing"""
        return App()

    @pytest.fixture
    def workload_config(self):
        """Create a basic workload config"""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                }
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={"name": "test", "environment": "test"},
        )

    def test_minimal_rum_app_monitor(self, app, deployment_config, workload_config):
        """Test RUM stack with minimal configuration"""
        stack_config = StackConfig(
            {
                "rum": {
                    "name": "test-rum-app",
                    "domain": "example.com",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = RumStack(
            app,
            "TestMinimalRum",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify RUM App Monitor exists
        template.has_resource("AWS::RUM::AppMonitor", {})

        # Verify app monitor has required properties
        template.has_resource_properties(
            "AWS::RUM::AppMonitor",
            {
                "Name": Match.string_like_regexp(".*test-rum-app.*"),
                "Domain": "example.com",
            },
        )

        # Verify Cognito Identity Pool is created
        template.has_resource("AWS::Cognito::IdentityPool", {})

        # Verify IAM role for unauthenticated access
        template.has_resource("AWS::IAM::Role", {})

        assert stack.rum_config.name == "test-rum-app"
        assert stack.rum_config.domain == "example.com"

    def test_rum_with_xray_enabled(self, app, deployment_config, workload_config):
        """Test RUM with X-Ray tracing enabled"""
        stack_config = StackConfig(
            {
                "rum": {
                    "name": "xray-rum-app",
                    "domain": "example.com",
                    "enable_xray": True,
                }
            },
            workload=workload_config.dictionary,
        )

        stack = RumStack(
            app,
            "TestXRayRum",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify X-Ray is enabled in app monitor configuration
        template.has_resource_properties(
            "AWS::RUM::AppMonitor",
            {
                "AppMonitorConfiguration": Match.object_like(
                    {
                        "EnableXRay": True,
                    }
                )
            },
        )


    def test_rum_with_cw_logs_enabled(self, app, deployment_config, workload_config):
        """Test RUM with CloudWatch Logs enabled"""
        stack_config = StackConfig(
            {
                "rum": {
                    "name": "cwlogs-rum",
                    "domain": "example.com",
                    "cw_log_enabled": True,
                }
            },
            workload=workload_config.dictionary,
        )

        stack = RumStack(
            app,
            "TestCWLogsRum",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify CloudWatch Logs is enabled
        template.has_resource_properties(
            "AWS::RUM::AppMonitor",
            {
                "CwLogEnabled": True,
            },
        )


    def test_rum_creates_cognito_identity_pool_by_default(
        self, app, deployment_config, workload_config
    ):
        """Test that RUM creates Cognito Identity Pool by default"""
        stack_config = StackConfig(
            {
                "rum": {
                    "name": "auto-cognito-rum",
                    "domain": "example.com",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = RumStack(
            app,
            "TestAutoCognitoRum",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify Cognito Identity Pool is created
        template.has_resource("AWS::Cognito::IdentityPool", {})

        # Verify Identity Pool allows unauthenticated access
        template.has_resource_properties(
            "AWS::Cognito::IdentityPool",
            {
                "AllowUnauthenticatedIdentities": True,
            },
        )

    def test_rum_creates_iam_roles_for_cognito(
        self, app, deployment_config, workload_config
    ):
        """Test that RUM creates necessary IAM roles for Cognito"""
        stack_config = StackConfig(
            {
                "rum": {
                    "name": "iam-roles-rum",
                    "domain": "example.com",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = RumStack(
            app,
            "TestIAMRolesRum",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify IAM roles exist (at least one)
        template.has_resource("AWS::IAM::Role", {})

        # Verify at least one role has Cognito identity assume role policy
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "AssumeRolePolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sts:AssumeRole",
                                    "Effect": "Allow",
                                    "Principal": Match.object_like(
                                        {
                                            "Federated": "cognito-identity.amazonaws.com"
                                        }
                                    ),
                                }
                            )
                        ]
                    )
                }
            },
        )
