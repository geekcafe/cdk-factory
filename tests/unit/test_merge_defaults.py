"""
Tests for cdk_factory.utilities.merge_defaults

Covers:
  - Property-based tests (Hypothesis) for merge correctness properties
  - Example-based unit tests for permission_key(), merge edge cases, and skip_stack_defaults
"""

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.utilities.merge_defaults import (
    merge_environment_variables,
    merge_permissions,
    merge_stack_defaults_into_resources,
    permission_key,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# DynamoDB permission: {"dynamodb": action, "table": table_name}
dynamodb_perm = st.fixed_dictionaries(
    {
        "dynamodb": st.text(min_size=1, max_size=10),
        "table": st.text(min_size=1, max_size=20),
    }
)

# S3 permission: {"s3": action, "bucket": bucket_name}
s3_perm = st.fixed_dictionaries(
    {"s3": st.text(min_size=1, max_size=10), "bucket": st.text(min_size=1, max_size=20)}
)

# String permission
string_perm = st.text(min_size=1, max_size=30)

# Inline IAM permission: {"actions": [...], "resources": [...]}
inline_iam_perm = st.fixed_dictionaries(
    {
        "actions": st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
        "resources": st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
    }
)

# Any permission format
any_perm = st.one_of(dynamodb_perm, s3_perm, string_perm, inline_iam_perm)

# Environment variable entry: {"name": name, "value": value}
env_var = st.fixed_dictionaries(
    {
        "name": st.text(min_size=1, max_size=20),
        "value": st.text(min_size=0, max_size=30),
    }
)


# ---------------------------------------------------------------------------
# Task 2: Property-based tests
# ---------------------------------------------------------------------------


class TestPropertyPermissionsMerge:
    """Property 1: Permissions merge with resource-level precedence.

    **Validates: Requirements 1.1, 1.2, 3.1, 3.3**
    """

    @given(
        resource_perms=st.lists(any_perm, max_size=8),
        stack_perms=st.lists(any_perm, max_size=8),
    )
    @settings(max_examples=100)
    def test_permissions_merge_with_precedence(self, resource_perms, stack_perms):
        """Merged result contains all originals plus only non-matching stack entries."""
        merged = merge_permissions(resource_perms, stack_perms)

        # All original resource permissions are preserved in order
        assert merged[: len(resource_perms)] == resource_perms

        # Every appended entry comes from stack_perms and has a key not in resource keys
        resource_keys = {permission_key(p) for p in resource_perms}
        appended = merged[len(resource_perms) :]
        for entry in appended:
            assert permission_key(entry) not in resource_keys

        # Every stack entry whose key is NOT in resource_keys appears in appended
        expected_new = [
            sp for sp in stack_perms if permission_key(sp) not in resource_keys
        ]
        assert len(appended) == len(expected_new)


class TestPropertyEnvVarsMerge:
    """Property 2: Environment variables merge with name-based precedence.

    **Validates: Requirements 2.1, 2.2, 3.2, 3.4**
    """

    @given(
        resource_env=st.lists(env_var, max_size=8),
        stack_env=st.lists(env_var, max_size=8),
    )
    @settings(max_examples=100)
    def test_env_vars_merge_with_name_precedence(self, resource_env, stack_env):
        """Merged result contains all originals plus only entries with new names."""
        merged = merge_environment_variables(resource_env, stack_env)

        # All original resource env vars preserved in order
        assert merged[: len(resource_env)] == resource_env

        # Appended entries have names not present in resource env vars
        resource_names = {ev["name"] for ev in resource_env}
        appended = merged[len(resource_env) :]
        for entry in appended:
            assert entry["name"] not in resource_names

        # Count matches expected
        expected_new = [sev for sev in stack_env if sev["name"] not in resource_names]
        assert len(appended) == len(expected_new)


class TestPropertyEmptyFieldsNoop:
    """Property 3: Absent or empty stack-level fields are a no-op.

    **Validates: Requirements 1.3, 2.3, 4.1, 4.2, 4.3, 4.4**
    """

    @given(
        resources=st.lists(
            st.fixed_dictionaries(
                {
                    "name": st.text(min_size=1, max_size=15),
                    "permissions": st.lists(any_perm, max_size=4),
                    "environment_variables": st.lists(env_var, max_size=4),
                }
            ),
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_empty_fields_are_noop(self, resources):
        """Merging with empty/absent stack-level fields leaves resources unchanged."""
        original = copy.deepcopy(resources)
        merge_stack_defaults_into_resources(resources, [], [])
        assert resources == original


class TestPropertyAllPermissionFormats:
    """Property 4: All permission formats are supported in merge.

    **Validates: Requirements 1.4**
    """

    @given(
        resource_perms=st.lists(any_perm, min_size=1, max_size=6),
        stack_perms=st.lists(any_perm, min_size=1, max_size=6),
    )
    @settings(max_examples=100)
    def test_all_permission_formats_supported(self, resource_perms, stack_perms):
        """Merge completes without error across all four permission formats."""
        merged = merge_permissions(resource_perms, stack_perms)

        # Result is a list and contains at least the resource perms
        assert isinstance(merged, list)
        assert len(merged) >= len(resource_perms)

        # Every entry has a hashable permission_key (no errors)
        for entry in merged:
            key = permission_key(entry)
            assert isinstance(key, (str, tuple))


class TestPropertySkipStackDefaults:
    """Property 5: skip_stack_defaults opt-out is honored.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(
        stack_perms=st.lists(any_perm, min_size=1, max_size=6),
        stack_env=st.lists(env_var, min_size=1, max_size=6),
        resource_perms=st.lists(any_perm, max_size=4),
        resource_env=st.lists(env_var, max_size=4),
    )
    @settings(max_examples=100)
    def test_skip_stack_defaults_honored(
        self, stack_perms, stack_env, resource_perms, resource_env
    ):
        """Resources with skip_stack_defaults=true are untouched after merge."""
        resources = [
            {
                "name": "skipped-fn",
                "skip_stack_defaults": True,
                "permissions": list(resource_perms),
                "environment_variables": list(resource_env),
            }
        ]
        original = copy.deepcopy(resources)
        merge_stack_defaults_into_resources(resources, stack_perms, stack_env)
        assert resources == original


# ---------------------------------------------------------------------------
# Task 4: Example-based unit tests
# ---------------------------------------------------------------------------


class TestPermissionKeyHelper:
    """Unit tests for permission_key() helper.

    **Validates: Requirements 1.4, 3.3**
    """

    def test_dynamodb_returns_tuple(self):
        entry = {"dynamodb": "read", "table": "my-table"}
        assert permission_key(entry) == ("dynamodb", "read", "my-table")

    def test_dynamodb_same_table_different_action(self):
        read = {"dynamodb": "read", "table": "t"}
        write = {"dynamodb": "write", "table": "t"}
        assert permission_key(read) != permission_key(write)

    def test_s3_returns_tuple(self):
        entry = {"s3": "write", "bucket": "my-bucket"}
        assert permission_key(entry) == ("s3", "write", "my-bucket")

    def test_s3_same_bucket_different_action(self):
        read = {"s3": "read", "bucket": "b"}
        delete = {"s3": "delete", "bucket": "b"}
        assert permission_key(read) != permission_key(delete)

    def test_string_returns_itself(self):
        assert permission_key("parameter_store_read") == "parameter_store_read"

    def test_inline_iam_returns_frozenset_tuple(self):
        entry = {
            "actions": ["s3:GetObject", "s3:PutObject"],
            "resources": ["arn:aws:s3:::b/*"],
        }
        key = permission_key(entry)
        assert key == (
            frozenset(["s3:GetObject", "s3:PutObject"]),
            frozenset(["arn:aws:s3:::b/*"]),
        )

    def test_inline_iam_same_actions_resources_match(self):
        a = {"actions": ["a", "b"], "resources": ["r1"]}
        b = {"actions": ["b", "a"], "resources": ["r1"]}
        assert permission_key(a) == permission_key(b)

    def test_dynamodb_missing_table_defaults_empty(self):
        entry = {"dynamodb": "read"}
        assert permission_key(entry) == ("dynamodb", "read", "")

    def test_s3_missing_bucket_defaults_empty(self):
        entry = {"s3": "write"}
        assert permission_key(entry) == ("s3", "write", "")


class TestMergeEdgeCases:
    """Unit tests for merge edge cases.

    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**
    """

    def test_resource_no_permissions_key_gets_stack_perms(self):
        resources = [{"name": "fn1"}]
        merge_stack_defaults_into_resources(
            resources,
            [{"dynamodb": "read", "table": "t"}],
            [],
        )
        assert resources[0]["permissions"] == [{"dynamodb": "read", "table": "t"}]

    def test_resource_no_env_vars_key_gets_stack_env(self):
        resources = [{"name": "fn1"}]
        merge_stack_defaults_into_resources(
            resources,
            [],
            [{"name": "ENV", "value": "dev"}],
        )
        assert resources[0]["environment_variables"] == [
            {"name": "ENV", "value": "dev"}
        ]

    def test_mixed_permission_formats_single_merge(self):
        resource_perms = [
            {"dynamodb": "read", "table": "t1"},
            "parameter_store_read",
        ]
        stack_perms = [
            {"s3": "write", "bucket": "b1"},
            {"actions": ["logs:Put"], "resources": ["*"]},
            "parameter_store_read",  # duplicate string — should be skipped
        ]
        merged = merge_permissions(resource_perms, stack_perms)
        assert len(merged) == 4  # 2 original + s3 + inline IAM (string dup skipped)
        assert merged[0] == {"dynamodb": "read", "table": "t1"}
        assert merged[1] == "parameter_store_read"
        assert merged[2] == {"s3": "write", "bucket": "b1"}
        assert merged[3] == {"actions": ["logs:Put"], "resources": ["*"]}

    def test_duplicate_env_var_name_keeps_resource_value(self):
        resource_env = [{"name": "ENVIRONMENT", "value": "staging"}]
        stack_env = [
            {"name": "ENVIRONMENT", "value": "dev"},
            {"name": "NEW_VAR", "value": "x"},
        ]
        merged = merge_environment_variables(resource_env, stack_env)
        assert len(merged) == 2
        assert merged[0] == {"name": "ENVIRONMENT", "value": "staging"}
        assert merged[1] == {"name": "NEW_VAR", "value": "x"}

    def test_empty_resource_perms_gets_all_stack_perms(self):
        merged = merge_permissions([], ["perm_a", "perm_b"])
        assert merged == ["perm_a", "perm_b"]

    def test_empty_stack_perms_returns_resource_perms(self):
        merged = merge_permissions(["perm_a"], [])
        assert merged == ["perm_a"]


class TestSkipStackDefaultsBehavior:
    """Unit tests for skip_stack_defaults behavior.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    def test_skip_true_skips_merge_entirely(self):
        resources = [
            {
                "name": "fn1",
                "skip_stack_defaults": True,
                "permissions": ["original"],
                "environment_variables": [{"name": "A", "value": "1"}],
            }
        ]
        original = copy.deepcopy(resources)
        merge_stack_defaults_into_resources(
            resources,
            ["new_perm"],
            [{"name": "B", "value": "2"}],
        )
        assert resources == original

    def test_skip_false_merges_normally(self):
        resources = [
            {
                "name": "fn1",
                "skip_stack_defaults": False,
                "permissions": [],
                "environment_variables": [],
            }
        ]
        merge_stack_defaults_into_resources(
            resources,
            ["new_perm"],
            [{"name": "B", "value": "2"}],
        )
        assert resources[0]["permissions"] == ["new_perm"]
        assert resources[0]["environment_variables"] == [{"name": "B", "value": "2"}]

    def test_absent_skip_merges_normally(self):
        resources = [
            {
                "name": "fn1",
                "permissions": [],
                "environment_variables": [],
            }
        ]
        merge_stack_defaults_into_resources(
            resources,
            ["new_perm"],
            [{"name": "B", "value": "2"}],
        )
        assert resources[0]["permissions"] == ["new_perm"]
        assert resources[0]["environment_variables"] == [{"name": "B", "value": "2"}]
