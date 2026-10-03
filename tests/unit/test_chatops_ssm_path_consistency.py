"""
Phase 9 (step 24): the HIGH-1 SSM path-consistency guard.

Three config strings must be byte-identical BEFORE synth:
  1. the SQS stack ssm.namespace-derived publish path,
  2. the consumer Lambda triggers[0].queue_ssm_path,
  3. the EventBridge rule target_queue_ssm_path.

And after synth, the AWS::SSM::Parameter Name that the SQS stack creates for the
queue ARN must be the exact literal that the consumer trigger and the rule
resolve. Drift between any of these fails HERE, not at deploy time.
"""

import json

from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack
from cdk_factory.workload.workload_factory import WorkloadConfig

from chatops_config_helpers import (
    EVENTBRIDGE_STACK_NAME,
    SQS_QUEUE_CONFIG_PATH,
    SQS_STACK_NAME,
    find_lambda,
    find_stack,
    load_chatops_config,
)

WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"


def _published_path(config) -> str:
    """Build the SQS stack publish path exactly as _publish_queue_to_ssm does."""
    sqs_cfg = find_stack(config, SQS_STACK_NAME)
    namespace = sqs_cfg["ssm"]["namespace"]
    queue_name = json.loads(SQS_QUEUE_CONFIG_PATH.read_text(encoding="utf-8"))["name"]
    queue_name = queue_name.replace("{{WORKLOAD_NAME}}", WORKLOAD).replace(
        "{{DEPLOYMENT_NAMESPACE}}", ENV
    )
    # prefix = /{namespace}; suffix = {queue_name}; path = {prefix}/{suffix}/arn
    return f"/{namespace}/{queue_name}/arn"


def _consumer_trigger_path(config) -> str:
    consumer = find_lambda(config, "chatops-slack-consumer")
    return consumer["triggers"][0]["queue_ssm_path"]


def _rule_target_path(config) -> str:
    eb_cfg = find_stack(config, EVENTBRIDGE_STACK_NAME)
    return eb_cfg["event_bridge_rules"][0]["target_queue_ssm_path"]


def test_three_paths_byte_identical_before_synth():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    publish = _published_path(config)
    trigger = _consumer_trigger_path(config)
    rule = _rule_target_path(config)

    assert publish == trigger == rule
    assert publish == f"/chatops/{ENV}/sqs/{WORKLOAD}-{ENV}-chatops-slack/arn"


def test_synthesized_ssm_parameter_name_matches_consume_paths():
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    expected = _published_path(config)

    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
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
    stack = SQSStack(app, "ChatOpsSqs", env={"account": ACCOUNT, "region": REGION})
    stack.build(
        stack_config=StackConfig(find_stack(config, SQS_STACK_NAME), wl.dictionary),
        deployment=deployment,
        workload=wl,
    )
    template = Template.from_stack(stack)

    params = template.find_resources("AWS::SSM::Parameter")
    names = [p["Properties"]["Name"] for p in params.values()]

    # The synthesized queue-ARN parameter name is the exact literal both the
    # consumer trigger and the rule resolve from.
    assert expected in names
    assert expected == _consumer_trigger_path(config)
    assert expected == _rule_target_path(config)
