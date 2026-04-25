"""
Bug Condition Exploration Tests — Custom Domain Config Silently Ignored

These tests demonstrate that ApiGatewayConfig does not expose a `custom_domain`
property, so any config dict with a `custom_domain` block is silently ignored.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty domain-like strings
domain_name_st = st.from_regex(r"[a-z][a-z0-9\-]{1,20}\.[a-z]{2,6}", fullmatch=True)
hosted_zone_id_st = st.from_regex(r"Z[A-Z0-9]{5,20}", fullmatch=True)
hosted_zone_name_st = st.from_regex(
    r"[a-z][a-z0-9\-]{1,15}\.[a-z]{2,6}", fullmatch=True
)
certificate_arn_st = st.from_regex(
    r"arn:aws:acm:us-east-1:[0-9]{12}:certificate/[a-f0-9\-]{8}", fullmatch=True
)


@st.composite
def custom_domain_dicts(draw):
    """Generate custom_domain config dicts with required and optional fields."""
    d = {
        "domain_name": draw(domain_name_st),
        "hosted_zone_id": draw(hosted_zone_id_st),
        "hosted_zone_name": draw(hosted_zone_name_st),
    }
    # certificate_arn is optional
    include_cert = draw(st.booleans())
    if include_cert:
        d["certificate_arn"] = draw(certificate_arn_st)
    return d


# ---------------------------------------------------------------------------
# Property-based test — Bug Condition
# ---------------------------------------------------------------------------


class TestBugConditionCustomDomainIgnored:
    """
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

    Property 1: Bug Condition — Custom Domain Config Silently Ignored

    For any config dict containing a `custom_domain` block with `domain_name`,
    `hosted_zone_id`, `hosted_zone_name`, and optionally `certificate_arn`,
    `ApiGatewayConfig.custom_domain` should return the correct values.

    On UNFIXED code this will fail because `ApiGatewayConfig` has no
    `custom_domain` property.
    """

    @given(cd=custom_domain_dicts())
    @settings(max_examples=50)
    def test_bug_condition_property_custom_domain_fields(self, cd):
        """Property test: custom_domain property returns generated values."""
        config = ApiGatewayConfig({"custom_domain": cd})

        result = config.custom_domain

        assert result.get("domain_name") == cd["domain_name"]
        assert result.get("hosted_zone_id") == cd["hosted_zone_id"]
        assert result.get("hosted_zone_name") == cd["hosted_zone_name"]
        assert result.get("certificate_arn") == cd.get("certificate_arn")

    def test_bug_condition_concrete_example(self):
        """Concrete example: custom_domain with all fields returns correct dict."""
        input_cd = {
            "domain_name": "api.beta.acme.com",
            "hosted_zone_id": "Z123",
            "hosted_zone_name": "beta.acme.com",
            "certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/abc",
        }
        config = ApiGatewayConfig({"custom_domain": input_cd})

        result = config.custom_domain

        assert result.get("domain_name") == "api.beta.acme.com"
        assert result.get("hosted_zone_id") == "Z123"
        assert result.get("hosted_zone_name") == "beta.acme.com"
        assert result.get("certificate_arn") == (
            "arn:aws:acm:us-east-1:123456789012:certificate/abc"
        )


# ---------------------------------------------------------------------------
# Strategies — Preservation (configs WITHOUT custom_domain)
# ---------------------------------------------------------------------------

# Simple text strategies for config values
_name_st = st.one_of(st.none(), st.text(min_size=1, max_size=30))
_description_st = st.one_of(st.none(), st.text(min_size=1, max_size=60))
_deploy_st = st.booleans()
_ssl_cert_arn_st = st.one_of(
    st.none(),
    st.from_regex(
        r"arn:aws:acm:us-east-1:[0-9]{12}:certificate/[a-f0-9]{8}", fullmatch=True
    ),
)
_routes_st = st.lists(
    st.fixed_dictionaries(
        {
            "path": st.text(min_size=1, max_size=15),
            "method": st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
        }
    ),
    max_size=5,
)
_deploy_options_st = st.one_of(
    st.just({}),
    st.fixed_dictionaries({"stage_name": st.text(min_size=1, max_size=10)}),
)
_hosted_zone_st = st.one_of(
    st.just({}),
    st.fixed_dictionaries(
        {
            "record_name": st.from_regex(r"[a-z]{2,10}\.[a-z]{2,6}", fullmatch=True),
            "id": st.from_regex(r"Z[A-Z0-9]{5,10}", fullmatch=True),
            "name": st.from_regex(r"[a-z]{2,10}\.[a-z]{2,6}", fullmatch=True),
        }
    ),
)


@st.composite
def non_custom_domain_configs(draw):
    """Generate API Gateway config dicts WITHOUT a `custom_domain` key."""
    config = {}

    # Optionally include each field
    if draw(st.booleans()):
        config["name"] = draw(_name_st)
    if draw(st.booleans()):
        config["description"] = draw(_description_st)
    if draw(st.booleans()):
        config["deploy"] = draw(_deploy_st)
    if draw(st.booleans()):
        config["deploy_options"] = draw(_deploy_options_st)
    if draw(st.booleans()):
        config["hosted_zone"] = draw(_hosted_zone_st)
    if draw(st.booleans()):
        config["ssl_cert_arn"] = draw(_ssl_cert_arn_st)
    if draw(st.booleans()):
        config["routes"] = draw(_routes_st)

    # NEVER include custom_domain — that's the whole point
    config.pop("custom_domain", None)
    return config


# ---------------------------------------------------------------------------
# Preservation Tests — Property 2
# ---------------------------------------------------------------------------


class TestPreservationNonCustomDomainBehavior:
    """
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

    Property 2: Preservation — Non-Custom-Domain Config Behavior Unchanged

    For any config dict that does NOT contain a `custom_domain` key, all
    existing properties must return the expected values. These tests capture
    baseline behavior on UNFIXED code so we can detect regressions after the fix.
    """

    # -------------------------------------------------------------------
    # Concrete preservation tests
    # -------------------------------------------------------------------

    def test_preservation_empty_config_defaults(self):
        """Empty config returns correct defaults for all properties."""
        config = ApiGatewayConfig({})

        assert config.name is None
        assert config.hosted_zone == {}
        assert config.ssl_cert_arn is None
        assert config.deploy is True
        assert config.routes == []
        assert config.description is None
        assert config.deploy_options == {}

    def test_preservation_hosted_zone_old_format(self):
        """Config with `hosted_zone` key (old format) returns the dict correctly."""
        hz = {"record_name": "api.example.com", "id": "Z123ABC", "name": "example.com"}
        config = ApiGatewayConfig({"hosted_zone": hz})

        assert config.hosted_zone == hz
        assert config.hosted_zone.get("record_name") == "api.example.com"
        assert config.hosted_zone.get("id") == "Z123ABC"
        assert config.hosted_zone.get("name") == "example.com"

    def test_preservation_ssl_cert_arn_top_level(self):
        """Config with top-level `ssl_cert_arn` returns the value correctly."""
        arn = "arn:aws:acm:us-east-1:123456789012:certificate/abcd-1234"
        config = ApiGatewayConfig({"ssl_cert_arn": arn})

        assert config.ssl_cert_arn == arn

    # -------------------------------------------------------------------
    # Property-based preservation test
    # -------------------------------------------------------------------

    @given(cfg=non_custom_domain_configs())
    @settings(max_examples=50)
    def test_preservation_property_all_fields(self, cfg):
        """
        Property test: for any config WITHOUT `custom_domain`, all properties
        return the expected values from the input dict (or defaults if absent).
        """
        config = ApiGatewayConfig(cfg)

        assert config.name == cfg.get("name")
        assert config.description == cfg.get("description")
        assert config.deploy_options == cfg.get("deploy_options", {})
        assert config.hosted_zone == cfg.get("hosted_zone", {})
        assert config.ssl_cert_arn == cfg.get("ssl_cert_arn")
        assert config.deploy == cfg.get("deploy", True)
        assert config.routes == cfg.get("routes", [])
