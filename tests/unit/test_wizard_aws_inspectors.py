"""Unit tests for the wizard AwsInspector (design §2.4 / §2.11).

House style: client-factory injection with per-service MagicMock clients +
botocore.exceptions.ClientError. No real AWS, no client at construction/import.
"""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from cdk_factory.wizard.aws_inspectors import (
    AwsIdentity,
    AwsInspector,
    AwsInspectorError,
    ConnectionSummary,
    PipelineSummary,
)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def _paginator(pages):
    pag = MagicMock()
    pag.paginate.return_value = pages
    return pag


# ---------------------------------------------------------------------------
# No AWS at construction / import
# ---------------------------------------------------------------------------


def test_no_client_built_at_construction():
    calls = []

    def factory(service):
        calls.append(service)
        return MagicMock()

    AwsInspector(client_factory=factory)
    assert calls == []  # nothing built until a method runs


def test_default_factory_not_invoked_without_method_call():
    # No client_factory + no method call -> must not touch boto3.
    inspector = AwsInspector(profile="p", region="us-east-1")
    assert inspector.profile == "p"


# ---------------------------------------------------------------------------
# resolve_account (STS)
# ---------------------------------------------------------------------------


def test_resolve_account_returns_identity():
    sts = MagicMock()
    sts.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:iam::123456789012:user/me",
        "UserId": "AIDEXAMPLE",
    }
    inspector = AwsInspector(client_factory=lambda s: {"sts": sts}[s])
    identity = inspector.resolve_account()
    assert isinstance(identity, AwsIdentity)
    assert identity.account == "123456789012"
    assert identity.user_id == "AIDEXAMPLE"


# ---------------------------------------------------------------------------
# list_pipelines pagination flatten
# ---------------------------------------------------------------------------


def test_list_pipelines_flattens_pages():
    cp = MagicMock()
    cp.get_paginator.return_value = _paginator(
        [
            {"pipelines": [{"name": "a"}, {"name": "b"}]},
            {"pipelines": [{"name": "c"}]},
        ]
    )
    inspector = AwsInspector(client_factory=lambda s: {"codepipeline": cp}[s])
    result = inspector.list_pipelines()
    assert result == [
        PipelineSummary("a"),
        PipelineSummary("b"),
        PipelineSummary("c"),
    ]


# ---------------------------------------------------------------------------
# list_connections pagination flatten
# ---------------------------------------------------------------------------


def test_list_connections_flattens_pages():
    cc = MagicMock()
    cc.get_paginator.return_value = _paginator(
        [
            {
                "Connections": [
                    {
                        "ConnectionName": "gh",
                        "ConnectionArn": "arn:aws:codeconnections:us-east-1:123456789012:connection/abc",
                        "ConnectionStatus": "AVAILABLE",
                        "ProviderType": "GitHub",
                    }
                ]
            }
        ]
    )
    inspector = AwsInspector(client_factory=lambda s: {"codeconnections": cc}[s])
    result = inspector.list_connections()
    assert result == [
        ConnectionSummary(
            name="gh",
            arn="arn:aws:codeconnections:us-east-1:123456789012:connection/abc",
            status="AVAILABLE",
            provider_type="GitHub",
        )
    ]


def test_list_connections_falls_back_to_codestar():
    cc = MagicMock()
    cc.get_paginator.return_value = _paginator([{"Connections": []}])

    def factory(service):
        if service == "codeconnections":
            raise ValueError("Unknown service: codeconnections")
        assert service == "codestar-connections"
        return cc

    inspector = AwsInspector(client_factory=factory)
    assert inspector.list_connections() == []
    cc.get_paginator.assert_called_once_with("list_connections")


# ---------------------------------------------------------------------------
# list_profiles — no network
# ---------------------------------------------------------------------------


def test_list_profiles_no_network(monkeypatch):
    class _FakeSession:
        available_profiles = ["default", "geekcafe-prod"]

    import botocore.session

    monkeypatch.setattr(botocore.session, "Session", lambda: _FakeSession())
    inspector = AwsInspector()  # no client_factory needed
    assert inspector.list_profiles() == ["default", "geekcafe-prod"]


# ---------------------------------------------------------------------------
# put_secret_value — exactly one call
# ---------------------------------------------------------------------------


def test_put_secret_value_one_call():
    sm = MagicMock()
    inspector = AwsInspector(client_factory=lambda s: {"secretsmanager": sm}[s])
    inspector.put_secret_value("some/secret", "xoxb-token")
    sm.put_secret_value.assert_called_once_with(
        SecretId="some/secret", SecretString="xoxb-token"
    )


# ---------------------------------------------------------------------------
# Friendly error mapping
# ---------------------------------------------------------------------------


def test_no_credentials_maps_to_sso_remediation():
    sts = MagicMock()
    sts.get_caller_identity.side_effect = NoCredentialsError()
    inspector = AwsInspector(
        client_factory=lambda s: {"sts": sts}[s], profile="geekcafe-prod"
    )
    with pytest.raises(AwsInspectorError) as exc:
        inspector.resolve_account()
    assert "aws sso login --profile geekcafe-prod" in (exc.value.remediation or "")
    assert exc.value.access_denied is False


def test_expired_token_maps_to_sso_remediation():
    sts = MagicMock()
    sts.get_caller_identity.side_effect = _client_error("ExpiredToken")
    inspector = AwsInspector(
        client_factory=lambda s: {"sts": sts}[s], profile="p"
    )
    with pytest.raises(AwsInspectorError) as exc:
        inspector.resolve_account()
    assert "aws sso login --profile p" in (exc.value.remediation or "")


def test_access_denied_sets_flag_on_list_connections():
    cc = MagicMock()
    cc.get_paginator.side_effect = _client_error("AccessDeniedException")
    inspector = AwsInspector(client_factory=lambda s: {"codeconnections": cc}[s])
    with pytest.raises(AwsInspectorError) as exc:
        inspector.list_connections()
    assert exc.value.access_denied is True


def test_access_denied_on_pipelines_sets_flag():
    cp = MagicMock()
    cp.get_paginator.side_effect = _client_error("AccessDenied")
    inspector = AwsInspector(client_factory=lambda s: {"codepipeline": cp}[s])
    with pytest.raises(AwsInspectorError) as exc:
        inspector.list_pipelines()
    assert exc.value.access_denied is True
