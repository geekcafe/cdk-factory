"""
Phase 9 (step 23): credential-free cdk synth smoke over the chatops stacks.

Synthesizes the SQS stack and the net-new EventBridge rule->SQS stack from the
chatops sample workload config and asserts:

  - synth succeeds with NO AWS credentials (NFR-2a). The test harness is expected
    to be run with blank AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (see the
    verification doc); we also assert here that no context-lookup markers are
    emitted, which is what would otherwise force a live AWS call.
  - no value_from_lookup / cdk.context.json lookups are emitted for the chatops
    resources (all cross-stack ARNs resolve via deploy-time SSM tokens).

The ingress/consumer Lambda functions are intentionally NOT synthesized here —
they require real code bundles + API Gateway wiring. Their config-driven wiring
is covered by test_chatops_lambda_config.py.
"""

import json

from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.event_bridge.eventbridge_stack import EventBridgeStack
from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack
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


def _deployment(wl: WorkloadConfig) -> DeploymentConfig:
    return DeploymentConfig(
        workload=wl.dictionary,
        deployment={
            "name": ENV,
            "environment": ENV,
            "account": ACCOUNT,
            "region": REGION,
        },
    )


def _build_chatops_stacks(app: App):
    """Build (not synth) the two credential-free chatops stacks on the app."""
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    deployment = _deployment(wl)

    sqs_stack = SQSStack(app, "ChatOpsSqs", env={"account": ACCOUNT, "region": REGION})
    sqs_stack.build(
        stack_config=StackConfig(find_stack(config, SQS_STACK_NAME), wl.dictionary),
        deployment=deployment,
        workload=wl,
    )

    eb_stack = EventBridgeStack(
        app, "ChatOpsEventBridge", env={"account": ACCOUNT, "region": REGION}
    )
    eb_stack.build(
        stack_config=StackConfig(
            find_stack(config, EVENTBRIDGE_STACK_NAME), wl.dictionary
        ),
        deployment=deployment,
        workload=wl,
    )
    return sqs_stack, eb_stack


def test_synth_succeeds_without_credentials():
    """Full app-level synth (what `cdk synth` does) — succeeds credential-free."""
    app = App()
    sqs_stack, eb_stack = _build_chatops_stacks(app)
    cloud_assembly = app.synth()
    assert cloud_assembly is not None
    names = {s.stack_name for s in cloud_assembly.stacks}
    assert "ChatOpsSqs" in names
    assert "ChatOpsEventBridge" in names


def test_no_context_lookups_emitted():
    """A value_from_lookup / context lookup would surface as a 'missing' entry in
    the synthesized manifest.json and/or produce a cdk.context.json, either of
    which forces a live AWS call at synth. Neither must appear for chatops."""
    import os

    app = App()
    _build_chatops_stacks(app)
    cloud_assembly = app.synth()
    out_dir = cloud_assembly.directory

    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    assert not manifest.get(
        "missing"
    ), f"unexpected context lookups: {manifest.get('missing')}"

    # value_from_lookup caches results in cdk.context.json — it must not exist.
    assert not os.path.exists(os.path.join(out_dir, "cdk.context.json"))


def test_queue_arns_resolved_via_ssm_token_not_lookup():
    """The EventBridge stack imports the queue ARN via an SSM-backed CfnParameter
    (deploy-time token), never a synth-time context lookup."""
    app = App()
    _, eb_stack = _build_chatops_stacks(app)
    eb_template = Template.from_stack(eb_stack).to_json()
    eb_json = json.dumps(eb_template)
    assert "SsmParameterValue" in eb_json
