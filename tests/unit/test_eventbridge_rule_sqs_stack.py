"""
Synth tests for the net-new eventbridge_stack (EventBridge rule -> SQS target).

Asserts (step 21):
  - one AWS::Events::Rule with the chatops event pattern
  - an SQS target on the rule
  - an AWS::SQS::QueuePolicy granting sqs:SendMessage to events.amazonaws.com
    scoped to the rule ARN
  - no builtin hash() in the stack source (NFR-2b)

And (step 22) the end-to-end config check that the rule's target_queue_ssm_path
matches the queue's published SSM path.
"""

import json
import re
from pathlib import Path

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.event_bridge.eventbridge_stack import EventBridgeStack
from cdk_factory.workload.workload_factory import WorkloadConfig

from chatops_config_helpers import (
    EVENTBRIDGE_STACK_NAME,
    SQS_STACK_NAME,
    find_stack,
    load_chatops_config,
)


WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"


def _build_eventbridge_template() -> Template:
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    eb_stack_cfg = find_stack(config, EVENTBRIDGE_STACK_NAME)

    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    stack_config = StackConfig(eb_stack_cfg, workload=wl.dictionary)
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
    stack = EventBridgeStack(
        app, "ChatOpsEventBridge", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def test_rule_has_expected_event_pattern():
    template = _build_eventbridge_template()
    template.resource_count_is("AWS::Events::Rule", 1)
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": {
                "source": ["geekcafe.chatops"],
                "detail-type": ["ChatOpsMessage"],
                "detail": {"platform": ["slack"]},
            },
            "Name": f"{WORKLOAD}-{ENV}-chatops-slack-rule",
        },
    )


def test_rule_has_sqs_target():
    template = _build_eventbridge_template()
    rules = template.find_resources("AWS::Events::Rule")
    rule = list(rules.values())[0]
    targets = rule["Properties"]["Targets"]
    assert len(targets) == 1
    # Target Arn is a CDK token resolving the queue ARN from SSM at deploy time
    # (an AWS::SSM::Parameter::Value<String> CfnParameter Ref), NOT a literal ARN.
    arn = targets[0]["Arn"]
    assert isinstance(arn, dict) and "Ref" in arn
    assert "SsmParameterValue" in arn["Ref"]
    assert "chatops" in arn["Ref"]


def test_sqs_queue_policy_grants_events_scoped_to_rule():
    template = _build_eventbridge_template()
    template.resource_count_is("AWS::SQS::QueuePolicy", 1)
    policies = template.find_resources("AWS::SQS::QueuePolicy")
    policy = list(policies.values())[0]
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Action"] == "sqs:SendMessage"
    assert stmt["Principal"] == {"Service": "events.amazonaws.com"}
    assert "ArnEquals" in stmt["Condition"]
    assert "aws:SourceArn" in stmt["Condition"]["ArnEquals"]


def test_no_builtin_hash_in_eventbridge_stack_source():
    stack_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cdk_factory"
        / "stack_library"
        / "event_bridge"
    )
    for py in stack_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not re.search(r"\bhash\(", text), f"builtin hash( found in {py}"


def test_rule_target_ssm_path_matches_published_queue_path():
    """End-to-end: the rule target SSM path equals the SQS stack publish path."""
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)

    # Rule target path (resolved placeholders).
    eb_cfg = find_stack(config, EVENTBRIDGE_STACK_NAME)
    rule = eb_cfg["event_bridge_rules"][0]
    rule_target_path = rule["target_queue_ssm_path"]

    # SQS stack publish path = /{namespace}/sqs/{queue-name}/arn, where the
    # queue name is the standalone queue file name (template-resolved).
    sqs_cfg = find_stack(config, SQS_STACK_NAME)
    namespace = sqs_cfg["ssm"]["namespace"]
    queue_file = (
        Path(__file__).resolve().parents[2]
        / "configs"
        / "stacks"
        / "sqs"
        / "chatops-slack-queue.json"
    )
    queue_name = json.loads(queue_file.read_text(encoding="utf-8"))["name"]
    queue_name = queue_name.replace("{{WORKLOAD_NAME}}", WORKLOAD).replace(
        "{{DEPLOYMENT_NAMESPACE}}", ENV
    )
    # _publish_queue_to_ssm builds "/{namespace}/{queue_name}/arn"; the namespace
    # already ends in "/sqs", so the published path is:
    published_path = f"/{namespace}/{queue_name}/arn"

    assert rule_target_path == published_path
