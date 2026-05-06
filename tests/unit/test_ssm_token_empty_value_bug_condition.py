"""
Bug Condition Exploration Tests — Empty Value With SSM Parameter Skips Token Injection

These tests demonstrate that the current `load_environment_variables` method
skips SSM parameter token injection when a config entry has `value=""` and
`ssm_parameter` is defined. The `if value is None:` check evaluates to False
for empty strings, so the SSM resolution branch is never reached.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2
"""

import os
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

import aws_cdk
from aws_cdk import aws_ssm as ssm

from cdk_factory.utilities.environment_services import EnvironmentServices
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.workload import WorkloadConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deployment() -> DeploymentConfig:
    """Create a minimal DeploymentConfig for testing."""
    dummy_workload = WorkloadConfig(
        {
            "workload": {
                "name": "test-workload",
                "devops": {"name": "test-devops"},
            },
            "region": "us-east-1",
            "account": "123456789012",
        }
    )

    return DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={
            "name": "test-deployment",
            "environment": "dev",
            "account": "123456789012",
            "region": "us-east-1",
        },
    )


def _make_stack() -> aws_cdk.Stack:
    """Create a CDK App and Stack for SSM token resolution."""
    app = aws_cdk.App()
    return aws_cdk.Stack(app, "TestStack")


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate arbitrary SSM parameter paths: non-empty strings starting with /
_ssm_path_st = st.from_regex(r"/[a-z][a-z0-9\-/]{2,40}", fullmatch=True)

# Generate arbitrary environment variable names (uppercase with underscores)
_env_var_name_st = st.from_regex(r"[A-Z][A-Z0-9_]{2,20}", fullmatch=True)


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestSsmTokenEmptyValueBugCondition(unittest.TestCase):
    """
    **Validates: Requirements 1.1, 1.2**

    Property 1: Bug Condition — Empty Value With SSM Parameter Skips Token Injection

    For any environment variable config entry where `value` is an empty string `""`
    and `ssm_parameter` is defined, `load_environment_variables` MUST inject the
    SSM parameter token (via `ssm.StringParameter.value_for_string_parameter`) as
    the environment variable value.

    On unfixed code, the `if value is None:` check skips SSM resolution for empty
    strings, so the environment variable is set to `""`. These tests WILL FAIL,
    confirming the bug exists.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_empty_value_with_ssm_parameter_injects_token(self):
        """Config entry with value="" and ssm_parameter defined should resolve
        via SSM token injection, not use the empty string.

        Validates: Requirements 1.1, 1.2
        """
        stack = _make_stack()
        deployment = _make_deployment()

        lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
                "environment_variables": [
                    {
                        "name": "COGNITO_USER_POOL_ID",
                        "value": "",
                        "ssm_parameter": "/test/cognito/user-pool-id",
                    }
                ],
            }
        )

        result = EnvironmentServices.load_environment_variables(
            environment=None,
            deployment=deployment,
            lambda_config=lambda_config,
            scope=stack,
        )

        # The result should contain the SSM token, NOT an empty string
        assert result is not None
        assert "COGNITO_USER_POOL_ID" in result, (
            "Bug confirmed: COGNITO_USER_POOL_ID not in result — "
            "entry may have been skipped entirely"
        )
        assert result["COGNITO_USER_POOL_ID"] != "", (
            "Bug confirmed: COGNITO_USER_POOL_ID is empty string ''. "
            "Expected SSM token from ssm.StringParameter.value_for_string_parameter "
            "for path '/test/cognito/user-pool-id'. "
            "The `if value is None:` check skips SSM resolution for empty strings."
        )

    @given(
        ssm_path=_ssm_path_st,
        var_name=_env_var_name_st,
    )
    @settings(max_examples=50)
    def test_arbitrary_empty_value_with_ssm_resolves_token(self, ssm_path, var_name):
        """For any config entry where value="" and ssm_parameter is a valid path,
        the resulting environment variable must contain the SSM CDK token (not empty).

        Bug Condition: isBugCondition(input) = input.get("value") == "" AND "ssm_parameter" IN input
        Expected Behavior: result[input.name] == ssm_token_for(input.ssm_parameter)

        Validates: Requirements 1.1, 1.2
        """
        stack = _make_stack()
        deployment = _make_deployment()

        lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
                "environment_variables": [
                    {
                        "name": var_name,
                        "value": "",
                        "ssm_parameter": ssm_path,
                    }
                ],
            }
        )

        result = EnvironmentServices.load_environment_variables(
            environment=None,
            deployment=deployment,
            lambda_config=lambda_config,
            scope=stack,
        )

        assert result is not None

        # The variable must be present and must NOT be empty string
        assert var_name in result, (
            f"Bug confirmed: '{var_name}' not in result. "
            f"Entry with value='' and ssm_parameter='{ssm_path}' was skipped."
        )
        assert result[var_name] != "", (
            f"Bug confirmed: '{var_name}' is empty string ''. "
            f"Expected SSM token for path '{ssm_path}'. "
            f"The `if value is None:` check skips SSM resolution for empty strings."
        )
