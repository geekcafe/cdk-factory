"""
Multi-rule synth tests for eventbridge_stack (FEAT-002, phase1-design §3).

Proves the construct-ID generalization of ``_build_rule``:

  1. Backward compatibility (hard requirement): the existing single-rule chatops
     config synthesizes to BYTE-IDENTICAL logical IDs for the ``AWS::Events::Rule``
     and ``AWS::SQS::QueuePolicy`` — i.e. a zero CloudFormation diff. Because the
     config ``name`` already ends in ``-rule`` and slugs to itself, the derived
     ``rule_id`` reproduces today's literal ``myapp-dev-chatops-slack-rule`` (and
     its ``-target-queue``/``-target-queue-policy`` forms). A regressed derivation
     — notably the double-``-rule`` mistake — would change these ids and fail here.

  2. Multi-rule safety: a config with TWO rules synthesizes two ``AWS::Events::Rule``
     resources with distinct Names and distinct logical IDs, and two distinct
     ``AWS::SQS::QueuePolicy`` resources, with NO construct-ID collision (synth does
     not raise).

The second rule in the two-rule config is a TEST FIXTURE ONLY — it is not the
Phase-2 realtime rule and nothing here ships a realtime rule config.

No live AWS, no builtin ``hash()`` — credential-free synth via Template.from_stack.
"""

from typing import Any, Dict, List

from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.event_bridge.eventbridge_stack import EventBridgeStack
from cdk_factory.workload.workload_factory import WorkloadConfig

from chatops_config_helpers import (
    EVENTBRIDGE_STACK_NAME,
    find_stack,
    load_chatops_config,
)


WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"

# Today's literal CloudFormation logical IDs (pre-change) that the slug
# derivation MUST reproduce byte-identically for the single-rule chatops config.
#
# A CloudFormation logical ID is CDK's sanitized construct id (non-alphanumeric
# characters stripped), optionally followed by an 8-char suffix that is a
# DETERMINISTIC function of the construct's full path (not Python's randomized
# builtin ``hash()``). The base — and the suffix, when CDK adds one — are a pure
# function of ``rule_id``, so a regressed derivation (in particular the
# double-``-rule`` mistake, ``...slackrulerule...``) would alter these ids.
# Pinning the full logical ids below guards the zero-CF-diff invariant.
EXPECTED_RULE_LOGICAL_ID = "myappdevchatopsslackruleC9B7282F"
EXPECTED_QUEUE_POLICY_LOGICAL_ID = "myappdevchatopsslackruletargetqueuepolicy"


def _build_template_from_eb_config(eb_stack_cfg: Dict[str, Any]) -> Template:
    """Synthesize an EventBridgeStack from a resolved eventbridge stack dict."""
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
        app, "EventBridgeMultiRule", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def _two_rule_eb_config() -> Dict[str, Any]:
    """A self-contained two-rule EventBridge stack config (TEST FIXTURE ONLY).

    The second rule is NOT a shipped realtime rule — it exists purely to prove
    two rules can co-exist in one stack without a construct-ID collision.
    """
    return {
        "name": EVENTBRIDGE_STACK_NAME,
        "module": "eventbridge_stack",
        "enabled": True,
        "event_bridge_rules": [
            {
                "name": f"{WORKLOAD}-{ENV}-chatops-slack-rule",
                "event_bus_name": "default",
                "event_pattern": {
                    "source": ["geekcafe.chatops"],
                    "detail-type": ["ChatOpsMessage"],
                    "detail": {"platform": ["slack"]},
                },
                "target_queue_ssm_path": (
                    f"/chatops/{ENV}/sqs/{WORKLOAD}-{ENV}-chatops-slack/arn"
                ),
            },
            {
                "name": f"{WORKLOAD}-{ENV}-chatops-realtime-rule",
                "event_bus_name": "default",
                "event_pattern": {
                    "source": ["geekcafe.chatops"],
                    "detail-type": ["ChatOpsMessage"],
                    "detail": {"platform": ["realtime"]},
                },
                "target_queue_ssm_path": (
                    f"/chatops/{ENV}/sqs/{WORKLOAD}-{ENV}-chatops-realtime/arn"
                ),
            },
        ],
    }


def _logical_ids(template: Template, resource_type: str) -> List[str]:
    return list(template.find_resources(resource_type).keys())


# ---------------------------------------------------------------------------
# 1. Backward-compat regression: single-rule config -> byte-identical ids
# ---------------------------------------------------------------------------


def test_single_rule_logical_ids_are_byte_identical_to_legacy_literals():
    """The slug derivation reproduces today's literal construct IDs exactly.

    Guards the zero-CloudFormation-diff invariant and directly catches the
    double-``-rule`` regression (which would yield ``...slackrulerule...``).
    """
    config = load_chatops_config(WORKLOAD, ENV, ACCOUNT, REGION)
    eb_stack_cfg = find_stack(config, EVENTBRIDGE_STACK_NAME)
    template = _build_template_from_eb_config(eb_stack_cfg)

    rule_ids = _logical_ids(template, "AWS::Events::Rule")
    policy_ids = _logical_ids(template, "AWS::SQS::QueuePolicy")

    assert rule_ids == [EXPECTED_RULE_LOGICAL_ID]
    assert policy_ids == [EXPECTED_QUEUE_POLICY_LOGICAL_ID]


# ---------------------------------------------------------------------------
# 2. Multi-rule safety: two rules -> distinct ids, no collision
# ---------------------------------------------------------------------------


def test_two_rules_synthesize_without_construct_id_collision():
    """Two rules in one stack synth to two distinct rules + two distinct policies."""
    template = _build_template_from_eb_config(_two_rule_eb_config())

    template.resource_count_is("AWS::Events::Rule", 2)
    template.resource_count_is("AWS::SQS::QueuePolicy", 2)

    rule_ids = _logical_ids(template, "AWS::Events::Rule")
    policy_ids = _logical_ids(template, "AWS::SQS::QueuePolicy")

    # Distinct logical IDs (no construct-ID collision).
    assert len(set(rule_ids)) == 2
    assert len(set(policy_ids)) == 2

    # Distinct rule Names, matching the two configured names.
    rules = template.find_resources("AWS::Events::Rule")
    names = sorted(r["Properties"]["Name"] for r in rules.values())
    assert names == [
        f"{WORKLOAD}-{ENV}-chatops-realtime-rule",
        f"{WORKLOAD}-{ENV}-chatops-slack-rule",
    ]


def test_two_rule_config_preserves_legacy_rule_logical_id():
    """The slack rule keeps its legacy logical ID even alongside a second rule."""
    template = _build_template_from_eb_config(_two_rule_eb_config())
    rule_ids = _logical_ids(template, "AWS::Events::Rule")
    assert EXPECTED_RULE_LOGICAL_ID in rule_ids
