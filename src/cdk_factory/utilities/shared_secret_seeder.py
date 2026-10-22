"""
Shared-Secret Seeder Utility

Fills a Secrets Manager secret that IaC created with a placeholder with a
strong, randomly generated value — exactly once. This runs as a post-deploy
pipeline step (after the secrets stack has created the secret with its
``REPLACE_ME`` placeholder) and:
    1. Reads the current secret value.
    2. If the value is MISSING (secret exists but has no / empty value) OR equals
       the placeholder, generates a strong random value with
       ``secrets.token_urlsafe`` and writes it via ``put_secret_value``.
    3. If the secret already holds a real (non-placeholder, non-empty) value it
       is a NO-OP — the existing value is NEVER overwritten.

This is a GENERIC utility: it does not know about any particular secret. It is
the generate-a-value counterpart to ``appsync_key_seeder`` (which DISCOVERS an
AppSync key); it mirrors that module's structure, cross-account-role support,
logging discipline, CLI/env contract, exit codes, and idempotency, and differs
only in that it GENERATES the value instead of discovering it.

Idempotency / rotation-safety:
    Writes happen only when the stored value is the placeholder or missing. A
    secret that already carries a real value is left untouched, so re-running on
    every deploy does NOT rotate a live secret.

Missing-secret contract (IMPORTANT):
    The IaC secrets stack is responsible for CREATING the secret with the
    ``REPLACE_ME`` placeholder. This seeder only FILLS a placeholder — it does
    NOT create secrets. Therefore a secret that does not exist yet
    (``ResourceNotFoundException``) is treated as a hard ERROR (raises
    ``RuntimeError``), not as "generate a new one". This deliberately
    distinguishes:
        - secret does not exist            -> ERROR (raise)
        - secret exists but value empty    -> generate + write
        - secret exists with placeholder   -> generate + write
        - secret exists with a real value  -> no-op

The secret value is NEVER logged (mirrors the appsync seeder's never-log-value
discipline). Only the secret-id, booleans, and paths are logged.

Usage as a CLI (called from pipeline post_steps):

    export AWS_REGION="us-east-1"
    export SECRET_ID="event-bus/ingress/shared-secret"
    # Optional overrides:
    export SECRET_PLACEHOLDER="REPLACE_ME"
    # Optional cross-account role (single-account pipelines leave this unset):
    export CROSS_ACCOUNT_ROLE_ARN="arn:aws:iam::123456789012:role/DevOpsCrossAccountAccessRole"
    python -m cdk_factory.utilities.shared_secret_seeder

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
import sys
import secrets as _secrets
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# IaC seeds the secret with this placeholder; treat it as "needs seeding".
PLACEHOLDER_VALUE = "REPLACE_ME"

# Default entropy (bytes) for the generated value. token_urlsafe(32) yields a
# ~43-char URL-safe string (256 bits of entropy).
DEFAULT_TOKEN_BYTES = 32


class SecretNotFoundError(RuntimeError):
    """Raised when the target secret does not exist.

    The IaC secrets stack is responsible for creating the secret with its
    placeholder; this seeder only fills a placeholder and never creates secrets.
    """


class SharedSecretSeeder:
    """Generates and seeds a strong random value into a placeholder secret."""

    def __init__(self, region: Optional[str] = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

    def _get_client(self, service: str, role_arn: Optional[str] = None):
        """Get a boto3 client, optionally assuming a cross-account role."""
        if role_arn:
            sts = boto3.client("sts")
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"shared-secret-seeder-{service}",
            )["Credentials"]
            return boto3.client(
                service,
                region_name=self.region,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        return boto3.client(service, region_name=self.region)

    def read_secret(
        self, secret_id: str, role_arn: Optional[str] = None
    ) -> Optional[str]:
        """Read the current secret string.

        Returns the stored value (stripped), or None when the secret exists but
        holds no / an empty value. Raises ``SecretNotFoundError`` when the secret
        itself does not exist — the caller must NOT create it here.
        """
        client = self._get_client("secretsmanager", role_arn)
        try:
            response = client.get_secret_value(SecretId=secret_id)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                # Missing secret is a hard error: IaC must have created it first.
                raise SecretNotFoundError(
                    f"secret '{secret_id}' does not exist. The IaC secrets stack "
                    "must create it with a placeholder before this seeder runs; "
                    "this seeder only fills a placeholder and never creates secrets."
                ) from e
            raise
        value = response.get("SecretString")
        return value.strip() if value else None

    def _generate_value(self, token_bytes: int = DEFAULT_TOKEN_BYTES) -> str:
        """Generate a strong, URL-safe random secret value."""
        return _secrets.token_urlsafe(token_bytes)

    def seed(
        self,
        secret_id: str,
        role_arn: Optional[str] = None,
        placeholder: str = PLACEHOLDER_VALUE,
        token_bytes: int = DEFAULT_TOKEN_BYTES,
    ) -> bool:
        """Seed the secret with a generated value if it is a placeholder/empty.

        Idempotent and rotation-safe: generates + writes a new value ONLY when
        the stored value is missing (empty) or equals ``placeholder``. A secret
        that already carries a real value is left untouched (no-op).

        Returns True on success. Raises ``SecretNotFoundError`` when the secret
        does not exist (the IaC secrets stack must create it first).
        """
        current = self.read_secret(secret_id, role_arn=role_arn)

        needs_seed = current is None or current == placeholder
        if not needs_seed:
            # Real value already present — never overwrite.
            logger.info(
                f"no-op: secret '{secret_id}' already set "
                f"(already_set=True, wrote_secret=False)"
            )
            return True

        # Missing or placeholder -> generate and write a strong random value.
        # NEVER log the generated value.
        new_value = self._generate_value(token_bytes=token_bytes)
        client = self._get_client("secretsmanager", role_arn)
        client.put_secret_value(SecretId=secret_id, SecretString=new_value)
        logger.info(
            f"seeded secret '{secret_id}' (generated=True, wrote_secret=True)"
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
    secret_id = _norm(os.getenv("SECRET_ID"))
    role_arn = _norm(os.getenv("CROSS_ACCOUNT_ROLE_ARN"))
    placeholder = _norm(os.getenv("SECRET_PLACEHOLDER")) or PLACEHOLDER_VALUE

    if not secret_id:
        print("ERROR: SECRET_ID is required", file=sys.stderr)
        sys.exit(1)

    seeder = SharedSecretSeeder(region=region)

    try:
        seeder.seed(
            secret_id=secret_id,
            role_arn=role_arn,
            placeholder=placeholder,
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("shared secret seeding failed")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info("shared secret seeding complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
