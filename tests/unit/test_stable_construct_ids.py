"""
Property-Based Tests — Stable Construct IDs and Permission Validation

These tests verify universal properties of construct ID generation and
permission string validation using hypothesis.

Feature: iac-migration-parity
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.deployment import DeploymentConfig


# ---------------------------------------------------------------------------
# Strategies — constrained to realistic naming values
# ---------------------------------------------------------------------------

# Workload names: lowercase alphanumeric + hyphens, 1-30 chars
_workload_name = st.from_regex(r"[a-z][a-z0-9\-]{0,29}", fullmatch=True)

# Environment names: lowercase alphanumeric + hyphens, 1-20 chars
_environment_name = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)

# Resource names: lowercase alphanumeric + hyphens, 1-40 chars
_resource_name = st.from_regex(r"[a-z][a-z0-9\-]{0,39}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deployment(workload_name: str, environment: str) -> DeploymentConfig:
    """Create a minimal DeploymentConfig for testing build_resource_name."""
    workload = {
        "name": workload_name,
        "environment": environment,
    }
    deployment = {
        "name": environment,
        "environment": environment,
        "mode": "direct",
    }
    return DeploymentConfig(workload=workload, deployment=deployment)


# ---------------------------------------------------------------------------
# Property 4: Stable construct ID generation follows naming pattern
# Feature: iac-migration-parity, Property 4: Stable construct IDs
# **Validates: Requirements 9.1, 9.2**
# ---------------------------------------------------------------------------


class TestStableConstructIdGeneration:
    """
    **Validates: Requirements 9.1, 9.2**

    For any valid workload name, environment name, and resource name,
    the generated construct ID via build_resource_name() SHALL be
    deterministic (same inputs always produce same output) and SHALL
    contain the resource name.
    """

    @given(
        workload_name=_workload_name,
        environment=_environment_name,
        resource_name=_resource_name,
    )
    @settings(max_examples=100)
    def test_build_resource_name_is_deterministic(
        self, workload_name, environment, resource_name
    ):
        """
        **Validates: Requirements 9.1, 9.2**

        Calling build_resource_name() twice with the same inputs produces
        identical output.
        """
        deployment = _make_deployment(workload_name, environment)

        result_1 = deployment.build_resource_name(resource_name)
        result_2 = deployment.build_resource_name(resource_name)

        assert result_1 == result_2, (
            f"build_resource_name is not deterministic: "
            f"'{result_1}' != '{result_2}' for resource_name='{resource_name}'"
        )

    @given(
        workload_name=_workload_name,
        environment=_environment_name,
        resource_name=_resource_name,
    )
    @settings(max_examples=100)
    def test_build_resource_name_contains_resource_name(
        self, workload_name, environment, resource_name
    ):
        """
        **Validates: Requirements 9.1, 9.2**

        The output of build_resource_name() contains the resource name
        that was passed in.
        """
        deployment = _make_deployment(workload_name, environment)

        result = deployment.build_resource_name(resource_name)

        assert resource_name in result, (
            f"build_resource_name output '{result}' does not contain "
            f"resource_name '{resource_name}'"
        )

    @given(
        workload_name=_workload_name,
        environment=_environment_name,
        resource_name=_resource_name,
    )
    @settings(max_examples=100)
    def test_build_resource_name_returns_string(
        self, workload_name, environment, resource_name
    ):
        """
        **Validates: Requirements 9.1, 9.2**

        build_resource_name() always returns a non-empty string.
        """
        deployment = _make_deployment(workload_name, environment)

        result = deployment.build_resource_name(resource_name)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        workload_name=_workload_name,
        environment=_environment_name,
        resource_name=_resource_name,
    )
    @settings(max_examples=100)
    def test_build_resource_name_with_workload_placeholder(
        self, workload_name, environment, resource_name
    ):
        """
        **Validates: Requirements 9.1, 9.2**

        When resource_name contains {{workload-name}}, it is replaced
        with the actual workload name, producing a deterministic result
        that contains the workload name.
        """
        deployment = _make_deployment(workload_name, environment)

        template_name = f"{{{{workload-name}}}}-{resource_name}"
        result = deployment.build_resource_name(template_name)

        assert workload_name in result, (
            f"build_resource_name output '{result}' does not contain "
            f"workload_name '{workload_name}' after placeholder substitution"
        )
        assert resource_name in result


# ---------------------------------------------------------------------------
# Property 8: Unknown permission strings produce descriptive errors
# Feature: iac-migration-parity, Property 8: Unknown permission errors
# **Validates: Requirements 11.2**
# ---------------------------------------------------------------------------

import pytest
from hypothesis import assume

from cdk_factory.stack_library.aws_lambdas.lambda_validation import (
    KNOWN_PERMISSION_STRINGS,
    validate_permission_strings,
)

# Strategy for invalid permission strings: alphanumeric + underscores, 1-40 chars
_permission_string = st.from_regex(r"[a-z][a-z0-9_]{0,39}", fullmatch=True)

# Lambda names for error messages
_lambda_name = st.from_regex(r"[a-z][a-z0-9\-]{0,29}", fullmatch=True)


class TestUnknownPermissionStringErrors:
    """
    **Validates: Requirements 11.2**

    For any permission string that is not present in the defined permission
    mapping, the validation function SHALL raise a descriptive error
    identifying the unknown permission string and the Lambda function name.
    """

    @given(
        unknown_perm=_permission_string,
        lambda_name=_lambda_name,
    )
    @settings(max_examples=100)
    def test_unknown_permission_raises_descriptive_error(
        self, unknown_perm, lambda_name
    ):
        """
        **Validates: Requirements 11.2**

        A permission string not in KNOWN_PERMISSION_STRINGS raises a
        ValueError that mentions both the unknown permission and the
        Lambda name.
        """
        assume(unknown_perm not in KNOWN_PERMISSION_STRINGS)

        with pytest.raises(ValueError) as exc_info:
            validate_permission_strings([unknown_perm], lambda_name)

        error_msg = str(exc_info.value)
        assert unknown_perm in error_msg, (
            f"Error message does not mention unknown permission '{unknown_perm}': "
            f"{error_msg}"
        )
        assert lambda_name in error_msg, (
            f"Error message does not mention Lambda name '{lambda_name}': "
            f"{error_msg}"
        )

    @given(
        known_perms=st.lists(
            st.sampled_from(sorted(KNOWN_PERMISSION_STRINGS)),
            min_size=1,
            max_size=5,
        ),
        lambda_name=_lambda_name,
    )
    @settings(max_examples=100)
    def test_known_permissions_do_not_raise(self, known_perms, lambda_name):
        """
        **Validates: Requirements 11.2**

        Permission strings that ARE in KNOWN_PERMISSION_STRINGS do not
        raise errors.
        """
        # Should not raise
        validate_permission_strings(known_perms, lambda_name)

    @given(
        lambda_name=_lambda_name,
    )
    @settings(max_examples=100)
    def test_dict_permissions_do_not_raise(self, lambda_name):
        """
        **Validates: Requirements 11.2**

        Dict-based permissions (with explicit actions/resources) are always
        valid and do not raise errors.
        """
        dict_perm = {
            "name": "Custom",
            "sid": "CustomAccess",
            "actions": ["s3:GetObject"],
            "resources": ["arn:aws:s3:::my-bucket/*"],
        }
        # Should not raise
        validate_permission_strings([dict_perm], lambda_name)

    @given(
        unknown_perms=st.lists(
            _permission_string,
            min_size=2,
            max_size=5,
            unique=True,
        ),
        lambda_name=_lambda_name,
    )
    @settings(max_examples=100)
    def test_multiple_unknown_permissions_all_reported(
        self, unknown_perms, lambda_name
    ):
        """
        **Validates: Requirements 11.2**

        When multiple unknown permissions are present, the error message
        mentions all of them.
        """
        # Filter out any that happen to be known
        truly_unknown = [p for p in unknown_perms if p not in KNOWN_PERMISSION_STRINGS]
        assume(len(truly_unknown) >= 1)

        with pytest.raises(ValueError) as exc_info:
            validate_permission_strings(truly_unknown, lambda_name)

        error_msg = str(exc_info.value)
        for perm in truly_unknown:
            assert perm in error_msg, (
                f"Error message does not mention unknown permission '{perm}': "
                f"{error_msg}"
            )


# ---------------------------------------------------------------------------
# Naming Pattern Determinism
# Feature: iac-migration-parity
# **Validates: Requirements 14.2, 14.3**
# ---------------------------------------------------------------------------

# Stage names: lowercase alphanumeric + hyphens, 1-20 chars
_stage_name = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)
