"""
Preservation Property Tests — SID Validity and Non-Colliding Behavior

These tests capture baseline behavior that MUST be preserved after the fix.
They run on UNFIXED code first (observation-first methodology) and should
PASS both before and after the fix is applied.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""

import os
import re
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# ---------------------------------------------------------------------------
# Helpers (same mock setup as test_duplicate_sid_bug_condition.py)
# ---------------------------------------------------------------------------


def _make_policy_documents() -> PolicyDocuments:
    """Create a PolicyDocuments instance with minimal mocks."""
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


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Resource names: alphanumeric with dashes/underscores, 1-60 chars, starting with a letter
_resource_name_st = st.from_regex(r"[a-z][a-z0-9\-_]{0,59}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


class TestSidValidityProperty(unittest.TestCase):
    """
    **Validates: Requirements 3.8**

    Property 2: Preservation — SID Validity

    For any resource name, _get_structured_permission() must produce a SID
    that is alphanumeric only and non-empty.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    @given(resource_name=_resource_name_st)
    @settings(max_examples=100)
    def test_dynamodb_sid_is_alphanumeric_and_nonempty(self, resource_name):
        """SID from DynamoDB structured permission must be alphanumeric and non-empty.

        **Validates: Requirements 3.8**
        """
        pd = _make_policy_documents()
        result = pd._get_structured_permission(
            {"dynamodb": "read", "table": resource_name}
        )
        sid = result["sid"]
        assert len(sid) > 0, f"SID is empty for resource_name='{resource_name}'"
        assert re.fullmatch(
            r"[A-Za-z0-9]+", sid
        ), f"SID '{sid}' is not alphanumeric for resource_name='{resource_name}'"

    @given(resource_name=_resource_name_st)
    @settings(max_examples=100)
    def test_s3_sid_is_alphanumeric_and_nonempty(self, resource_name):
        """SID from S3 structured permission must be alphanumeric and non-empty.

        **Validates: Requirements 3.8**
        """
        pd = _make_policy_documents()
        result = pd._get_structured_permission({"s3": "read", "bucket": resource_name})
        sid = result["sid"]
        assert len(sid) > 0, f"SID is empty for resource_name='{resource_name}'"
        assert re.fullmatch(
            r"[A-Za-z0-9]+", sid
        ), f"SID '{sid}' is not alphanumeric for resource_name='{resource_name}'"


class TestSlugLengthBoundedProperty(unittest.TestCase):
    """
    **Validates: Requirements 3.8**

    Property 2: Preservation — Slug Length Bounded

    For any resource name, the slug portion of the SID (after the action prefix)
    must be <= 20 characters.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    @given(resource_name=_resource_name_st)
    @settings(max_examples=100)
    def test_dynamodb_slug_length_bounded(self, resource_name):
        """The slug portion of a DynamoDB SID must be <= 20 characters.

        **Validates: Requirements 3.8**
        """
        pd = _make_policy_documents()
        result = pd._get_structured_permission(
            {"dynamodb": "read", "table": resource_name}
        )
        sid = result["sid"]
        # DynamoDB read prefix is "DynamoDbRead"
        slug = sid.replace("DynamoDbRead", "", 1)
        assert (
            len(slug) <= 20
        ), f"Slug '{slug}' has length {len(slug)} > 20 for resource_name='{resource_name}'"

    @given(resource_name=_resource_name_st)
    @settings(max_examples=100)
    def test_s3_slug_length_bounded(self, resource_name):
        """The slug portion of an S3 SID must be <= 20 characters.

        **Validates: Requirements 3.8**
        """
        pd = _make_policy_documents()
        result = pd._get_structured_permission({"s3": "read", "bucket": resource_name})
        sid = result["sid"]
        # S3 read prefix is "S3Read"
        slug = sid.replace("S3Read", "", 1)
        assert (
            len(slug) <= 20
        ), f"Slug '{slug}' has length {len(slug)} > 20 for resource_name='{resource_name}'"


# ---------------------------------------------------------------------------
# Example Tests — Preservation of Existing Behavior
# ---------------------------------------------------------------------------


class TestSingleResourcePreservation(unittest.TestCase):
    """
    **Validates: Requirements 3.1, 3.3, 3.5**

    Verify single-resource structured permissions return valid policy dicts
    with all expected keys.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"
        self.pd = _make_policy_documents()

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_single_dynamodb_table(self):
        """Single-table DynamoDB permission returns a valid policy dict.

        **Validates: Requirements 3.1**
        """
        result = self.pd._get_structured_permission(
            {"dynamodb": "read", "table": "users-table"}
        )

        # Must have all expected keys
        for key in ("name", "description", "sid", "actions", "resources", "nag"):
            assert key in result, f"Missing key '{key}' in result"

        assert result["name"] == "DynamoDB"
        assert "DynamoDB Read" in result["description"]
        assert "DynamoDbRead" in result["sid"]
        assert len(result["actions"]) > 0
        assert any("users-table" in r for r in result["resources"])

    def test_single_s3_bucket(self):
        """Single-bucket S3 permission returns a valid policy dict.

        **Validates: Requirements 3.3**
        """
        result = self.pd._get_structured_permission(
            {"s3": "read", "bucket": "my-bucket"}
        )

        for key in ("name", "sid", "actions", "resources", "nag"):
            assert key in result, f"Missing key '{key}' in result"

        assert result["name"] == "S3"
        assert "S3Read" in result["sid"]
        assert len(result["actions"]) > 0
        assert any("my-bucket" in r for r in result["resources"])

    def test_single_ssm_path(self):
        """Single-path SSM permission returns a valid policy dict.

        **Validates: Requirements 3.5**
        """
        result = self.pd._get_structured_permission(
            {"parameter_store": "read", "path": "/my-app/dev/config"}
        )

        for key in ("name", "description", "sid", "actions", "resources", "nag"):
            assert key in result, f"Missing key '{key}' in result"

        assert result["name"] == "SSM"
        assert "SSMRead" in result["sid"]
        assert len(result["actions"]) > 0
        assert any("/my-app/dev/config" in r for r in result["resources"])


