"""
Unit tests for AppSyncKeySeeder utility with mocked boto3 calls.

Follows the house style of test_cognito_trigger_attachment.py:
``@patch.object(AppSyncKeySeeder, "_get_client")`` returning per-service
MagicMock clients, and ``botocore.exceptions.ClientError`` for not-found paths.
No moto (not a dependency here); no real AWS calls.
"""

import time
import logging

from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from cdk_factory.utilities.appsync_key_seeder import (
    AppSyncKeySeeder,
    DEFAULT_MIN_REMAINING_SECONDS,
    NEW_KEY_TTL_SECONDS,
)

API_ID = "abcd1234"
API_ID_SSM_PATH = "/my-app/dev/appsync-events/realtime/api-id"
SECRET_ID = "realtime/appsync-events/api-key"


def _far_future() -> int:
    """Epoch well beyond the usable threshold (~30 days out)."""
    return int(time.time()) + 30 * 24 * 3600


def _near_expiry() -> int:
    """Epoch inside the usable threshold (~1 day out) — treated as absent."""
    return int(time.time()) + 24 * 3600


def _not_found_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def _build_clients(
    *,
    ssm_value=API_ID,
    api_keys=None,
    secret_value=None,
    secret_missing=False,
):
    """Build mocked ssm/appsync/secretsmanager clients + a client factory.

    Returns (factory, {service: mock}) so tests can assert on call args.
    """
    ssm = MagicMock()
    if ssm_value is None:
        ssm.get_parameter.side_effect = _not_found_error("ParameterNotFound")
    else:
        ssm.get_parameter.return_value = {"Parameter": {"Value": ssm_value}}

    appsync = MagicMock()
    appsync.list_api_keys.return_value = {"apiKeys": api_keys or []}
    # create_api_key returns a freshly minted key id by default
    appsync.create_api_key.return_value = {
        "apiKey": {"id": "da2-CREATED", "expires": _far_future()}
    }

    secrets = MagicMock()
    if secret_missing:
        secrets.get_secret_value.side_effect = _not_found_error(
            "ResourceNotFoundException"
        )
    else:
        secrets.get_secret_value.return_value = {"SecretString": secret_value}

    clients = {"ssm": ssm, "appsync": appsync, "secretsmanager": secrets}

    def factory(service, role_arn=None):
        return clients[service]

    return factory, clients


