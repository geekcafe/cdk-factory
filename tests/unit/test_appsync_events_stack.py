"""
Credential-free synth tests for the appsync_events stack (FEAT-001).

Mirrors test_eventbridge_rule_sqs_stack.py via aws_cdk.assertions.Template.
Asserts:
  - exactly one AWS::AppSync::Api
  - EventConfig.AuthProviders include AMAZON_COGNITO_USER_POOLS + AWS_LAMBDA
    (+ API_KEY), and connection/subscribe auth modes are AWS_LAMBDA
  - one AWS::AppSync::ChannelNamespace per configured namespace
  - three AWS::SSM::Parameter exports (api-id / http-endpoint / realtime-endpoint)
  - user-pool id and authorizer ARN appear as Refs to
    AWS::SSM::Parameter::Value<String> CfnParameters (deploy-time tokens)
  - the stack source contains no builtin hash(
  - ValueError on missing-SSM-path and duplicate-namespace configs
"""

import re
from pathlib import Path

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.appsync_events.appsync_events_stack import (
    AppSyncEventsStack,
)
from cdk_factory.workload.workload_factory import WorkloadConfig

from realtime_config_helpers import (
    APPSYNC_EVENTS_STACK_NAME,
    find_stack,
    load_realtime_config,
)


WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"


def _build_template(stack_cfg: dict) -> Template:
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    stack_config = StackConfig(stack_cfg, workload=wl.dictionary)
    deployment = DeploymentConfig(
        workload=wl.dictionary,
        deployment={
            "name": ENV,
            "environment": ENV,
            "account": ACCOUNT,
            "region": REGION,
        },
    )

    app = App()
    stack = AppSyncEventsStack(
        app, "RealtimeAppSyncEvents", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def _build_sample_template() -> Template:
    config = load_realtime_config(WORKLOAD, ENV, ACCOUNT, REGION)
    stack_cfg = find_stack(config, APPSYNC_EVENTS_STACK_NAME)
    return _build_template(stack_cfg)


def _sample_stack_cfg() -> dict:
    config = load_realtime_config(WORKLOAD, ENV, ACCOUNT, REGION)
    return find_stack(config, APPSYNC_EVENTS_STACK_NAME)


def test_one_appsync_api_created():
    template = _build_sample_template()
    template.resource_count_is("AWS::AppSync::Api", 1)


def test_event_config_auth_providers_and_modes():
    template = _build_sample_template()
    apis = template.find_resources("AWS::AppSync::Api")
    api = list(apis.values())[0]
    event_config = api["Properties"]["EventConfig"]

    provider_types = {p["AuthType"] for p in event_config["AuthProviders"]}
    assert "AMAZON_COGNITO_USER_POOLS" in provider_types
    assert "AWS_LAMBDA" in provider_types
    assert "API_KEY" in provider_types

    connection_modes = {m["AuthType"] for m in event_config["ConnectionAuthModes"]}
    subscribe_modes = {m["AuthType"] for m in event_config["DefaultSubscribeAuthModes"]}
    assert connection_modes == {"AWS_LAMBDA"}
    assert subscribe_modes == {"AWS_LAMBDA"}


def test_channel_namespace_count_matches_config():
    stack_cfg = _sample_stack_cfg()
    expected = len(stack_cfg["appsync_events"]["channel_namespaces"])
    template = _build_template(stack_cfg)
    template.resource_count_is("AWS::AppSync::ChannelNamespace", expected)


def test_three_ssm_exports_with_expected_names():
    template = _build_sample_template()
    template.resource_count_is("AWS::SSM::Parameter", 3)
    params = template.find_resources("AWS::SSM::Parameter")
    names = {p["Properties"]["Name"] for p in params.values()}
    prefix = f"/{WORKLOAD}/{ENV}/appsync-events/realtime"
    assert names == {
        f"{prefix}/api-id",
        f"{prefix}/http-endpoint",
        f"{prefix}/realtime-endpoint",
    }


def test_cross_stack_ids_are_ssm_tokens_not_literals():
    template = _build_sample_template()
    apis = template.find_resources("AWS::AppSync::Api")
    api = list(apis.values())[0]
    providers = api["Properties"]["EventConfig"]["AuthProviders"]

    cognito = next(p for p in providers if p["AuthType"] == "AMAZON_COGNITO_USER_POOLS")
    user_pool_id = cognito["CognitoConfig"]["UserPoolId"]
    assert isinstance(user_pool_id, dict) and "Ref" in user_pool_id

    lambda_provider = next(p for p in providers if p["AuthType"] == "AWS_LAMBDA")
    authorizer_uri = lambda_provider["LambdaAuthorizerConfig"]["AuthorizerUri"]
    assert isinstance(authorizer_uri, dict) and "Ref" in authorizer_uri

    # Both Refs point at AWS::SSM::Parameter::Value<String> CfnParameters.
    cfn_params = template.find_parameters("*")
    for ref in (user_pool_id["Ref"], authorizer_uri["Ref"]):
        assert ref in cfn_params
        assert cfn_params[ref]["Type"] == "AWS::SSM::Parameter::Value<String>"


def test_no_builtin_hash_in_appsync_events_stack_source():
    stack_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cdk_factory"
        / "stack_library"
        / "appsync_events"
    )
    for py in stack_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not re.search(r"\bhash\(", text), f"builtin hash( found in {py}"


