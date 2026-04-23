"""
Unit tests for SsmResolver utility with mocked boto3 calls.
"""

import subprocess
import sys

import pytest
from unittest.mock import patch, MagicMock, call
from botocore.exceptions import ClientError

from cdk_factory.utilities.ssm_resolver import SsmResolver, main


class TestSsmResolverLibrary:
    """Test SsmResolver class directly (library usage)."""

    @patch.object(SsmResolver, "_get_client")
    def test_resolve_happy_path_ambient_credentials(self, mock_get_client):
        """Resolve with ambient credentials (no role_arn) returns correct value."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "my-secret-value"}
        }
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        result = resolver.resolve(parameter_name="/app/config/key")

        assert result == "my-secret-value"
        mock_get_client.assert_called_once_with("ssm", role_arn=None, region=None)

    @patch.object(SsmResolver, "_get_client")
    def test_resolve_happy_path_cross_account_role(self, mock_get_client):
        """Resolve with cross-account role returns correct value."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "cross-account-value"}
        }
        mock_get_client.return_value = mock_ssm

        role_arn = "arn:aws:iam::111111111111:role/CrossAccountRole"
        resolver = SsmResolver()
        result = resolver.resolve(parameter_name="/app/config/key", role_arn=role_arn)

        assert result == "cross-account-value"
        mock_get_client.assert_called_once_with("ssm", role_arn=role_arn, region=None)

    @patch.object(SsmResolver, "_get_client")
    def test_with_decryption_always_true(self, mock_get_client):
        """WithDecryption=True is always passed to get_parameter."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "decrypted-value"}
        }
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        resolver.resolve(parameter_name="/app/secure/param")

        mock_ssm.get_parameter.assert_called_once_with(
            Name="/app/secure/param", WithDecryption=True
        )

    @patch.object(SsmResolver, "_get_client")
    def test_region_forwarded_to_client(self, mock_get_client):
        """--region is forwarded to boto3 client."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "regional-value"}}
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        resolver.resolve(parameter_name="/app/config/key", region="eu-west-1")

        mock_get_client.assert_called_once_with(
            "ssm", role_arn=None, region="eu-west-1"
        )

    @patch.object(SsmResolver, "_get_client")
    def test_default_region_when_omitted(self, mock_get_client):
        """Default region (None) when --region is omitted."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "default-region-value"}
        }
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        resolver.resolve(parameter_name="/app/config/key")

        mock_get_client.assert_called_once_with("ssm", role_arn=None, region=None)

    @patch.object(SsmResolver, "_get_client")
    def test_parameter_not_found_exits_with_error(self, mock_get_client):
        """ParameterNotFound exits with code 1 and error message on stderr containing the parameter name."""
        mock_ssm = MagicMock()
        error_response = {
            "Error": {"Code": "ParameterNotFound", "Message": "Parameter not found"}
        }
        mock_ssm.get_parameter.side_effect = ClientError(error_response, "GetParameter")
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        with pytest.raises(SystemExit) as exc_info:
            resolver.resolve(parameter_name="/app/missing/param")

        assert exc_info.value.code == 1

    @patch.object(SsmResolver, "_get_client")
    def test_parameter_not_found_stderr_contains_param_name(
        self, mock_get_client, capsys
    ):
        """ParameterNotFound error message on stderr contains the parameter name."""
        mock_ssm = MagicMock()
        error_response = {
            "Error": {"Code": "ParameterNotFound", "Message": "Parameter not found"}
        }
        mock_ssm.get_parameter.side_effect = ClientError(error_response, "GetParameter")
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        with pytest.raises(SystemExit):
            resolver.resolve(parameter_name="/app/missing/param")

        captured = capsys.readouterr()
        assert "/app/missing/param" in captured.err

    @patch.object(SsmResolver, "_get_client")
    def test_sts_failure_exits_with_error(self, mock_get_client):
        """STS failure exits with code 1 and error message on stderr containing the parameter name."""
        error_response = {
            "Error": {"Code": "AccessDenied", "Message": "Not authorized"}
        }
        mock_get_client.side_effect = ClientError(error_response, "AssumeRole")

        resolver = SsmResolver()
        with pytest.raises(SystemExit) as exc_info:
            resolver.resolve(
                parameter_name="/app/config/key",
                role_arn="arn:aws:iam::999999999999:role/BadRole",
            )

        assert exc_info.value.code == 1

    @patch.object(SsmResolver, "_get_client")
    def test_sts_failure_stderr_contains_param_name(self, mock_get_client, capsys):
        """STS failure error message on stderr contains the parameter name."""
        error_response = {
            "Error": {"Code": "AccessDenied", "Message": "Not authorized"}
        }
        mock_get_client.side_effect = ClientError(error_response, "AssumeRole")

        resolver = SsmResolver()
        with pytest.raises(SystemExit):
            resolver.resolve(
                parameter_name="/app/config/key",
                role_arn="arn:aws:iam::999999999999:role/BadRole",
            )

        captured = capsys.readouterr()
        assert "/app/config/key" in captured.err

    @patch.object(SsmResolver, "_get_client")
    def test_unexpected_client_error_exits_with_code_1(self, mock_get_client):
        """Unexpected ClientError exits with code 1."""
        mock_ssm = MagicMock()
        error_response = {
            "Error": {"Code": "InternalError", "Message": "Something went wrong"}
        }
        mock_ssm.get_parameter.side_effect = ClientError(error_response, "GetParameter")
        mock_get_client.return_value = mock_ssm

        resolver = SsmResolver()
        with pytest.raises(SystemExit) as exc_info:
            resolver.resolve(parameter_name="/app/config/key")

        assert exc_info.value.code == 1

    @patch.object(SsmResolver, "_get_client")
    def test_library_import_and_programmatic_call(self, mock_get_client):
        """Library import and programmatic call works correctly."""
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": "programmatic-value"}
        }
        mock_get_client.return_value = mock_ssm

        # Verify the class is importable and callable as a library
        resolver = SsmResolver()
        value = resolver.resolve(
            parameter_name="/app/lib/param",
            role_arn="arn:aws:iam::111111111111:role/Role",
            region="us-west-2",
        )

        assert value == "programmatic-value"
        mock_get_client.assert_called_once_with(
            "ssm",
            role_arn="arn:aws:iam::111111111111:role/Role",
            region="us-west-2",
        )
        mock_ssm.get_parameter.assert_called_once_with(
            Name="/app/lib/param", WithDecryption=True
        )


class TestSsmResolverCLI:
    """Test CLI entry point and module invocation."""

    def test_module_invocation_via_python_m(self):
        """Module invocation via python -m cdk_factory.utilities.ssm_resolver works."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cdk_factory.utilities.ssm_resolver",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        # --help exits with 0 and shows usage
        assert result.returncode == 0
        assert "--parameter-name" in result.stdout

    def test_missing_parameter_name_exits_non_zero(self):
        """Missing --parameter-name exits non-zero."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cdk_factory.utilities.ssm_resolver",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert (
            "parameter-name" in result.stderr.lower()
            or "required" in result.stderr.lower()
        )
