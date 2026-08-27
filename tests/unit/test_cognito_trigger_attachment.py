"""
Unit tests for CognitoTriggerAttachment utility with mocked boto3 calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from cdk_factory.utilities.cognito_trigger_attachment import (
    CognitoTriggerAttachment,
    _parse_triggers_spec,
)


class TestCognitoTriggerAttachment:
    """Test CognitoTriggerAttachment with mocked boto3."""

    @patch.object(CognitoTriggerAttachment, "_get_client")
    def test_attach_triggers_merges_existing_config(self, mock_get_client):
        """Verify describe-then-merge preserves existing LambdaConfig entries."""
        mock_cognito = MagicMock()
        mock_lambda = MagicMock()

        # Pool already has a PreSignUp trigger configured
        mock_cognito.describe_user_pool.return_value = {
            "UserPool": {
                "LambdaConfig": {
                    "PreSignUp": "arn:aws:lambda:us-east-1:123:function:existing-presignup"
                },
                "DeletionProtection": "ACTIVE",
            }
        }

        def client_factory(service, role_arn=None):
            return mock_cognito if service == "cognito-idp" else mock_lambda

        mock_get_client.side_effect = client_factory

        attacher = CognitoTriggerAttachment()
        attacher.attach_triggers(
            user_pool_id="us-east-1_ABC",
            triggers={
                "PostAuthentication": "arn:aws:lambda:us-east-1:123:function:post-auth"
            },
            account="123456789012",
            region="us-east-1",
        )

        # Verify update_user_pool was called
        mock_cognito.update_user_pool.assert_called_once()
        call_kwargs = mock_cognito.update_user_pool.call_args.kwargs

        # The merged config should contain BOTH the existing and new trigger
        assert call_kwargs["LambdaConfig"]["PreSignUp"] == (
            "arn:aws:lambda:us-east-1:123:function:existing-presignup"
        )
        assert call_kwargs["LambdaConfig"]["PostAuthentication"] == (
            "arn:aws:lambda:us-east-1:123:function:post-auth"
        )
        # Deletion protection should be preserved
        assert call_kwargs["DeletionProtection"] == "ACTIVE"

    @patch.object(CognitoTriggerAttachment, "_get_client")
    def test_attach_triggers_grants_invoke_permission(self, mock_get_client):
        """Verify each trigger Lambda gets a cognito-idp invoke permission."""
        mock_cognito = MagicMock()
        mock_lambda = MagicMock()
        mock_cognito.describe_user_pool.return_value = {"UserPool": {"LambdaConfig": {}}}

        def client_factory(service, role_arn=None):
            return mock_cognito if service == "cognito-idp" else mock_lambda

        mock_get_client.side_effect = client_factory

        attacher = CognitoTriggerAttachment()
        attacher.attach_triggers(
            user_pool_id="us-east-1_ABC",
            triggers={
                "PreTokenGeneration": "arn:aws:lambda:us-east-1:123:function:pre-token"
            },
            account="123456789012",
            region="us-east-1",
        )

        mock_lambda.add_permission.assert_called_once()
        perm_kwargs = mock_lambda.add_permission.call_args.kwargs
        assert perm_kwargs["Principal"] == "cognito-idp.amazonaws.com"
        assert perm_kwargs["StatementId"] == "CognitoPreTokenGeneration"
        assert (
            perm_kwargs["SourceArn"]
            == "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC"
        )

    @patch.object(CognitoTriggerAttachment, "_get_client")
    def test_grant_permission_idempotent(self, mock_get_client):
        """Verify an existing permission (ResourceConflictException) is a no-op."""
        mock_lambda = MagicMock()
        mock_lambda.add_permission.side_effect = ClientError(
            {"Error": {"Code": "ResourceConflictException", "Message": "exists"}},
            "AddPermission",
        )
        mock_get_client.return_value = mock_lambda

        attacher = CognitoTriggerAttachment()
        # Should not raise
        attacher.grant_cognito_invoke_permission(
            function_arn="arn:aws:lambda:us-east-1:123:function:x",
            user_pool_arn="arn:aws:cognito-idp:us-east-1:123:userpool/us-east-1_ABC",
            statement_id="CognitoPostAuthentication",
        )

    @patch.object(CognitoTriggerAttachment, "_get_client")
    def test_no_update_when_config_unchanged(self, mock_get_client):
        """Verify update_user_pool is NOT called when triggers already match."""
        mock_cognito = MagicMock()
        mock_lambda = MagicMock()
        mock_cognito.describe_user_pool.return_value = {
            "UserPool": {
                "LambdaConfig": {
                    "PostAuthentication": "arn:aws:lambda:us-east-1:123:function:post-auth"
                }
            }
        }

        def client_factory(service, role_arn=None):
            return mock_cognito if service == "cognito-idp" else mock_lambda

        mock_get_client.side_effect = client_factory

        attacher = CognitoTriggerAttachment()
        attacher.attach_triggers(
            user_pool_id="us-east-1_ABC",
            triggers={
                "PostAuthentication": "arn:aws:lambda:us-east-1:123:function:post-auth"
            },
            account="123456789012",
            region="us-east-1",
        )

        mock_cognito.update_user_pool.assert_not_called()

    @patch.object(CognitoTriggerAttachment, "get_ssm_parameter")
    def test_resolve_trigger_arn_from_ssm(self, mock_get_ssm):
        """Verify trigger ARN resolution builds the correct SSM path."""
        mock_get_ssm.return_value = "arn:aws:lambda:us-east-1:123:function:post-auth"

        attacher = CognitoTriggerAttachment()
        arn = attacher.resolve_trigger_arn(
            "my-app/dev/lambda", "cognito-post-auth-trigger"
        )

        assert arn == "arn:aws:lambda:us-east-1:123:function:post-auth"
        # Verify the normalized SSM path
        mock_get_ssm.assert_called_once()
        called_path = mock_get_ssm.call_args.args[0]
        assert called_path == "/my-app/dev/lambda/cognito-post-auth-trigger/arn"


class TestParseTriggersSpec:
    """Test the COGNITO_TRIGGERS spec parser."""

    def test_parse_valid_spec(self):
        """Verify a valid spec resolves each trigger to its ARN."""
        attacher = MagicMock()
        attacher.resolve_trigger_arn.side_effect = lambda ns, name, role_arn=None: (
            f"arn:aws:lambda:us-east-1:123:function:{name}"
        )

        result = _parse_triggers_spec(
            "PreTokenGeneration=pre-token,PostAuthentication=post-auth",
            "my-app/dev/lambda",
            attacher,
            None,
        )

        assert result == {
            "PreTokenGeneration": "arn:aws:lambda:us-east-1:123:function:pre-token",
            "PostAuthentication": "arn:aws:lambda:us-east-1:123:function:post-auth",
        }

    def test_parse_skips_unknown_trigger_key(self):
        """Verify unknown trigger keys are skipped."""
        attacher = MagicMock()
        attacher.resolve_trigger_arn.return_value = "arn:aws:lambda:us-east-1:123:function:x"

        result = _parse_triggers_spec(
            "NotARealTrigger=some-lambda",
            "my-app/dev/lambda",
            attacher,
            None,
        )

        assert result == {}

    def test_parse_skips_unresolved_arn(self):
        """Verify triggers whose ARN can't be resolved are skipped."""
        attacher = MagicMock()
        attacher.resolve_trigger_arn.return_value = None

        result = _parse_triggers_spec(
            "PostAuthentication=missing-lambda",
            "my-app/dev/lambda",
            attacher,
            None,
        )

        assert result == {}