class TestStringPermissionsPreserved(unittest.TestCase):
    """
    **Validates: Requirements 3.6**

    Verify string-based permissions return identical dicts as before.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"
        self.pd = _make_policy_documents()

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_cognito_admin_preserved(self):
        """cognito_admin returns the expected permission dict.

        **Validates: Requirements 3.6**
        """
        result = self.pd.get_permission_details("cognito_admin")

        assert result["name"] == "Cognito"
        assert result["description"] == "Cognito Admin Access"
        assert result["sid"] == "CognitoAdminAccess"
        assert result["actions"] == ["cognito-idp:*"]
        assert result["resources"] == ["*"]
        assert result["nag"] is not None
        assert result["nag"]["id"] == "AwsSolutions-IAM5"

    def test_parameter_store_read_preserved(self):
        """parameter_store_read returns the expected permission dict.

        **Validates: Requirements 3.6**
        """
        result = self.pd.get_permission_details("parameter_store_read")

        assert result["name"] == "ssm"
        assert result["description"] == "Parameter Store Read"
        assert result["sid"] == "ParameterStoreRead"
        assert "ssm:GetParameter" in result["actions"]
        assert "ssm:GetParameters" in result["actions"]
        assert "ssm:GetParametersByPath" in result["actions"]
        assert "ssm:DescribeParameters" in result["actions"]
        assert result["resources"] == ["*"]


class TestInlineIamDictPreserved(unittest.TestCase):
    """
    **Validates: Requirements 3.7**

    Verify inline IAM dicts with actions/resources keys return identical dicts.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"
        self.pd = _make_policy_documents()

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_inline_iam_dict_preserved(self):
        """Inline IAM dict permission returns the expected dict.

        **Validates: Requirements 3.7**
        """
        inline = {
            "name": "Custom",
            "sid": "CustomAccess",
            "actions": ["s3:GetObject"],
            "resources": ["*"],
        }
        result = self.pd.get_permission_details(inline)

        assert result["name"] == "Custom"
        assert result["sid"] == "CustomAccess"
        assert result["actions"] == ["s3:GetObject"]
        assert result["resources"] == ["*"]
        assert result["description"] is None
        assert result["nag"] is None


class TestNonCollidingMultiResource(unittest.TestCase):
    """
    **Validates: Requirements 3.2**

    Verify that resources whose slugs are already unique within 20 chars
    produce distinct SIDs.
    """

    def setUp(self):
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCOUNT"] = "123456789012"
        self.pd = _make_policy_documents()

    def tearDown(self):
        os.environ.pop("AWS_REGION", None)
        os.environ.pop("AWS_ACCOUNT", None)

    def test_non_colliding_dynamodb_tables(self):
        """users-table and orders-table produce distinct SIDs.

        **Validates: Requirements 3.2**
        """
        result_a = self.pd._get_structured_permission(
            {"dynamodb": "read", "table": "users-table"}
        )
        result_b = self.pd._get_structured_permission(
            {"dynamodb": "read", "table": "orders-table"}
        )

        sid_a = result_a["sid"]
        sid_b = result_b["sid"]

        assert sid_a != sid_b, (
            f"Non-colliding tables should produce distinct SIDs: "
            f"users-table -> '{sid_a}', orders-table -> '{sid_b}'"
        )