def test_missing_user_pool_id_ssm_path_raises():
    stack_cfg = {
        "name": APPSYNC_EVENTS_STACK_NAME,
        "module": "appsync_events_stack",
        "appsync_events": {
            "name": "realtime",
            "authorizer_lambda_arn_ssm_path": "/x/y/authorizer/arn",
            "channel_namespaces": ["notifications"],
        },
    }
    with pytest.raises(ValueError, match="user_pool_id_ssm_path"):
        _build_template(stack_cfg)


def test_missing_authorizer_arn_ssm_path_raises():
    stack_cfg = {
        "name": APPSYNC_EVENTS_STACK_NAME,
        "module": "appsync_events_stack",
        "appsync_events": {
            "name": "realtime",
            "user_pool_id_ssm_path": "/x/y/user-pool/id",
            "channel_namespaces": ["notifications"],
        },
    }
    with pytest.raises(ValueError, match="authorizer_lambda_arn_ssm_path"):
        _build_template(stack_cfg)


def test_duplicate_namespace_names_raises():
    stack_cfg = {
        "name": APPSYNC_EVENTS_STACK_NAME,
        "module": "appsync_events_stack",
        "appsync_events": {
            "name": "realtime",
            "user_pool_id_ssm_path": "/x/y/user-pool/id",
            "authorizer_lambda_arn_ssm_path": "/x/y/authorizer/arn",
            "channel_namespaces": ["notifications", "notifications"],
        },
    }
    with pytest.raises(ValueError, match="Duplicate channel namespace"):
        _build_template(stack_cfg)


def _ns_stack_cfg(namespace_name: str) -> dict:
    return {
        "name": APPSYNC_EVENTS_STACK_NAME,
        "module": "appsync_events_stack",
        "appsync_events": {
            "name": "realtime",
            "user_pool_id_ssm_path": "/x/y/user-pool/id",
            "authorizer_lambda_arn_ssm_path": "/x/y/authorizer/arn",
            "channel_namespaces": [namespace_name],
        },
    }


def test_underscore_namespace_name_raises():
    # The real-world failure: "event_bus" passes a naive check but AppSync rejects
    # the underscore at CREATE time. Must fail fast at synth instead.
    with pytest.raises(ValueError, match="Invalid channel namespace name 'event_bus'"):
        _build_template(_ns_stack_cfg("event_bus"))


@pytest.mark.parametrize(
    "bad_name",
    [
        "event_bus",  # underscore (the motivating case)
        "-channels",  # leading hyphen
        "channels-",  # trailing hyphen
        "chan nels",  # space
        "channels!",  # punctuation
        "",  # empty
        "a" * 51,  # too long (>50)
    ],
)
def test_invalid_namespace_names_raise(bad_name):
    with pytest.raises(ValueError, match="Invalid channel namespace name"):
        _build_template(_ns_stack_cfg(bad_name))


@pytest.mark.parametrize(
    "good_name",
    [
        "channels",  # the chosen event-platform namespace
        "inboxes",  # the ChatOps namespace
        "a",  # single alphanumeric
        "my-channel-1",  # internal hyphens + digit end
        "a" * 50,  # max length
    ],
)
def test_valid_namespace_names_accepted(good_name):
    # Should synth without raising and produce exactly one ChannelNamespace.
    template = _build_template(_ns_stack_cfg(good_name))
    template.resource_count_is("AWS::AppSync::ChannelNamespace", 1)


def _auth_stack_cfg(auth: dict, api_key_publish: bool = True) -> dict:
    """Build a minimal appsync_events stack cfg carrying an `auth` block."""
    appsync_events = {
        "name": "realtime",
        "user_pool_id_ssm_path": "/x/y/user-pool/id",
        "authorizer_lambda_arn_ssm_path": "/x/y/authorizer/arn",
        "authorizer_result_ttl_seconds": 300,
        "api_key_publish": api_key_publish,
        "channel_namespaces": ["inboxes"],
    }
    if auth is not None:
        appsync_events["auth"] = auth
    return {
        "name": APPSYNC_EVENTS_STACK_NAME,
        "module": "appsync_events_stack",
        "appsync_events": appsync_events,
    }


