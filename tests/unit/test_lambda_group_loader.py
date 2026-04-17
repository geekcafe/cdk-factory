"""
Property-Based Tests — Lambda Group Loader

These tests verify universal properties of the lambda group loader
using hypothesis to generate random inputs across many iterations.

Feature: iac-migration-parity
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.utilities.lambda_group_loader import load_and_group_lambda_configs

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Stack names: lowercase alphanumeric + hyphens, 1-20 chars
_stack_name = st.from_regex(r"[a-z][a-z0-9\-]{0,19}", fullmatch=True)

# Lambda names: lowercase alphanumeric + hyphens, 1-30 chars
_lambda_name = st.from_regex(r"[a-z][a-z0-9\-]{0,29}", fullmatch=True)


def _lambda_config_with_stack():
    """Strategy that generates a Lambda config dict with a stack field."""
    return st.fixed_dictionaries(
        {
            "stack": _stack_name,
            "name": _lambda_name,
            "handler": st.just("index.handler"),
            "timeout": st.integers(min_value=1, max_value=900),
        }
    )


# ---------------------------------------------------------------------------
# Property 9: Named stack grouping produces one stack per unique stack
# field value
# Feature: iac-migration-parity, Property 9: Named stack grouping
# **Validates: Requirements 13.1, 13.5**
# ---------------------------------------------------------------------------


class TestNamedStackGrouping:
    """
    **Validates: Requirements 13.1, 13.5**

    For any directory of individual Lambda JSON files where each file declares
    a stack field, the grouping function SHALL return exactly one group per
    unique stack value, each group containing exactly the Lambda configs that
    declared that stack name, and groups SHALL be created in sorted order by
    stack name.
    """

    @given(
        configs=st.lists(
            _lambda_config_with_stack(),
            min_size=1,
            max_size=10,
            unique_by=lambda c: c["name"],
        )
    )
    @settings(max_examples=100)
    def test_one_group_per_unique_stack_name(self, configs):
        """
        **Validates: Requirements 13.1, 13.5**

        Each unique stack name produces exactly one group, with correct
        membership and sorted order.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each config as a separate JSON file
            for i, config in enumerate(configs):
                filepath = Path(tmpdir) / f"{i:03d}-{config['name']}.json"
                with open(filepath, "w") as f:
                    json.dump(config, f)

            result = load_and_group_lambda_configs(tmpdir)

            # Compute expected groups
            expected_groups = {}
            for config in configs:
                stack = config["stack"]
                resource = {k: v for k, v in config.items() if k != "stack"}
                expected_groups.setdefault(stack, []).append(resource)

            # One group per unique stack name
            assert set(result.keys()) == set(expected_groups.keys())

            # Groups are in sorted order
            assert list(result.keys()) == sorted(result.keys())

            # Each group has the correct number of members
            for stack_name, group in result.items():
                assert len(group) == len(expected_groups[stack_name])

            # Each member has the stack field stripped
            for group in result.values():
                for resource in group:
                    assert "stack" not in resource

            # Each member preserves other fields
            for stack_name, group in result.items():
                expected_names = {r["name"] for r in expected_groups[stack_name]}
                actual_names = {r["name"] for r in group}
                assert actual_names == expected_names


# ---------------------------------------------------------------------------
# Property 10: Lambda configs missing the stack field produce errors
# Feature: iac-migration-parity, Property 10: Missing stack field errors
# **Validates: Requirements 13.2**
# ---------------------------------------------------------------------------


class TestMissingStackFieldErrors:
    """
    **Validates: Requirements 13.2**

    For any individual Lambda JSON file that does not contain a stack field,
    the grouping function SHALL raise a descriptive error identifying the file.
    """

    @given(
        lambda_name=_lambda_name,
        timeout=st.integers(min_value=1, max_value=900),
    )
    @settings(max_examples=100)
    def test_missing_stack_field_raises_error_with_filename(self, lambda_name, timeout):
        """
        **Validates: Requirements 13.2**

        Lambda configs without a stack field produce a descriptive error
        that identifies the file.
        """
        config = {
            "name": lambda_name,
            "handler": "index.handler",
            "timeout": timeout,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{lambda_name}.json"
            filepath = Path(tmpdir) / filename
            with open(filepath, "w") as f:
                json.dump(config, f)

            with pytest.raises(ValueError) as exc_info:
                load_and_group_lambda_configs(tmpdir)

            error_msg = str(exc_info.value)
            # Error should mention the filename
            assert filename in error_msg
            # Error should mention the missing field
            assert "stack" in error_msg
