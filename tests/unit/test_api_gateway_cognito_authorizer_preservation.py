"""
Preservation Property Tests — Existing Config Key Formats Still Work

These tests capture baseline behavior that MUST be preserved after the fix.
They run on UNFIXED code first (observation-first methodology) and should
PASS both before and after the fix is applied.

**Validates: Requirements 3.2, 3.3**
"""

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty dicts to use as Cognito config values.
_cognito_value_st = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        ),
        min_size=1,
        max_size=20,
    ),
    values=st.one_of(
        st.text(min_size=1, max_size=50),
        st.booleans(),
        st.integers(min_value=0, max_value=1000),
    ),
    min_size=1,
    max_size=5,
)

# Config keys that are NOT "cognito" or "cognito_authorizer"
_safe_key_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=30,
).filter(lambda k: k not in ("cognito", "cognito_authorizer"))

_safe_value_st = st.one_of(
    st.text(min_size=0, max_size=50),
    st.booleans(),
    st.integers(min_value=0, max_value=1000),
    st.lists(st.text(min_size=1, max_size=20), max_size=3),
)

# Generate config dicts that contain NEITHER "cognito" nor "cognito_authorizer"
_no_cognito_config_st = st.dictionaries(
    keys=_safe_key_st,
    values=_safe_value_st,
    min_size=0,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


class TestCognitoAuthorizerKeyPreserved(unittest.TestCase):
    """
    **Validates: Requirements 3.2**

    Property 2: Preservation — cognito_authorizer Key Still Works

    For any config dict that uses the "cognito_authorizer" key with a non-empty
    dict value, ApiGatewayConfig.cognito_authorizer must return that dict value.
    """

    @given(cognito_value=_cognito_value_st)
    @settings(max_examples=100)
    def test_cognito_authorizer_key_returns_value(self, cognito_value):
        """Configs using "cognito_authorizer" key must return the dict value.

        **Validates: Requirements 3.2**
        """
        config = {"cognito_authorizer": cognito_value}
        api_config = ApiGatewayConfig(config)

        result = api_config.cognito_authorizer

        assert result == cognito_value, (
            f"Expected cognito_authorizer to return {cognito_value}, " f"got {result}"
        )


class TestNoCognitoConfigPreserved(unittest.TestCase):
    """
    **Validates: Requirements 3.3**

    Property 2: Preservation — No Cognito Config Returns None

    For any config dict that contains NEITHER "cognito" nor "cognito_authorizer"
    keys, ApiGatewayConfig.cognito_authorizer must return None.
    """

    @given(config=_no_cognito_config_st)
    @settings(max_examples=100)
    def test_no_cognito_keys_returns_none(self, config):
        """Configs with neither cognito key must return None.

        **Validates: Requirements 3.3**
        """
        api_config = ApiGatewayConfig(config)

        result = api_config.cognito_authorizer

        assert result is None, (
            f"Expected cognito_authorizer to return None for config "
            f"without cognito keys, got {result}. Config: {config}"
        )


# ---------------------------------------------------------------------------
# Example Tests — Other Properties Unaffected
# ---------------------------------------------------------------------------


class TestOtherPropertiesUnaffected(unittest.TestCase):
    """
    **Validates: Requirements 3.2, 3.3**

    Verify that other ApiGatewayConfig properties (name, description, deploy,
    routes) are unaffected and continue to work as expected.
    """

    def test_name_property(self):
        """name property returns the configured name.

        **Validates: Requirements 3.2**
        """
        config = {"name": "my-api-gateway"}
        api_config = ApiGatewayConfig(config)
        assert api_config.name == "my-api-gateway"

    def test_name_property_missing(self):
        """name property returns None when not configured.

        **Validates: Requirements 3.2**
        """
        config = {"description": "some api"}
        api_config = ApiGatewayConfig(config)
        assert api_config.name is None

    def test_description_property(self):
        """description property returns the configured description.

        **Validates: Requirements 3.2**
        """
        config = {"description": "My API Gateway"}
        api_config = ApiGatewayConfig(config)
        assert api_config.description == "My API Gateway"

    def test_deploy_property_default(self):
        """deploy property defaults to True when not configured.

        **Validates: Requirements 3.2**
        """
        config = {}
        api_config = ApiGatewayConfig(config)
        assert api_config.deploy is True

    def test_deploy_property_false(self):
        """deploy property returns False when configured.

        **Validates: Requirements 3.2**
        """
        config = {"deploy": False}
        api_config = ApiGatewayConfig(config)
        assert api_config.deploy is False

    def test_routes_property_default(self):
        """routes property defaults to empty list when not configured.

        **Validates: Requirements 3.2**
        """
        config = {}
        api_config = ApiGatewayConfig(config)
        assert api_config.routes == []

    def test_routes_property_with_routes(self):
        """routes property returns configured routes.

        **Validates: Requirements 3.2**
        """
        routes = [{"path": "/users", "method": "GET"}]
        config = {"routes": routes}
        api_config = ApiGatewayConfig(config)
        assert api_config.routes == routes

    def test_cognito_authorizer_with_cognito_authorizer_key(self):
        """cognito_authorizer returns the dict when using cognito_authorizer key.

        **Validates: Requirements 3.2**
        """
        config = {"cognito_authorizer": {"user_pool_ssm_path": "/auth/pool"}}
        api_config = ApiGatewayConfig(config)
        assert api_config.cognito_authorizer == {"user_pool_ssm_path": "/auth/pool"}

    def test_cognito_authorizer_returns_none_when_absent(self):
        """cognito_authorizer returns None when no cognito config present.

        **Validates: Requirements 3.3**
        """
        config = {"name": "my-api", "deploy": True, "routes": []}
        api_config = ApiGatewayConfig(config)
        assert api_config.cognito_authorizer is None

    def test_empty_config(self):
        """Empty config returns None for cognito_authorizer.

        **Validates: Requirements 3.3**
        """
        config = {}
        api_config = ApiGatewayConfig(config)
        assert api_config.cognito_authorizer is None
