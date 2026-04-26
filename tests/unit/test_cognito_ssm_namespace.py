"""
Unit Tests — Cognito Per-Client SSM Namespace

These tests verify the per-client SSM namespace feature using CDK template
assertions to validate that SSM parameters are exported under the correct
namespace paths.

Feature: cognito-app-client-ssm-namespace
"""

import os
import pytest
from unittest.mock import patch

from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.stack_library.cognito.cognito_stack import CognitoStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_environment():
    """Set ENVIRONMENT variable for tests"""
    os.environ["ENVIRONMENT"] = "test"
    yield
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]


def _dummy_workload():
    return WorkloadConfig(
        {
            "workload": {
                "name": "dummy-workload",
                "environment": "test",
                "devops": {"name": "dummy-devops"},
            },
        }
    )


def _build_stack(stack_dict: dict):
    """Helper to build a CognitoStack from a config dict and return the stack."""
    app = App()
    workload = _dummy_workload()
    stack_config = StackConfig(stack_dict, workload=workload.dictionary)
    dc = DeploymentConfig(
        workload=workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "test"},
    )
    stack = CognitoStack(app, "TestId")
    stack.build(stack_config, dc, workload)
    return stack


# ---------------------------------------------------------------------------
# 5.1 Client with ssm_namespace exports under client namespace
# Requirements: 2.1, 4.1
# ---------------------------------------------------------------------------


class TestClientWithSsmNamespace:
    def test_client_ssm_param_uses_client_namespace(self):
        """Client with ssm_namespace should export its ID under the client namespace."""
        stack = _build_stack(
            {
                "ssm": {"auto_export": True, "namespace": "pool/ns"},
                "cognito": {
                    "user_pool_name": "TestPool",
                    "app_clients": [
                        {
                            "name": "my-client",
                            "ssm_namespace": "client/ns",
                            "auth_flows": {"user_srp": True},
                        }
                    ],
                },
            }
        )
        template = Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/client/ns/client-id",
                "Value": Match.any_value(),
            },
        )


# ---------------------------------------------------------------------------
# 5.2 Client without ssm_namespace exports under pool namespace
# Requirements: 2.3, 5.1
# ---------------------------------------------------------------------------


class TestClientWithoutSsmNamespace:
    def test_client_ssm_param_uses_pool_namespace(self):
        """Client without ssm_namespace should export its ID under the pool namespace."""
        stack = _build_stack(
            {
                "ssm": {"auto_export": True, "namespace": "pool/ns"},
                "cognito": {
                    "user_pool_name": "TestPool",
                    "app_clients": [
                        {
                            "name": "my-client",
                            "auth_flows": {"user_srp": True},
                        }
                    ],
                },
            }
        )
        template = Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pool/ns/app-client-my-client-id",
                "Value": Match.any_value(),
            },
        )


# ---------------------------------------------------------------------------
# 5.3 Pool-level parameters always use pool namespace
# Requirements: 3.1, 3.2
# ---------------------------------------------------------------------------


class TestPoolLevelParamsUsePoolNamespace:
    def test_pool_params_under_pool_namespace_even_with_client_ns(self):
        """Pool-level params (user_pool_id, arn, name) must always use pool namespace."""
        stack = _build_stack(
            {
                "ssm": {"auto_export": True, "namespace": "pool/ns"},
                "cognito": {
                    "user_pool_name": "TestPool",
                    "app_clients": [
                        {
                            "name": "my-client",
                            "ssm_namespace": "client/ns",
                            "auth_flows": {"user_srp": True},
                        }
                    ],
                },
            }
        )
        template = Template.from_stack(stack)

        # user_pool_id
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pool/ns/user-pool-id",
                "Value": Match.any_value(),
            },
        )
        # user_pool_arn
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pool/ns/user-pool-arn",
                "Value": Match.any_value(),
            },
        )
        # user_pool_name
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pool/ns/user-pool-name",
                "Value": Match.any_value(),
            },
        )


