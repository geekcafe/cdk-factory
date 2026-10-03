"""
Phase 7 (steps 18-19) tests for the chatops Lambda configs.

The full lambda_stack synth requires real code bundles + API Gateway wiring, so
these tests exercise the exact production code paths that translate the config
into AWS wiring without bundling assets:

  - LambdaFunctionConfig parses handler / timeout / triggers / permissions / api.
  - policy_docs.get_permission_details() (the same call the role construct makes)
    turns the inline IAM permission dicts into IAM actions/resources.
  - no inline sqs.queues anywhere in the chatops configs (decoupled pattern).
"""

import json

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments
from cdk_factory.workload.workload_factory import WorkloadConfig
from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from chatops_config_helpers import (
    LAMBDA_STACK_NAME,
    find_lambda,
    find_stack,
    load_chatops_config,
)

WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"


def _deployment() -> DeploymentConfig:
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    return DeploymentConfig(
        workload=wl.dictionary,
        deployment={
            "name": ENV,
            "environment": ENV,
            "account": ACCOUNT,
            "region": REGION,
        },
    )


def _permission_statements(lambda_cfg: LambdaFunctionConfig):
    """Resolve each config permission through the production policy_docs path."""
    app = App()
    stack = Stack(app, "PolicyProbe", env={"account": ACCOUNT, "region": REGION})
    role = iam.Role(
        stack, "ProbeRole", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
    )
    docs = PolicyDocuments(
        scope=stack,
        role=role,
        deployment=_deployment(),
        lambda_config=lambda_cfg,
    )
    statements = []
    for permission in lambda_cfg.permissions:
        details = docs.get_permission_details(permission)
        statements.append(details)
    return statements


# ── Consumer Lambda ──────────────────────────────────────────────────────────


def test_consumer_handler_and_timeout_and_no_inline_queues():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    consumer = find_lambda(config, "chatops-slack-consumer")
    assert (
        consumer["handler"]
        == "geek_cafe_saas_sdk.modules.notifications.handlers.slack_consumer.app.lambda_handler"
    )
    assert consumer["timeout"] == 20
    assert "sqs" not in consumer  # no legacy inline sqs.queues


def test_consumer_sqs_trigger_uses_ssm_path():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    consumer = find_lambda(config, "chatops-slack-consumer")
    cfg = LambdaFunctionConfig(config=consumer, deployment=_deployment())
    assert len(cfg.triggers) == 1
    trig = cfg.triggers[0]
    assert trig.resource_type == "sqs"
    assert (
        trig.queue_ssm_path == f"/chatops/{ENV}/sqs/{WORKLOAD}-{ENV}-chatops-slack/arn"
    )
    assert trig.batch_size == 1
    assert trig.max_batching_window_seconds == 0


def test_consumer_permissions_ssm_and_secrets():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    consumer = find_lambda(config, "chatops-slack-consumer")
    cfg = LambdaFunctionConfig(config=consumer, deployment=_deployment())
    statements = _permission_statements(cfg)

    all_actions = {a for s in statements for a in s.get("actions", [])}
    all_resources = [r for s in statements for r in s.get("resources", [])]

    assert "ssm:GetParameter" in all_actions
    assert "ssm:GetParametersByPath" in all_actions
    assert "secretsmanager:GetSecretValue" in all_actions
    # SQS consume permissions are auto-granted by __setup_sqs_trigger — NOT here.
    assert not any(a.startswith("sqs:") for a in all_actions)

    joined = " ".join(all_resources)
    assert "chatops/slack/targets/*" in joined
    assert "secret:chatops/slack/*" in joined


# ── Ingress Lambda ───────────────────────────────────────────────────────────


def test_ingress_handler_and_api():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    ingress = find_lambda(config, "chatops-ingress")
    assert (
        ingress["handler"]
        == "geek_cafe_saas_sdk.modules.notifications.handlers.chatops_ingress.app.lambda_handler"
    )
    assert ingress["api"]["route"] == "/notifications/chatops"
    assert ingress["api"]["method"] == "POST"
    assert ingress["api"]["authorization_type"] == "NONE"
    assert "sqs" not in ingress  # no legacy inline sqs.queues


def test_ingress_permissions_putevents_and_secret_only():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    ingress = find_lambda(config, "chatops-ingress")
    cfg = LambdaFunctionConfig(config=ingress, deployment=_deployment())
    statements = _permission_statements(cfg)

    all_actions = {a for s in statements for a in s.get("actions", [])}
    all_resources = [r for s in statements for r in s.get("resources", [])]

    assert "events:PutEvents" in all_actions
    assert "secretsmanager:GetSecretValue" in all_actions
    # No Slack / synchronous / SQS permissions on the ingress.
    assert not any(a.startswith("sqs:") for a in all_actions)

    joined = " ".join(all_resources)
    assert f"event-bus/default" in joined
    assert "secret:chatops/ingress/shared-secret*" in joined


def test_no_inline_queues_in_chatops_configs():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    assert '"queues"' not in json.dumps(config)
