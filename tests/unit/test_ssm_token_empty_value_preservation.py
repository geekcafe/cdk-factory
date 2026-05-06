"""
Preservation Property Tests — Non-Empty Values and None-Value Behavior Unchanged

These tests capture the current correct behavior for non-buggy inputs.
They verify that:
1. Non-empty values are used directly as environment variables
2. None values with SSM parameters get SSM token injection
3. None values with fallback_value use the fallback
4. None values with neither SSM nor fallback are skipped
5. Non-empty values with SSM parameter present use the value directly

All tests MUST PASS on the current unfixed code — confirming baseline behavior
that must be preserved after the fix is applied.

Validates: Requirements 3.1, 3.2, 3.3, 3.4
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

# Generate non-empty string values (at least 1 character, printable ASCII)
_non_empty_value_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=50,
).filter(lambda s: len(s.strip()) > 0)

# Generate arbitrary SSM parameter paths: non-empty strings starting with /
_ssm_path_st = st.from_regex(r"/[a-z][a-z0-9\-/]{2,40}", fullmatch=True)

# Generate arbitrary environment variable names (uppercase with underscores)
_env_var_name_st = st.from_regex(r"[A-Z][A-Z0-9_]{2,20}", fullmatch=True)


# ---------------------------------------------------------------------------
# Preservation Tests
# ---------------------------------------------------------------------------


class TestSsmTokenEmptyValuePreservation(unittest.TestCase):
    """
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

    Property 2: Preservation — Non-Empty Values and None-Value Behavior Unchanged

    For any environment variable config entry where the bug condition does NOT hold,
    `load_environment_variables` must produce the same result as the current code.
    These tests capture baseline behavior that must remain unchanged after the fix.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    # -------------------------------------------------------------------
    # Property-based: Non-empty value preservation
    # -------------------------------------------------------------------

    @given(
        value=_non_empty_value_st,
        var_name=_env_var_name_st,
    )
    @settings(max_examples=50)
    def test_non_empty_value_used_directly_without_ssm(self, value, var_name):
        """Non-empty value without ssm_parameter is used directly.

        **Validates: Requirements 3.1**
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
                        "value": value,
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
        assert var_name in result, f"Expected '{var_name}' in result but it was missing"
        assert (
            result[var_name] == value
        ), f"Expected '{var_name}' to be '{value}' but got '{result[var_name]}'"

    @given(
        value=_non_empty_value_st,
        var_name=_env_var_name_st,
        ssm_path=_ssm_path_st,
    )
    @settings(max_examples=50)
    def test_non_empty_value_used_directly_with_ssm_present(
        self, value, var_name, ssm_path
    ):
        """Non-empty value with ssm_parameter present still uses value directly.

        **Validates: Requirements 3.1, 3.4**
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
                        "value": value,
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
        assert var_name in result, f"Expected '{var_name}' in result but it was missing"
        assert result[var_name] == value, (
            f"Expected '{var_name}' to be '{value}' (direct value) "
            f"but got '{result[var_name]}'. SSM should not be consulted "
            f"when value is non-empty."
        )

    # -------------------------------------------------------------------
    # Property-based: None value with SSM preservation
    # -------------------------------------------------------------------

    @given(
        ssm_path=_ssm_path_st,
        var_name=_env_var_name_st,
    )
    @settings(max_examples=50)
    def test_none_value_with_ssm_injects_token(self, ssm_path, var_name):
        """Entry with no value key and ssm_parameter defined gets SSM token injected.

        **Validates: Requirements 3.2**
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
        assert var_name in result, (
            f"Expected '{var_name}' in result — SSM token should be injected "
            f"when value is None and ssm_parameter is defined"
        )
        # SSM token should be a non-empty, non-None value (CDK token string)
        assert (
            result[var_name] is not None
        ), f"Expected '{var_name}' to have SSM token but got None"
        assert (
            result[var_name] != ""
        ), f"Expected '{var_name}' to have SSM token but got empty string"

    # -------------------------------------------------------------------
    # Example test: None value with fallback
    # -------------------------------------------------------------------

    def test_none_value_with_fallback_uses_fallback(self):
        """Entry with no value key, no ssm_parameter, but fallback_value present
        uses the fallback value.

        **Validates: Requirements 3.3**
        """
        stack = _make_stack()
        deployment = _make_deployment()

        lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
                "environment_variables": [
                    {
                        "name": "FALLBACK_VAR",
                        "fallback_value": "default-val",
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
        assert (
            "FALLBACK_VAR" in result
        ), "Expected 'FALLBACK_VAR' in result when fallback_value is defined"
        assert result["FALLBACK_VAR"] == "default-val", (
            f"Expected 'FALLBACK_VAR' to be 'default-val' "
            f"but got '{result['FALLBACK_VAR']}'"
        )

    # -------------------------------------------------------------------
    # Example test: None value with neither SSM nor fallback
    # -------------------------------------------------------------------

    def test_none_value_with_neither_ssm_nor_fallback_is_skipped(self):
        """Entry with no value key, no ssm_parameter, no fallback_value is
        skipped (not in environment dict) with a warning.

        **Validates: Requirements 3.3, 3.4**
        """
        stack = _make_stack()
        deployment = _make_deployment()

        lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
                "environment_variables": [
                    {
                        "name": "MISSING_VAR",
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
        assert "MISSING_VAR" not in result, (
            f"Expected 'MISSING_VAR' to NOT be in result (should be skipped) "
            f"but found value: '{result.get('MISSING_VAR')}'"
        )

    # -------------------------------------------------------------------
    # Example test: Non-empty value with SSM parameter present
    # -------------------------------------------------------------------

    def test_non_empty_value_with_ssm_uses_value_directly(self):
        """Entry with non-empty value and ssm_parameter present uses the value
        directly — SSM is not consulted.

        **Validates: Requirements 3.1, 3.4**
        """
        stack = _make_stack()
        deployment = _make_deployment()

        lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
                "environment_variables": [
                    {
                        "name": "POOL_ID",
                        "value": "us-east-1_abc123",
                        "ssm_parameter": "/test/pool-id",
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
        assert "POOL_ID" in result, "Expected 'POOL_ID' in result"
        assert result["POOL_ID"] == "us-east-1_abc123", (
            f"Expected 'POOL_ID' to be 'us-east-1_abc123' (direct value) "
            f"but got '{result['POOL_ID']}'. Non-empty value should be used "
            f"directly even when ssm_parameter is present."
        )
