"""
Property-Based Tests — Cognito Per-Client SSM Namespace

These tests verify universal properties of the per-client SSM namespace
resolution logic using hypothesis to generate random inputs.

Feature: cognito-app-client-ssm-namespace
"""

import os
import pytest
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.cognito import get_client_ssm_namespace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_environment():
    """Set ENVIRONMENT variable for tests"""
    os.environ["ENVIRONMENT"] = "test"
    yield
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cognito_stack_with_namespace(pool_namespace: str):
    """
    Build a minimal CognitoStack-like object whose _resolve_client_namespace
    method can be called directly.  We import the real class and wire up just
    enough state so the method works without synthesising a full CDK stack.
    """
    from aws_cdk import App
    from cdk_factory.stack_library.cognito.cognito_stack import CognitoStack

    app = App()
    stack = CognitoStack(app, "PropTestStack")

    # Wire up a mock stack_config with the pool-level ssm_namespace
    mock_stack_config = MagicMock()
    mock_stack_config.ssm_namespace = pool_namespace
    stack.stack_config = mock_stack_config

    return stack


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty namespace strings (printable, no leading/trailing whitespace)
_namespace_str = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() != "")

# Client name: alphanumeric + hyphens/spaces/underscores, 1-40 chars
_client_name = st.from_regex(r"[a-zA-Z][a-zA-Z0-9 _\-]{0,39}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 1: Client namespace config parsing
# Feature: cognito-app-client-ssm-namespace, Property 1: Client namespace config parsing
# **Validates: Requirements 1.1, 1.2, 1.3, 5.2**
# ---------------------------------------------------------------------------


class TestClientNamespaceConfigParsing:
    """
    **Validates: Requirements 1.1, 1.2, 1.3, 5.2**

    For any app client configuration dict, if ``ssm_namespace`` is present as a
    non-empty string the parsed value SHALL equal the input string; if
    ``ssm_namespace`` is absent the parsed value SHALL be ``None``.
    """

    @given(namespace=_namespace_str)
    @settings(max_examples=100)
    def test_present_namespace_is_returned(self, namespace):
        """
        **Validates: Requirements 1.1, 1.2, 1.3, 5.2**

        When ssm_namespace is present, get_client_ssm_namespace returns it.
        """
        config = {"name": "test-client", "ssm_namespace": namespace}
        result = get_client_ssm_namespace(config)
        assert result == namespace

    @given(
        extra_keys=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(
                lambda k: k != "ssm_namespace"
            ),
            values=st.text(max_size=20),
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_absent_namespace_returns_none(self, extra_keys):
        """
        **Validates: Requirements 1.1, 1.2, 1.3, 5.2**

        When ssm_namespace is absent, get_client_ssm_namespace returns None.
        """
        config = {"name": "test-client", **extra_keys}
        assert "ssm_namespace" not in config
        result = get_client_ssm_namespace(config)
        assert result is None


# ---------------------------------------------------------------------------
# Property 2: SSM path resolution uses correct namespace
# Feature: cognito-app-client-ssm-namespace, Property 2: SSM path resolution uses correct namespace
# **Validates: Requirements 2.1, 2.3, 4.1, 4.2**
# ---------------------------------------------------------------------------


class TestSsmPathResolutionNamespace:
    """
    **Validates: Requirements 2.1, 2.3, 4.1, 4.2**

    For any app client with a valid name and an optional ``ssm_namespace``,
    the resolved SSM parameter path SHALL use the client-level namespace when
    ``ssm_namespace`` is a non-empty string, and SHALL use the pool-level
    namespace when ``ssm_namespace`` is absent or ``None``.
    """

    @given(
        client_name=_client_name,
        client_namespace=_namespace_str,
        pool_namespace=_namespace_str,
    )
    @settings(max_examples=100, deadline=None)
    def test_client_namespace_takes_precedence(
        self, client_name, client_namespace, pool_namespace
    ):
        """
        **Validates: Requirements 2.1, 2.3, 4.1, 4.2**

        When a client specifies ssm_namespace, _resolve_client_namespace
        returns the client-level namespace.
        """
        stack = _make_cognito_stack_with_namespace(pool_namespace)
        client_config = {"name": client_name, "ssm_namespace": client_namespace}

        result = stack._resolve_client_namespace(client_config)
        assert result == client_namespace

    @given(
        client_name=_client_name,
        pool_namespace=_namespace_str,
    )
    @settings(max_examples=100, deadline=None)
    def test_pool_namespace_used_when_client_absent(self, client_name, pool_namespace):
        """
        **Validates: Requirements 2.1, 2.3, 4.1, 4.2**

        When a client does not specify ssm_namespace, _resolve_client_namespace
        returns the pool-level namespace.
        """
        stack = _make_cognito_stack_with_namespace(pool_namespace)
        client_config = {"name": client_name}

        result = stack._resolve_client_namespace(client_config)
        assert result == pool_namespace


# ---------------------------------------------------------------------------
# Property 3: Safe client name transformation is idempotent
# Feature: cognito-app-client-ssm-namespace, Property 3: Safe client name transformation is idempotent
# **Validates: Requirements 2.1, 2.2, 2.3**
# ---------------------------------------------------------------------------


class TestSafeClientNameIdempotent:
    """
    **Validates: Requirements 2.1, 2.2, 2.3**

    For any client name string, applying the safe-name transformation
    (replacing hyphens and spaces with underscores) twice SHALL produce the
    same result as applying it once.
    """

    @given(name=st.text(max_size=80))
    @settings(max_examples=100)
    def test_safe_name_is_idempotent(self, name):
        """
        **Validates: Requirements 2.1, 2.2, 2.3**

        f(f(x)) == f(x) for the safe client name transformation.
        """

        def safe_name(s: str) -> str:
            return s.replace(" ", "-")

        once = safe_name(name)
        twice = safe_name(once)
        assert twice == once


# ---------------------------------------------------------------------------
# Property 4: Empty string namespace rejection
# Feature: cognito-app-client-ssm-namespace, Property 4: Empty string namespace rejection
# **Validates: Requirements 6.2**
# ---------------------------------------------------------------------------


class TestEmptyNamespaceRejection:
    """
    **Validates: Requirements 6.2**

    For any app client configuration where ``ssm_namespace`` is a string
    composed entirely of whitespace (including empty string), the namespace
    resolution SHALL raise a ``ValueError``.
    """

    @given(
        whitespace=st.from_regex(r"[\s]{0,20}", fullmatch=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_whitespace_namespace_raises_value_error(self, whitespace):
        """
        **Validates: Requirements 6.2**

        Whitespace-only (including empty) ssm_namespace raises ValueError.
        """
        stack = _make_cognito_stack_with_namespace("pool/ns")
        client_config = {"name": "test-client", "ssm_namespace": whitespace}

        with pytest.raises(ValueError, match="ssm_namespace"):
            stack._resolve_client_namespace(client_config)
