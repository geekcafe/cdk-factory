"""
Unit tests for SharedSecretSeeder utility with mocked boto3 calls.

Follows the house style of test_appsync_key_seeder.py:
``@patch.object(SharedSecretSeeder, "_get_client")`` returning a per-service
MagicMock client, and ``botocore.exceptions.ClientError`` for not-found paths.
No moto (not a dependency here); no real AWS calls.
"""

import logging

from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

import pytest

from cdk_factory.utilities.shared_secret_seeder import (
    SharedSecretSeeder,
    SecretNotFoundError,
    PLACEHOLDER_VALUE,
)

SECRET_ID = "event-bus/ingress/shared-secret"


def _not_found_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def _build_clients(*, secret_value=None, secret_missing=False):
    """Build a mocked secretsmanager client + a client factory.

    Returns (factory, {service: mock}) so tests can assert on call args.
    """
    secrets = MagicMock()
    if secret_missing:
        secrets.get_secret_value.side_effect = _not_found_error(
            "ResourceNotFoundException"
        )
    else:
        secrets.get_secret_value.return_value = {"SecretString": secret_value}

    clients = {"secretsmanager": secrets}

    def factory(service, role_arn=None):
        return clients[service]

    return factory, clients


class TestSharedSecretSeeder:
    """Test SharedSecretSeeder with mocked boto3."""

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_placeholder_generates_and_writes(self, mock_get_client):
        """Secret currently REPLACE_ME -> generate a strong value and write it."""
        factory, clients = _build_clients(secret_value=PLACEHOLDER_VALUE)
        mock_get_client.side_effect = factory

        result = SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)
        assert result is True

        clients["secretsmanager"].put_secret_value.assert_called_once()
        kwargs = clients["secretsmanager"].put_secret_value.call_args.kwargs
        assert kwargs["SecretId"] == SECRET_ID
        written = kwargs["SecretString"]
        # Never the placeholder, and reasonably long (token_urlsafe(32) ~= 43).
        assert written != PLACEHOLDER_VALUE
        assert len(written) >= 32

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_empty_value_generates_and_writes(self, mock_get_client):
        """Secret exists but value is empty -> generate + write."""
        factory, clients = _build_clients(secret_value="")
        mock_get_client.side_effect = factory

        SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)

        clients["secretsmanager"].put_secret_value.assert_called_once()
        written = clients["secretsmanager"].put_secret_value.call_args.kwargs[
            "SecretString"
        ]
        assert written != PLACEHOLDER_VALUE
        assert len(written) >= 32

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_none_value_generates_and_writes(self, mock_get_client):
        """Secret exists but SecretString is None -> generate + write."""
        factory, clients = _build_clients(secret_value=None)
        mock_get_client.side_effect = factory

        SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)

        clients["secretsmanager"].put_secret_value.assert_called_once()

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_already_set_is_noop(self, mock_get_client):
        """A real value already present -> NO-OP, never overwritten."""
        factory, clients = _build_clients(secret_value="an-already-real-secret-value")
        mock_get_client.side_effect = factory

        result = SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)
        assert result is True

        clients["secretsmanager"].put_secret_value.assert_not_called()

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_missing_secret_raises(self, mock_get_client):
        """Secret does not exist -> hard error (so main() exits non-zero)."""
        factory, clients = _build_clients(secret_missing=True)
        mock_get_client.side_effect = factory

        with pytest.raises(SecretNotFoundError):
            SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)

        clients["secretsmanager"].put_secret_value.assert_not_called()

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_custom_placeholder_is_honored(self, mock_get_client):
        """A configurable placeholder is treated as 'needs seeding'."""
        factory, clients = _build_clients(secret_value="CUSTOM_PLACEHOLDER")
        mock_get_client.side_effect = factory

        SharedSecretSeeder(region="us-east-1").seed(
            SECRET_ID, placeholder="CUSTOM_PLACEHOLDER"
        )

        clients["secretsmanager"].put_secret_value.assert_called_once()

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_custom_token_length(self, mock_get_client):
        """A larger token_bytes produces a longer generated value."""
        factory, clients = _build_clients(secret_value=PLACEHOLDER_VALUE)
        mock_get_client.side_effect = factory

        SharedSecretSeeder(region="us-east-1").seed(SECRET_ID, token_bytes=64)

        written = clients["secretsmanager"].put_secret_value.call_args.kwargs[
            "SecretString"
        ]
        # token_urlsafe(64) ~= 86 chars; comfortably longer than the 32-byte default.
        assert len(written) >= 64

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_generated_value_never_logged(self, mock_get_client, caplog):
        """The generated secret value must not appear in any log record."""
        factory, clients = _build_clients(secret_value=PLACEHOLDER_VALUE)
        mock_get_client.side_effect = factory

        with caplog.at_level(logging.DEBUG):
            SharedSecretSeeder(region="us-east-1").seed(SECRET_ID)

        written = clients["secretsmanager"].put_secret_value.call_args.kwargs[
            "SecretString"
        ]
        for record in caplog.records:
            assert written not in record.getMessage()

    @patch.object(SharedSecretSeeder, "_get_client")
    def test_generate_values_are_random(self, mock_get_client):
        """Two generations produce different values (not a fixed constant)."""
        factory, clients = _build_clients(secret_value=PLACEHOLDER_VALUE)
        mock_get_client.side_effect = factory

        seeder = SharedSecretSeeder(region="us-east-1")
        seeder.seed(SECRET_ID)
        first = clients["secretsmanager"].put_secret_value.call_args.kwargs[
            "SecretString"
        ]
        seeder.seed(SECRET_ID)
        second = clients["secretsmanager"].put_secret_value.call_args.kwargs[
            "SecretString"
        ]
        assert first != second