def test_auth_block_drops_cognito_provider_and_sets_modes():
    # (b) providers ['lambda','api_key'] + all three mode lists.
    stack_cfg = _auth_stack_cfg(
        {
            "providers": ["lambda", "api_key"],
            "connection_auth_modes": ["lambda"],
            "subscribe_auth_modes": ["lambda"],
            "publish_auth_modes": ["api_key"],
        }
    )
    template = _build_template(stack_cfg)
    apis = template.find_resources("AWS::AppSync::Api")
    api = list(apis.values())[0]
    event_config = api["Properties"]["EventConfig"]

    provider_types = {p["AuthType"] for p in event_config["AuthProviders"]}
    assert provider_types == {"AWS_LAMBDA", "API_KEY"}
    assert "AMAZON_COGNITO_USER_POOLS" not in provider_types

    connection_modes = {m["AuthType"] for m in event_config["ConnectionAuthModes"]}
    subscribe_modes = {m["AuthType"] for m in event_config["DefaultSubscribeAuthModes"]}
    publish_modes = {m["AuthType"] for m in event_config["DefaultPublishAuthModes"]}
    assert connection_modes == {"AWS_LAMBDA"}
    assert subscribe_modes == {"AWS_LAMBDA"}
    assert publish_modes == {"API_KEY"}

    # The AWS_LAMBDA provider still carries a LambdaAuthorizerConfig.AuthorizerUri Ref.
    lambda_provider = next(
        p for p in event_config["AuthProviders"] if p["AuthType"] == "AWS_LAMBDA"
    )
    authorizer_uri = lambda_provider["LambdaAuthorizerConfig"]["AuthorizerUri"]
    assert isinstance(authorizer_uri, dict) and "Ref" in authorizer_uri


def test_unknown_auth_token_raises():
    # (c) an unmapped friendly token fails synth.
    stack_cfg = _auth_stack_cfg({"providers": ["bogus"]})
    with pytest.raises(ValueError, match="bogus"):
        _build_template(stack_cfg)


def test_legacy_no_api_key_publish_defaults_publish_to_lambda():
    # (d) legacy api_key_publish:false + no auth => publish AWS_LAMBDA, no API_KEY.
    stack_cfg = _auth_stack_cfg(None, api_key_publish=False)
    template = _build_template(stack_cfg)
    apis = template.find_resources("AWS::AppSync::Api")
    api = list(apis.values())[0]
    event_config = api["Properties"]["EventConfig"]

    provider_types = {p["AuthType"] for p in event_config["AuthProviders"]}
    assert "API_KEY" not in provider_types
    assert provider_types == {"AMAZON_COGNITO_USER_POOLS", "AWS_LAMBDA"}

    publish_modes = {m["AuthType"] for m in event_config["DefaultPublishAuthModes"]}
    assert publish_modes == {"AWS_LAMBDA"}


def _single_lambda_permission(template: Template) -> dict:
    """Return the single AWS::Lambda::Permission properties, asserting exactly one."""
    template.resource_count_is("AWS::Lambda::Permission", 1)
    perms = template.find_resources("AWS::Lambda::Permission")
    return list(perms.values())[0]["Properties"]


def test_lambda_invoke_permission_granted_in_legacy_path():
    # Legacy fallback (no `auth` block) always includes AWS_LAMBDA, so the
    # authorizer-invoke permission must be granted.
    template = _build_sample_template()
    props = _single_lambda_permission(template)

    assert props["Action"] == "lambda:InvokeFunction"
    assert props["Principal"] == "appsync.amazonaws.com"

    # FunctionName is a Ref to the authorizer SSM CfnParameter (deploy-time token).
    function_name = props["FunctionName"]
    assert isinstance(function_name, dict) and "Ref" in function_name
    cfn_params = template.find_parameters("*")
    assert function_name["Ref"] in cfn_params
    assert (
        cfn_params[function_name["Ref"]]["Type"] == "AWS::SSM::Parameter::Value<String>"
    )

    # SourceArn must be the BARE API ARN (a GetAtt on the CfnApi's ApiArn), NOT
    # scoped with a trailing /*. AppSync Events invokes the authorizer with a
    # SourceArn equal to the bare API ARN; a /*-scoped policy would not match and
    # the authorizer would never be invoked (400 BadRequestException).
    source_arn = props["SourceArn"]
    # Bare GetAtt token — no Fn::Join wrapping, no "/*" suffix.
    assert isinstance(source_arn, dict)
    assert "Fn::Join" not in source_arn
    assert source_arn.get("Fn::GetAtt", [None, None])[1] == "ApiArn"


def test_lambda_invoke_permission_granted_with_lambda_provider():
    # Config-driven providers including "lambda" => permission granted.
    stack_cfg = _auth_stack_cfg(
        {
            "providers": ["lambda", "api_key"],
            "connection_auth_modes": ["lambda"],
            "subscribe_auth_modes": ["lambda"],
            "publish_auth_modes": ["api_key"],
        }
    )
    template = _build_template(stack_cfg)
    props = _single_lambda_permission(template)

    assert props["Action"] == "lambda:InvokeFunction"
    assert props["Principal"] == "appsync.amazonaws.com"


def test_no_lambda_invoke_permission_when_no_lambda_provider():
    # providers omit "lambda" => no AuthorizerUri wired => no invoke permission.
    stack_cfg = _auth_stack_cfg(
        {
            "providers": ["api_key"],
            "connection_auth_modes": ["api_key"],
            "subscribe_auth_modes": ["api_key"],
            "publish_auth_modes": ["api_key"],
        }
    )
    template = _build_template(stack_cfg)
    template.resource_count_is("AWS::Lambda::Permission", 0)
