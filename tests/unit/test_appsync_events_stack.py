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
    subscribe_modes = {
        m["AuthType"] for m in event_config["DefaultSubscribeAuthModes"]
    }
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

    cognito = next(
        p for p in providers if p["AuthType"] == "AMAZON_COGNITO_USER_POOLS"
    )
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
