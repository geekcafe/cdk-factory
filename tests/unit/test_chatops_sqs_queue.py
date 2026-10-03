"""
Phase 6 (steps 16-17) tests for the chatops Slack standalone queue + the SQS
stack entry that owns the SSM publish namespace.

Asserts:
  - the standalone queue JSON is schema-valid against sqs.schema.json and does
    NOT use the legacy inline sqs.queues pattern or a type:"consumer".
  - synthesizing the SQS stack with the chatops config publishes the queue ARN
    at exactly /chatops/{env}/sqs/{workload}-{env}-chatops-slack/arn.
"""

import json
from pathlib import Path

import jsonschema
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack
from cdk_factory.workload.workload_factory import WorkloadConfig

from chatops_config_helpers import (
    SQS_QUEUE_CONFIG_PATH,
    SQS_STACK_NAME,
    find_stack,
    load_chatops_config,
)

WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SQS_SCHEMA_PATH = REPO_ROOT / "src" / "cdk_factory" / "schemas" / "sqs.schema.json"


def _queue_json() -> dict:
    return json.loads(SQS_QUEUE_CONFIG_PATH.read_text(encoding="utf-8"))


def test_queue_json_is_schema_valid():
    schema = json.loads(SQS_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=_queue_json(), schema=schema)


def test_queue_omits_type_and_has_explicit_settings():
    queue = _queue_json()
    assert "type" not in queue  # omitted -> schema-valid "standard"
    assert queue["visibility_timeout_seconds"] == 120
    assert queue["message_retention_period_days"] == 4
    assert queue["delay_seconds"] == 0
    assert queue["dead_letter_queue"]["max_receive_count"] == 3
    assert queue["dead_letter_queue"]["message_retention_period_days"] == 14
    assert "ssm_parameters" not in queue  # dead field removed


def test_no_legacy_inline_queues_in_sqs_configs():
    sqs_dir = REPO_ROOT / "configs" / "stacks" / "sqs"
    for f in sqs_dir.glob("*.json"):
        assert '"queues"' not in f.read_text(encoding="utf-8")


def _build_sqs_template() -> Template:
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    sqs_cfg = find_stack(config, SQS_STACK_NAME)

    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    stack_config = StackConfig(sqs_cfg, workload=wl.dictionary)
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
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def test_queue_arn_published_at_expected_ssm_path():
    template = _build_sqs_template()
    params = template.find_resources("AWS::SSM::Parameter")
    names = [p["Properties"]["Name"] for p in params.values()]
    expected = f"/chatops/{ENV}/sqs/{WORKLOAD}-{ENV}-chatops-slack/arn"
    assert expected in names


def test_queue_and_dlq_created():
    template = _build_sqs_template()
    # main queue + DLQ
    template.resource_count_is("AWS::SQS::Queue", 2)
