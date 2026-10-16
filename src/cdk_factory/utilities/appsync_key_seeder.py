"""
AppSync Events API-Key Seeder Utility

Ensures the realtime AppSync Events API has a usable publish API key and copies
that key into the Secrets Manager secret the realtime publisher reads. This runs
as a post-deploy pipeline step (after the AppSync Events API exists and its api-id
is published to SSM), discovers the api-id from SSM, and:
    1. Lists the AppSync API keys; if a usable (non-expired, not expiring soon)
       key exists it reuses the newest one, otherwise it creates a new key.
    2. Writes the key into the realtime api-key secret ONLY when the stored value
       differs from the live key (idempotent; re-seeds automatically on rotation).

Key-value choice (confirmed against the realtime publisher):
    For AppSync *Events*, ``appsync list-api-keys`` / ``create-api-key`` return
    ``apiKey.id`` — the ``da2-...`` string that IS the ``x-api-key`` value a client
    sends on publish. The publisher sets the header directly from the secret:
        headers["x-api-key"] = cfg.api_key
        (geek_cafe_saas_sdk/.../notifications/realtime/publisher.py:101-102)
    and the resolver's ``_read_api_key()`` accepts a raw string first, only parsing
    JSON when the value starts with ``{``
        (geek_cafe_saas_sdk/.../notifications/realtime/endpoint_resolver.py).
    Therefore this seeder stores the plain ``apiKey["id"]`` string as the secret's
    ``SecretString`` — exactly the string the publisher must send. No JSON wrapper.

The secret value is NEVER logged (mirrors the resolver's "api_key must never appear
in a repr/log" discipline). Only the api-id, booleans, and paths are logged.

Usage as a CLI (called from pipeline post_steps):

    export WORKLOAD_NAME="my-app"
    export ENVIRONMENT="dev"
    export AWS_REGION="us-east-1"
    export APPSYNC_API_ID_SSM_PATH="/my-app/dev/appsync-events/realtime/api-id"
    export SECRET_ID="realtime/appsync-events/api-key"
    # Optional cross-account role (single-account pipelines leave this unset):
    export CROSS_ACCOUNT_ROLE_ARN="arn:aws:iam::123456789012:role/DevOpsCrossAccountAccessRole"
    python -m cdk_factory.utilities.appsync_key_seeder

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
import sys
import time
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# A key is "usable" only if it has more than this many seconds of life left.
# Matches design §5.2 (">7 days remaining"); near-expiry/expired keys are treated
# as absent so the seeder mints a fresh one before the old one lapses.
DEFAULT_MIN_REMAINING_SECONDS = 7 * 24 * 3600

# New keys are created with ~1 year of validity.
NEW_KEY_TTL_SECONDS = 365 * 24 * 3600

# IaC seeds the secret with this placeholder; treat it as "needs seeding".
PLACEHOLDER_VALUE = "REPLACE_ME"


class AppSyncKeySeeder:
    """Seeds the realtime AppSync Events publish key into Secrets Manager."""

    def __init__(self, region: Optional[str] = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

    def _get_client(self, service: str, role_arn: Optional[str] = None):
        """Get a boto3 client, optionally assuming a cross-account role."""
        if role_arn:
            sts = boto3.client("sts")
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"appsync-key-seeder-{service}",
            )["Credentials"]
            return boto3.client(
                service,
                region_name=self.region,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        return boto3.client(service, region_name=self.region)

    def get_ssm_parameter(
        self, parameter_name: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Read an SSM parameter. Returns None if not found (idempotent)."""
        from cdk_factory.utilities.ssm_path_utils import normalize_ssm_path

        parameter_name = normalize_ssm_path(parameter_name)
        client = self._get_client("ssm", role_arn)
        try:
            return client.get_parameter(Name=parameter_name)["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.warning(f"SSM parameter not found: {parameter_name}")
                return None
            raise

    def get_usable_key(
        self,
        api_id: str,
        role_arn: Optional[str] = None,
        min_remaining_seconds: int = DEFAULT_MIN_REMAINING_SECONDS,
    ) -> Optional[dict]:
        """Return the newest non-expiring AppSync API key, or None.

        Lists all keys (paginating on ``nextToken``) and keeps those whose
        ``expires`` epoch is more than ``min_remaining_seconds`` in the future.
        Returns the newest usable key (max ``expires``) or None when none qualify.
        """
        client = self._get_client("appsync", role_arn)
        cutoff = int(time.time()) + min_remaining_seconds

        keys: list = []
        next_token: Optional[str] = None
        while True:
            kwargs = {"apiId": api_id}
            if next_token:
                kwargs["nextToken"] = next_token
            response = client.list_api_keys(**kwargs)
            keys.extend(response.get("apiKeys", []))
            next_token = response.get("nextToken")
            if not next_token:
                break

        usable = [k for k in keys if int(k.get("expires", 0)) > cutoff]
        if not usable:
            return None
        return max(usable, key=lambda k: int(k.get("expires", 0)))

    def create_key(self, api_id: str, role_arn: Optional[str] = None) -> dict:
        """Create a new AppSync API key (~1 year) and return the ``apiKey`` dict."""
        client = self._get_client("appsync", role_arn)
        expires = int(time.time()) + NEW_KEY_TTL_SECONDS
        response = client.create_api_key(apiId=api_id, expires=expires)
        # Do NOT log the key id/value — it is the publish secret.
        logger.info(f"created new api key for apiId={api_id}")
        return response["apiKey"]

    def read_secret(
        self, secret_id: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Read the current secret string, or None if the secret doesn't exist."""
        client = self._get_client("secretsmanager", role_arn)
        try:
            response = client.get_secret_value(SecretId=secret_id)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.warning(f"secret not found: {secret_id}")
                return None
            raise
        value = response.get("SecretString")
        return value.strip() if value else None

    def seed(
        self,
        api_id_ssm_path: str,
        secret_id: str,
        role_arn: Optional[str] = None,
    ) -> bool:
        """Resolve the api-id, ensure a usable key exists, and seed the secret.

        Idempotent and rotation-safe: writes the secret only when the stored
        value is missing, the placeholder, or differs from the live key.

        Returns True on success. Raises on hard failure (missing api-id).
        """
        api_id = self.get_ssm_parameter(api_id_ssm_path, role_arn=role_arn)
        if not api_id:
            raise RuntimeError(
                f"AppSync api-id not found at SSM path '{api_id_ssm_path}'. "
                "Ensure deploy-realtime-appsync ran before this step."
            )
        logger.info(f"resolved AppSync api-id from {api_id_ssm_path}")

        key = self.get_usable_key(api_id, role_arn=role_arn)
        if key is None:
            key = self.create_key(api_id, role_arn=role_arn)
            reused = False
        else:
            logger.info(f"reusing existing usable api key for apiId={api_id}")
            reused = True

        # For AppSync Events, the key's id string IS the x-api-key publish value.
        live_key = key["id"]

        current = self.read_secret(secret_id, role_arn=role_arn)
        needs_write = (
            current is None
            or current == PLACEHOLDER_VALUE
            or current != live_key
        )

        if needs_write:
            client = self._get_client("secretsmanager", role_arn)
            client.put_secret_value(SecretId=secret_id, SecretString=live_key)
            logger.info(
                f"seeded secret '{secret_id}' "
                f"(reused_existing_key={reused}, wrote_secret=True)"
            )
        else:
            logger.info(
                f"no-op: secret '{secret_id}' already current "
                f"(reused_existing_key={reused}, wrote_secret=False)"
            )
        return True


def main():
    """CLI entry point for pipeline post_steps."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    def _norm(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v or v.lower() == "none":
            return None
        return v

    region = os.getenv("AWS_REGION", "us-east-1")
    api_id_ssm_path = _norm(os.getenv("APPSYNC_API_ID_SSM_PATH"))
    secret_id = _norm(os.getenv("SECRET_ID"))
    role_arn = _norm(os.getenv("CROSS_ACCOUNT_ROLE_ARN"))

    if not api_id_ssm_path:
        print("ERROR: APPSYNC_API_ID_SSM_PATH is required", file=sys.stderr)
        sys.exit(1)

    if not secret_id:
        print("ERROR: SECRET_ID is required", file=sys.stderr)
        sys.exit(1)

    seeder = AppSyncKeySeeder(region=region)

    try:
        seeder.seed(
            api_id_ssm_path=api_id_ssm_path,
            secret_id=secret_id,
            role_arn=role_arn,
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("AppSync key seeding failed")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info("AppSync key seeding complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