# ---------------------------------------------------------------------------
# 5.4 Warning logged when ssm_namespace set but auto_export disabled
# Requirements: 6.1
# ---------------------------------------------------------------------------


class TestWarningWhenAutoExportDisabled:
    def test_warning_logged_when_ssm_namespace_but_no_auto_export(self):
        """A warning should be logged when ssm_namespace is set but auto_export is false."""
        with patch(
            "cdk_factory.stack_library.cognito.cognito_stack.logger"
        ) as mock_logger:
            _build_stack(
                {
                    "ssm": {"auto_export": False, "namespace": "pool/ns"},
                    "cognito": {
                        "user_pool_name": "TestPool",
                        "app_clients": [
                            {
                                "name": "my-client",
                                "ssm_namespace": "client/ns",
                                "auth_flows": {"user_srp": True},
                            }
                        ],
                    },
                }
            )
            # Assert warning was called with a message about ssm_namespace being ignored
            mock_logger.warning.assert_any_call(
                "App client 'my-client' has 'ssm_namespace' configured but "
                "ssm.auto_export is disabled and no explicit exports are configured. "
                "The client-level namespace will be ignored."
            )


# ---------------------------------------------------------------------------
# 5.5 Empty ssm_namespace raises ValueError
# Requirements: 6.2
# ---------------------------------------------------------------------------


class TestEmptySsmNamespaceRaisesError:
    def test_empty_ssm_namespace_raises_value_error(self):
        """An empty ssm_namespace string should raise ValueError."""
        with pytest.raises(ValueError, match="ssm_namespace"):
            _build_stack(
                {
                    "ssm": {"auto_export": True, "namespace": "pool/ns"},
                    "cognito": {
                        "user_pool_name": "TestPool",
                        "app_clients": [
                            {
                                "name": "bad-client",
                                "ssm_namespace": "",
                                "auth_flows": {"user_srp": True},
                            }
                        ],
                    },
                }
            )


# ---------------------------------------------------------------------------
# 5.6 Mixed clients with different namespaces
# Requirements: 4.1, 4.2
# ---------------------------------------------------------------------------


class TestMixedClientNamespaces:
    def test_mixed_clients_export_under_correct_namespaces(self):
        """Two clients — one with ssm_namespace, one without — each export correctly."""
        stack = _build_stack(
            {
                "ssm": {"auto_export": True, "namespace": "pool/ns"},
                "cognito": {
                    "user_pool_name": "TestPool",
                    "app_clients": [
                        {
                            "name": "client-a",
                            "ssm_namespace": "client-a/ns",
                            "auth_flows": {"user_srp": True},
                        },
                        {
                            "name": "client-b",
                            "auth_flows": {"user_srp": True},
                        },
                    ],
                },
            }
        )
        template = Template.from_stack(stack)

        # client-a uses its own namespace
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/client-a/ns/client-id",
                "Value": Match.any_value(),
            },
        )
        # client-b falls back to pool namespace
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/pool/ns/app-client-client-b-id",
                "Value": Match.any_value(),
            },
        )


# ---------------------------------------------------------------------------
# 5.7 Secret ARN exported under client namespace
# Requirements: 2.2
# ---------------------------------------------------------------------------


class TestSecretArnUnderClientNamespace:
    def test_secret_arn_uses_client_namespace(self):
        """When generate_secret is true and ssm_namespace is set, secret ARN uses client ns."""
        stack = _build_stack(
            {
                "ssm": {"auto_export": True, "namespace": "pool/ns"},
                "cognito": {
                    "user_pool_name": "TestPool",
                    "app_clients": [
                        {
                            "name": "secret-client",
                            "ssm_namespace": "secret/ns",
                            "generate_secret": True,
                            "auth_flows": {"user_srp": True},
                        }
                    ],
                },
            }
        )
        template = Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/secret/ns/secret-arn",
                "Value": Match.any_value(),
            },
        )
