"""
Unit tests for PolicyDocuments SSM ARN resolution.

Tests the ssm_arn field on Lambda invoke permissions — using CDK's
StringParameter.value_for_string_parameter() to produce CloudFormation
dynamic references resolved at deploy time.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 3.1, 3.2, 3.3,
           4.1, 4.2, 4.3, 5.1, 5.2
"""

import unittest
from unittest.mock import patch, MagicMock

from aws_cdk import App, Stack, Token
from aws_cdk import aws_iam as iam

from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestPolicyDocumentsSsmArn(unittest.TestCase):
    """Unit tests for ssm_arn Lambda invoke permission resolution."""

    def setUp(self):
        """Set up test environment with CDK stack and PolicyDocuments instance."""
        self.app = App()
        self.stack = Stack(self.app, "TestStack")

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

        self.deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={
                "name": "test-deployment",
                "environment": "dev",
                "account": "123456789012",
                "region": "us-east-1",
            },
        )

        self.lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": [],
            }
        )

        self.role = iam.Role(
            self.stack,
            "TestRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        self.policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

    # -------------------------------------------------------------------------
    # Backward compatibility tests (Requirement 3.1, 3.2)
    # -------------------------------------------------------------------------

    def test_backward_compat_wildcard_function(self):
        """{"lambda": "invoke", "function": "*"} produces wildcard resource.

        Validates: Requirement 3.1
        """
        permission = {"lambda": "invoke", "function": "*"}
        result = self.policy_docs.get_permission_details(permission)

        self.assertEqual(result["actions"], ["lambda:InvokeFunction"])
        self.assertEqual(result["resources"], ["*"])
        self.assertEqual(result["name"], "Lambda")
        self.assertIn("LambdaInvoke", result["sid"])

    def test_backward_compat_exact_function_name(self):
        """{"lambda": "invoke", "function": "exact-name"} produces ARN-scoped resource.

        Validates: Requirement 3.2
        """
        permission = {"lambda": "invoke", "function": "exact-name"}
        result = self.policy_docs.get_permission_details(permission)

        self.assertEqual(result["actions"], ["lambda:InvokeFunction"])
        self.assertEqual(len(result["resources"]), 1)
        resource = result["resources"][0]
        self.assertIn("arn:aws:lambda:", resource)
        self.assertIn("exact-name", resource)
        self.assertIn("123456789012", resource)
        self.assertIn("us-east-1", resource)

    # -------------------------------------------------------------------------
    # SSM ARN resolution tests (Requirement 1.1, 1.2)
    # -------------------------------------------------------------------------

    def test_ssm_arn_produces_token_based_resource(self):
        """ssm_arn produces a CDK token resource (CF dynamic reference).

        Validates: Requirements 1.1, 1.2
        """
        permission = {"lambda": "invoke", "ssm_arn": "/my-app/dev/lambda/target/arn"}
        result = self.policy_docs.get_permission_details(permission)

        self.assertEqual(result["actions"], ["lambda:InvokeFunction"])
        self.assertEqual(len(result["resources"]), 1)
        # The resource should be a CDK token (unresolved reference)
        resource = result["resources"][0]
        self.assertTrue(
            Token.is_unresolved(resource),
            f"Expected a CDK token but got: {resource}",
        )
        self.assertEqual(result["name"], "Lambda")
        self.assertIn("LambdaInvokeSsm", result["sid"])

    # -------------------------------------------------------------------------
    # Precedence test (Requirement 3.3)
    # -------------------------------------------------------------------------

    def test_ssm_arn_takes_precedence_over_function(self):
        """ssm_arn takes precedence when both ssm_arn and function are present.

        Validates: Requirement 3.3
        """
        permission = {
            "lambda": "invoke",
            "function": "ignored-function-name",
            "ssm_arn": "/my-app/dev/lambda/ssm-target/arn",
        }
        result = self.policy_docs.get_permission_details(permission)

        # Should produce a token (SSM reference), not the exact function name
        resource = result["resources"][0]
        self.assertTrue(Token.is_unresolved(resource))
        # The function name should NOT appear in the resource
        self.assertNotIn("ignored-function-name", str(result["resources"]))

    # -------------------------------------------------------------------------
    # Validation tests (Requirement 5.1, 5.2)
    # -------------------------------------------------------------------------

    def test_ssm_arn_empty_raises_valueerror(self):
        """ssm_arn with empty string raises ValueError.

        Validates: Requirement 5.1
        """
        with self.assertRaises(ValueError) as ctx:
            self.policy_docs._resolve_ssm_arn_permission("invoke", "")

        self.assertIn("empty", str(ctx.exception).lower())

    def test_ssm_arn_without_leading_slash_raises_valueerror(self):
        """ssm_arn without leading '/' after resolution raises ValueError.

        Validates: Requirement 5.2
        """
        permission = {"lambda": "invoke", "ssm_arn": "no-leading-slash/path"}
        with self.assertRaises(ValueError) as ctx:
            self.policy_docs.get_permission_details(permission)

        self.assertIn("/", str(ctx.exception))
        self.assertIn("no-leading-slash/path", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Template variable resolution (Requirement 1.3)
    # -------------------------------------------------------------------------

    @patch.dict(
        "os.environ",
        {"WORKLOAD_NAME": "my-workload", "DEPLOYMENT_NAMESPACE": "dev"},
        clear=False,
    )
    def test_template_variable_resolution(self):
        """Template variable resolution with mocked os.environ.

        Validates: Requirement 1.3
        """
        permission = {
            "lambda": "invoke",
            "ssm_arn": "/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/lambda/handler/arn",
        }
        result = self.policy_docs.get_permission_details(permission)

        # Should produce a token (SSM reference)
        resource = result["resources"][0]
        self.assertTrue(Token.is_unresolved(resource))
        # Description should contain the resolved path
        self.assertIn("/my-workload/dev/lambda/handler/arn", result["description"])

    # -------------------------------------------------------------------------
    # Output structure tests (Requirement 4.1, 4.2, 4.3)
    # -------------------------------------------------------------------------

    def test_output_structure_completeness(self):
        """Output structure contains SID, nag suppression, and description with SSM path.

        Validates: Requirements 4.1, 4.2, 4.3
        """
        permission = {"lambda": "invoke", "ssm_arn": "/app/dev/lambda/target/arn"}
        result = self.policy_docs.get_permission_details(permission)

        # SID is derived from the SSM path (Requirement 4.1)
        self.assertIn("LambdaInvokeSsm", result["sid"])
        self.assertTrue(len(result["sid"]) > len("LambdaInvokeSsm"))

        # Nag suppression entry (Requirement 4.2)
        self.assertEqual(result["nag"]["id"], "AwsSolutions-IAM5")
        self.assertIn("/app/dev/lambda/target/arn", result["nag"]["reason"])

        # Description includes SSM path (Requirement 4.3)
        self.assertIn("/app/dev/lambda/target/arn", result["description"])
        self.assertIn("SSM", result["description"])


if __name__ == "__main__":
    unittest.main()