class TestAppSyncKeySeeder:
    """Test AppSyncKeySeeder with mocked boto3."""

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_create_when_absent_then_seed(self, mock_get_client):
        """No keys exist -> create one ~1yr out and seed the secret with its id."""
        factory, clients = _build_clients(api_keys=[], secret_missing=True)
        mock_get_client.side_effect = factory

        before = int(time.time())
        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)
        after = int(time.time())

        clients["appsync"].create_api_key.assert_called_once()
        create_kwargs = clients["appsync"].create_api_key.call_args.kwargs
        assert create_kwargs["apiId"] == API_ID
        # expires ~1 year out from "now"
        assert before + NEW_KEY_TTL_SECONDS <= create_kwargs["expires"] <= (
            after + NEW_KEY_TTL_SECONDS
        )

        clients["secretsmanager"].put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-CREATED"
        )

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_reuse_usable_key_no_create(self, mock_get_client):
        """A usable key (>7d) exists -> reuse newest, do not create."""
        factory, clients = _build_clients(
            api_keys=[{"id": "da2-REUSE", "expires": _far_future()}],
            secret_value="REPLACE_ME",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["appsync"].create_api_key.assert_not_called()
        clients["secretsmanager"].put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-REUSE"
        )

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_reseed_on_rotation(self, mock_get_client):
        """Live key id differs from the stored secret -> re-seed with the new id."""
        factory, clients = _build_clients(
            api_keys=[{"id": "da2-NEW", "expires": _far_future()}],
            secret_value="da2-OLD",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["secretsmanager"].put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-NEW"
        )

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_no_op_when_correct(self, mock_get_client):
        """Stored secret already equals the live key id -> no write."""
        factory, clients = _build_clients(
            api_keys=[{"id": "da2-SAME", "expires": _far_future()}],
            secret_value="da2-SAME",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["appsync"].create_api_key.assert_not_called()
        clients["secretsmanager"].put_secret_value.assert_not_called()

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_reseed_over_placeholder(self, mock_get_client):
        """Secret currently REPLACE_ME -> write the live key id."""
        factory, clients = _build_clients(
            api_keys=[{"id": "da2-REAL", "expires": _far_future()}],
            secret_value="REPLACE_ME",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["secretsmanager"].put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-REAL"
        )

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_reads_api_id_from_ssm_path(self, mock_get_client):
        """api id is read from exactly APPSYNC_API_ID_SSM_PATH and used as apiId."""
        factory, clients = _build_clients(
            ssm_value=API_ID,
            api_keys=[{"id": "da2-X", "expires": _far_future()}],
            secret_value="REPLACE_ME",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["ssm"].get_parameter.assert_called_once_with(Name=API_ID_SSM_PATH)
        clients["appsync"].list_api_keys.assert_called_once_with(apiId=API_ID)

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_expired_or_near_expiry_key_treated_as_absent(self, mock_get_client):
        """Only a near-expiry key (<7d) exists -> create a fresh key."""
        factory, clients = _build_clients(
            api_keys=[{"id": "da2-STALE", "expires": _near_expiry()}],
            secret_value="REPLACE_ME",
        )
        mock_get_client.side_effect = factory

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        clients["appsync"].create_api_key.assert_called_once()
        clients["secretsmanager"].put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-CREATED"
        )

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_secret_value_never_logged(self, mock_get_client, caplog):
        """The key id string must not appear in any log record."""
        factory, _ = _build_clients(
            api_keys=[{"id": "da2-SECRET-VALUE", "expires": _far_future()}],
            secret_value="REPLACE_ME",
        )
        mock_get_client.side_effect = factory

        with caplog.at_level(logging.DEBUG):
            AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        for record in caplog.records:
            assert "da2-SECRET-VALUE" not in record.getMessage()

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_missing_api_id_raises(self, mock_get_client):
        """Missing api-id in SSM is a hard failure (so main() exits non-zero)."""
        factory, _ = _build_clients(ssm_value=None)
        mock_get_client.side_effect = factory

        try:
            AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)
            assert False, "expected RuntimeError for missing api-id"
        except RuntimeError:
            pass

    @patch.object(AppSyncKeySeeder, "_get_client")
    def test_list_api_keys_paginates(self, mock_get_client):
        """get_usable_key follows nextToken across pages."""
        ssm = MagicMock()
        ssm.get_parameter.return_value = {"Parameter": {"Value": API_ID}}
        appsync = MagicMock()
        appsync.list_api_keys.side_effect = [
            {"apiKeys": [{"id": "da2-P1", "expires": _far_future()}], "nextToken": "t"},
            {"apiKeys": [{"id": "da2-P2", "expires": _far_future() + 10}]},
        ]
        secrets = MagicMock()
        secrets.get_secret_value.return_value = {"SecretString": "REPLACE_ME"}
        clients = {"ssm": ssm, "appsync": appsync, "secretsmanager": secrets}
        mock_get_client.side_effect = lambda service, role_arn=None: clients[service]

        AppSyncKeySeeder(region="us-east-1").seed(API_ID_SSM_PATH, SECRET_ID)

        assert appsync.list_api_keys.call_count == 2
        # newest (max expires) is da2-P2 -> that is what gets seeded
        secrets.put_secret_value.assert_called_once_with(
            SecretId=SECRET_ID, SecretString="da2-P2"
        )
        _ = DEFAULT_MIN_REMAINING_SECONDS  # referenced to keep import meaningful
