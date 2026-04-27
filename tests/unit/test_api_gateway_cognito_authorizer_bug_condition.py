"""
Bug Condition Exploration Tests — API Gateway Cognito Authorizer Config Key Mismatch

These tests demonstrate that `ApiGatewayConfig.cognito_authorizer` returns `None`
when the config dict uses the `"cognito"` key (the actual convention in deployment
configs) instead of `"cognito_authorizer"` (the key the property reads from).

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2
"""

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty dicts to use as Cognito config values.
# Keys are simple strings, values are simple JSON-compatible types.
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


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestApiGatewayCognitoAuthorizerBugCondition(unittest.TestCase):
    """
    **Validates: Requirements 1.1, 1.2**

    Property 1: Bug Condition — Config Key Lookup Returns None for "cognito" Key

    When the API Gateway config contains a `"cognito"` key with a non-empty dict
    value (and does NOT contain `"cognito_authorizer"`), the `cognito_authorizer`
    property MUST return that dict value.

    On unfixed code, the property only reads `"cognito_authorizer"`, so configs
    using the `"cognito"` key return `None`. These tests WILL FAIL, confirming
    the bug exists.
    """

    def test_cognito_key_returns_config_dict(self):
        """Config with "cognito" key should return the dict, not None.

        **Validates: Requirements 1.1**
        """
        config = {"cognito": {"user_pool_ssm_path": "/path"}}
        api_config = ApiGatewayConfig(config)

        result = api_config.cognito_authorizer

        assert result is not None, (
            f"Bug confirmed: cognito_authorizer returns None when config uses "
            f"'cognito' key. Config: {config}, Result: {result}"
        )
        assert result == {"user_pool_ssm_path": "/path"}, (
            f"Expected cognito_authorizer to return the cognito dict value, "
            f"got: {result}"
        )

    def test_cognito_authorizer_key_takes_precedence(self):
        """When both keys are present, "cognito_authorizer" takes precedence.

        **Validates: Requirements 1.2**
        """
        config = {"cognito_authorizer": {"a": 1}, "cognito": {"b": 2}}
        api_config = ApiGatewayConfig(config)

        result = api_config.cognito_authorizer

        assert result == {"a": 1}, (
            f"Expected cognito_authorizer key to take precedence. "
            f"Expected: {{'a': 1}}, Got: {result}"
        )

    @given(cognito_value=_cognito_value_st)
    @settings(max_examples=100)
    def test_cognito_key_always_returns_value(self, cognito_value):
        """For any non-empty Cognito config dict under the "cognito" key
        (without "cognito_authorizer" present), cognito_authorizer must
        return the dict value.

        **Validates: Requirements 1.1, 1.2**
        """
        config = {"cognito": cognito_value}
        api_config = ApiGatewayConfig(config)

        result = api_config.cognito_authorizer

        assert result is not None, (
            f"Bug confirmed: cognito_authorizer returns None for config "
            f"with 'cognito' key. Config: {config}, Result: {result}"
        )
        assert result == cognito_value, (
            f"Expected cognito_authorizer to return the cognito dict value. "
            f"Expected: {cognito_value}, Got: {result}"
        )
