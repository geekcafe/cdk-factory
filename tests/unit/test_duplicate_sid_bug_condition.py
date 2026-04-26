"""
Bug Condition Exploration Tests — Duplicate SIDs for Colliding Resource Name Slugs

These tests demonstrate that the current `_get_structured_permission()` method
generates identical SIDs when multiple resource names share the same first 20
characters after slug transformation (dash/underscore removal). This causes
CloudFormation deployment to fail with "Statement IDs (SID) in a single policy
must be unique".

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2, 1.3
"""

import os
import unittest

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy_documents() -> PolicyDocuments:
    """Create a PolicyDocuments instance with minimal mocks following the
    pattern from test_policy_documents_flexible_resolution.py."""
    app = App()
    stack = Stack(app, "TestStack")

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

    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={
            "name": "test-deployment",
            "environment": "dev",
            "account": "123456789012",
            "region": "us-east-1",
        },
    )

    lambda_config = LambdaFunctionConfig({"name": "test-lambda", "permissions": []})

    role = iam.Role(
        stack,
        "TestRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    )

    return PolicyDocuments(
        scope=stack,
        role=role,
        lambda_config=lambda_config,
        deployment=deployment,
    )


def _extract_sid(result: dict) -> str:
    """Extract the SID from a _get_structured_permission result."""
    return result["sid"]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate a common prefix longer than 20 chars (alphanumeric + dashes)
# and two distinct suffixes to create colliding resource names.
_common_prefix_st = st.from_regex(r"[a-z][a-z0-9\-]{20,30}", fullmatch=True)
_suffix_st = st.from_regex(r"[a-z][a-z0-9\-]{1,10}", fullmatch=True)


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestDuplicateSidBugCondition(unittest.TestCase):
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    Property 1: Bug Condition — Duplicate SIDs for Colliding Resource Name Slugs

    For any set of distinct resource names whose current 20-character truncation
    produces identical slugs, _get_structured_permission() MUST produce distinct
    SIDs for each resource name.

    On unfixed code, the slug is truncated to 20 chars, so names sharing a long
    common prefix produce identical SIDs. These tests WILL FAIL, confirming the
    bug exists.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_dynamodb_collision_real_world(self):
        """DynamoDB tables with colliding 20-char prefixes produce duplicate SIDs.

        Validates: Requirements 1.1
        """
        pd = _make_policy_documents()

        result_a = pd._get_structured_permission(
            {"dynamodb": "read", "table": "v3-acme-saas-alpha-app-database"}
        )
        result_b = pd._get_structured_permission(
            {
                "dynamodb": "read",
                "table": "v3-acme-saas-alpha-audit-logger-database",
            }
        )

        sid_a = _extract_sid(result_a)
        sid_b = _extract_sid(result_b)

        assert sid_a != sid_b, (
            f"Bug confirmed: DynamoDB tables produce duplicate SIDs. "
            f"table_a='v3-acme-saas-alpha-app-database' -> sid='{sid_a}', "
            f"table_b='v3-acme-saas-alpha-audit-logger-database' -> sid='{sid_b}'"
        )

    def test_s3_collision_real_world(self):
        """S3 buckets with colliding 20-char prefixes produce duplicate SIDs.

        Validates: Requirements 1.2
        """
        pd = _make_policy_documents()

        # These two buckets both produce slug 'v3acmesaasalphaa' (first 20 chars)
        result_a = pd._get_structured_permission(
            {"s3": "read", "bucket": "v3-acme-saas-alpha-app-uploads"}
        )
        result_b = pd._get_structured_permission(
            {"s3": "read", "bucket": "v3-acme-saas-alpha-app-downloads"}
        )

        sid_a = _extract_sid(result_a)
        sid_b = _extract_sid(result_b)

        assert sid_a != sid_b, (
            f"Bug confirmed: S3 buckets produce duplicate SIDs. "
            f"bucket_a='v3-acme-saas-alpha-app-uploads' -> sid='{sid_a}', "
            f"bucket_b='v3-acme-saas-alpha-app-downloads' -> sid='{sid_b}'"
        )

    def test_ssm_collision_real_world(self):
        """SSM paths with colliding 20-char prefixes produce duplicate SIDs.

        Validates: Requirements 1.3
        """
        pd = _make_policy_documents()

        result_a = pd._get_structured_permission(
            {
                "parameter_store": "read",
                "path": "/v3-acme-saas-alpha/dev/cognito/pool-id",
            }
        )
        result_b = pd._get_structured_permission(
            {
                "parameter_store": "read",
                "path": "/v3-acme-saas-alpha/dev/cognito/client-id",
            }
        )

        sid_a = _extract_sid(result_a)
        sid_b = _extract_sid(result_b)

        assert sid_a != sid_b, (
            f"Bug confirmed: SSM paths produce duplicate SIDs. "
            f"path_a='/v3-acme-saas-alpha/dev/cognito/pool-id' -> sid='{sid_a}', "
            f"path_b='/v3-acme-saas-alpha/dev/cognito/client-id' -> sid='{sid_b}'"
        )

    @given(
        prefix=_common_prefix_st,
        suffix_a=_suffix_st,
        suffix_b=_suffix_st,
    )
    @settings(max_examples=100)
    def test_dynamodb_distinct_names_produce_distinct_sids(
        self, prefix, suffix_a, suffix_b
    ):
        """For any two distinct DynamoDB table names sharing a common prefix
        longer than 20 chars (after stripping), SIDs must be different.

        Validates: Requirements 1.1
        """
        table_a = f"{prefix}-{suffix_a}"
        table_b = f"{prefix}-{suffix_b}"

        # Only test truly distinct names
        assume(table_a != table_b)

        # Verify the stripped names share >20 char prefix (bug condition)
        stripped_a = table_a.replace("-", "").replace("_", "")
        stripped_b = table_b.replace("-", "").replace("_", "")
        assume(stripped_a[:20] == stripped_b[:20])
        assume(stripped_a != stripped_b)

        pd = _make_policy_documents()

        result_a = pd._get_structured_permission({"dynamodb": "read", "table": table_a})
        result_b = pd._get_structured_permission({"dynamodb": "read", "table": table_b})

        sid_a = _extract_sid(result_a)
        sid_b = _extract_sid(result_b)

        assert sid_a != sid_b, (
            f"Bug confirmed: Distinct DynamoDB tables produce duplicate SIDs. "
            f"table_a='{table_a}' -> sid='{sid_a}', "
            f"table_b='{table_b}' -> sid='{sid_b}'"
        )
