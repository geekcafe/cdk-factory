"""AWS inspection for the monitor wizard (design §2.4).

A single injectable :class:`AwsInspector` whose boto3 access funnels through a
**client factory** so tests can substitute mocks (matching the
``test_shared_secret_seeder.py`` house style) and so **no client is ever created
at import or at construction** — a client is built lazily only when a method is
invoked (honors the ``no-live-aws-calls`` steering).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Immutable result shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AwsIdentity:
    """Result of ``sts:GetCallerIdentity``."""

    account: str
    arn: str
    user_id: str


@dataclass(frozen=True)
class PipelineSummary:
    """A single CodePipeline pipeline."""

    name: str


@dataclass(frozen=True)
class ConnectionSummary:
    """A single CodeConnections / codestar-connections connection."""

    name: str
    arn: str
    status: str  # e.g. "AVAILABLE", "PENDING", "ERROR"
    provider_type: str  # "GitHub", "Bitbucket", ...


# ---------------------------------------------------------------------------
# Friendly error
# ---------------------------------------------------------------------------


class AwsInspectorError(Exception):
    """Carries a friendly, already-formatted message + optional remediation.

    ``access_denied`` is set True when the underlying cause was an
    ``AccessDenied``/``AccessDeniedException`` on a list call, so callers can
    distinguish a permission problem from a genuinely empty result.
    """

    def __init__(
        self,
        message: str,
        remediation: Optional[str] = None,
        *,
        access_denied: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation
        self.access_denied = access_denied


# Error codes that indicate the operator's credentials/SSO session need refreshing.
_CREDENTIAL_ERROR_CODES = frozenset(
    {
        "ExpiredToken",
        "ExpiredTokenException",
        "UnauthorizedSSOTokenError",
    }
)
_ACCESS_DENIED_CODES = frozenset({"AccessDenied", "AccessDeniedException"})


class AwsInspector:
    """Operator-credential AWS inspection, built lazily, mock-friendly.

    Args:
        client_factory: ``client_factory(service_name) -> boto3 client``. When
            ``None``, a default factory is used that builds a
            ``boto3.Session(profile_name=...).client(service, region_name=...)``
            LAZILY — only when a method is invoked, never at construction/import.
        profile: Optional AWS profile name.
        region: Optional AWS region.
    """

    def __init__(
        self,
        client_factory: Optional[Callable[[str], object]] = None,
        profile: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self._client_factory = client_factory
        self.profile = profile
        self.region = region

    # -- client plumbing ----------------------------------------------------

    def _get_client(self, service: str):
        """Return a boto3 client for *service*, building one lazily if needed.

        The default factory imports boto3 and constructs the session/client only
        when this is first called (never at import/construction).
        """
        if self._client_factory is not None:
            return self._client_factory(service)
        return self._default_client(service)

    def _default_client(self, service: str):
        import boto3  # local import — never at module import time

        session = boto3.Session(profile_name=self.profile)
        if self.region:
            return session.client(service, region_name=self.region)
        return session.client(service)

    def _connections_client(self):
        """Return a CodeConnections client, preferring the modern service name.

        The modern API is the ``codeconnections`` boto3 client; older
        environments expose only ``codestar-connections``. Both share
        ``list_connections``. This is the one place the two names are reconciled.
        """
        try:
            return self._get_client("codeconnections")
        except Exception:  # pragma: no cover - unknown-service / botocore errors
            return self._get_client("codestar-connections")

    # -- inspection API (no AWS until invoked) ------------------------------

    def list_profiles(self) -> List[str]:
        """Return configured AWS profile names (config-file read, no network)."""
        import botocore.session  # local import

        session = botocore.session.Session()
        return list(session.available_profiles)

    def resolve_account(self) -> AwsIdentity:
        """Resolve the current account via ``sts:GetCallerIdentity``."""
        client = self._get_client("sts")
        try:
            resp = client.get_caller_identity()
        except Exception as exc:  # noqa: BLE001 - normalized below
            self._raise_friendly(exc, action="sts:GetCallerIdentity")
        return AwsIdentity(
            account=resp.get("Account", ""),
            arn=resp.get("Arn", ""),
            user_id=resp.get("UserId", ""),
        )

    def list_pipelines(self) -> List[PipelineSummary]:
        """List all CodePipeline pipelines (paginated, flattened)."""
        client = self._get_client("codepipeline")
        out: List[PipelineSummary] = []
        try:
            paginator = client.get_paginator("list_pipelines")
            for page in paginator.paginate():
                for item in page.get("pipelines", []):
                    name = item.get("name")
                    if name:
                        out.append(PipelineSummary(name=name))
        except Exception as exc:  # noqa: BLE001 - normalized below
            self._raise_friendly(exc, action="codepipeline:ListPipelines")
        return out

    def list_connections(self) -> List[ConnectionSummary]:
        """List CodeConnections connections (paginated, flattened)."""
        client = self._connections_client()
        out: List[ConnectionSummary] = []
        try:
            paginator = client.get_paginator("list_connections")
            for page in paginator.paginate():
                for item in page.get("Connections", []):
                    out.append(
                        ConnectionSummary(
                            name=item.get("ConnectionName", ""),
                            arn=item.get("ConnectionArn", ""),
                            status=item.get("ConnectionStatus", ""),
                            provider_type=item.get("ProviderType", ""),
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - normalized below
            self._raise_friendly(exc, action="codeconnections:ListConnections")
        return out

    def put_secret_value(self, secret_id: str, secret_string: str) -> None:
        """Write a single secret value (one ``secretsmanager:PutSecretValue``)."""
        client = self._get_client("secretsmanager")
        try:
            client.put_secret_value(SecretId=secret_id, SecretString=secret_string)
        except Exception as exc:  # noqa: BLE001 - normalized below
            self._raise_friendly(exc, action="secretsmanager:PutSecretValue")

    # -- error normalization ------------------------------------------------

    def _raise_friendly(self, exc: Exception, *, action: str) -> None:
        """Convert a boto3/botocore exception into an :class:`AwsInspectorError`.

        Never lets a raw boto3 traceback escape. Credential/SSO problems get an
        ``aws sso login`` remediation; AccessDenied sets ``access_denied=True``.
        """
        # Import lazily so this module stays import-light and AWS-free.
        from botocore.exceptions import (
            ClientError,
            NoCredentialsError,
            SSOTokenLoadError,
        )

        profile_hint = self.profile or "<profile>"
        login_remediation = f"Run: aws sso login --profile {profile_hint}"

        if isinstance(exc, NoCredentialsError):
            raise AwsInspectorError(
                f"No AWS credentials available for {action}.",
                remediation=login_remediation,
            ) from exc

        if isinstance(exc, SSOTokenLoadError):
            raise AwsInspectorError(
                f"Your SSO session for {action} is not loaded or has expired.",
                remediation=login_remediation,
            ) from exc

        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            if code in _CREDENTIAL_ERROR_CODES:
                raise AwsInspectorError(
                    f"Your AWS session for {action} has expired.",
                    remediation=login_remediation,
                ) from exc
            if code in _ACCESS_DENIED_CODES:
                raise AwsInspectorError(
                    f"Access denied for {action}.",
                    remediation=f"Grant permission for {action} and retry.",
                    access_denied=True,
                ) from exc
            raise AwsInspectorError(
                f"AWS call failed for {action}: {code or exc}.",
            ) from exc

        # Unknown exception type — still never leak a raw traceback upward.
        raise AwsInspectorError(f"AWS call failed for {action}: {exc}.") from exc
