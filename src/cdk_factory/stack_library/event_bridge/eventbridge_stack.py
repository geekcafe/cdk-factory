"""
EventBridge Stack Pattern for CDK-Factory

Net-new EventBridge-rule -> SQS-target support. For each ``event_bridge_rules``
entry it:

  1. Imports the target SQS queue by ARN resolved from SSM at DEPLOY time via a
     CloudFormation token (``aws_ssm.StringParameter.value_for_string_parameter``
     + ``aws_sqs.Queue.from_queue_arn``) — no live boto3, no ``value_from_lookup``
     at synth (NFR-2).
  2. Creates an ``events.Rule`` with the configured event pattern.
  3. Adds an ``aws_events_targets.SqsQueue`` target.
  4. Because the queue is IMPORTED (immutable), explicitly attaches an SQS
     resource policy (``AWS::SQS::QueuePolicy``) granting ``sqs:SendMessage`` to
     the ``events.amazonaws.com`` principal, conditioned on the rule ARN
     (``aws:SourceArn``). Without this grant, rule -> queue delivery silently
     fails.

Construct IDs are explicit, stable strings (never the builtin randomized-per-
process hash function), so the synthesized CloudFormation logical IDs are
reproducible across synths.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import List, Optional

from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.event_bridge_rules import (
    EventBridgeRuleConfig,
    EventBridgeRulesConfig,
)
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="EventBridgeStack")


@register_stack("eventbridge_library_module")
@register_stack("eventbridge_stack")
class EventBridgeStack(IStack):
    """
    Reusable stack that wires EventBridge rules to existing SQS queues.

    The target queue is created elsewhere (``sqs_stack``) and imported by ARN
    from SSM, keeping queue lifecycle decoupled from routing lifecycle.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config: Optional[EventBridgeRulesConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.rules: List[events.Rule] = []

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the EventBridge stack."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.config = EventBridgeRulesConfig(stack_config.dictionary)
        rules = self.config.rules
        if not rules:
            logger.warning("No event_bridge_rules defined in stack config")
            return

        for rule_config in rules:
            self._build_rule(rule_config)

    def _build_rule(self, rule_config: EventBridgeRuleConfig) -> None:
        """Create one rule -> SQS target with the required resource policy."""
        if not rule_config.target_queue_ssm_path:
            raise ValueError(
                f"EventBridge rule '{rule_config.name}' requires "
                "'target_queue_ssm_path'"
            )
        if not rule_config.event_pattern:
            raise ValueError(
                f"EventBridge rule '{rule_config.name}' requires 'event_pattern'"
            )

        workload = self.deployment.workload_name
        env = self.deployment.environment

        # Stable, explicit construct IDs (never the builtin randomized hashing).
        rule_id = f"{workload}-{env}-chatops-slack-rule"
        queue_id = f"{workload}-{env}-chatops-slack-rule-target-queue"

        # Import the target queue ARN from SSM at DEPLOY time (CF token).
        queue_arn = ssm.StringParameter.value_for_string_parameter(
            self, rule_config.target_queue_ssm_path
        )
        queue = sqs.Queue.from_queue_arn(self, queue_id, queue_arn=queue_arn)

        # Build the event pattern from the config dict.
        event_pattern = self._to_event_pattern(rule_config.event_pattern)

        rule = events.Rule(
            self,
            rule_id,
            rule_name=rule_config.name,
            event_bus=self._resolve_event_bus(rule_config, rule_id),
            event_pattern=event_pattern,
        )
        rule.add_target(events_targets.SqsQueue(queue))

        # The queue is IMPORTED (immutable), so add_target cannot mutate its
        # resource policy. Attach the required SQS resource policy explicitly,
        # scoped to this rule's ARN via the aws:SourceArn condition.
        self._grant_events_send_message(rule_id, queue, rule)

        self.rules.append(rule)

    def _resolve_event_bus(
        self, rule_config: EventBridgeRuleConfig, rule_id: str
    ) -> Optional[events.IEventBus]:
        """Resolve the target event bus.

        The AWS ``default`` bus is represented by ``None`` (CDK uses the account
        default bus when ``event_bus`` is omitted). A named custom bus is imported
        by name.
        """
        bus_name = rule_config.event_bus_name
        if not bus_name or bus_name == "default":
            return None
        return events.EventBus.from_event_bus_name(self, f"{rule_id}-bus", bus_name)

    def _to_event_pattern(self, pattern: dict) -> events.EventPattern:
        """Translate the config dict into an ``events.EventPattern``.

        Supports ``source``, ``detail-type``, and ``detail`` keys (the ones used
        by the chatops routing contract). Unknown keys are ignored.
        """
        kwargs = {}
        if "source" in pattern:
            kwargs["source"] = pattern["source"]
        if "detail-type" in pattern:
            kwargs["detail_type"] = pattern["detail-type"]
        if "detail" in pattern:
            kwargs["detail"] = pattern["detail"]
        return events.EventPattern(**kwargs)

    def _grant_events_send_message(
        self, rule_id: str, queue: sqs.IQueue, rule: events.Rule
    ) -> None:
        """Attach an SQS resource policy allowing EventBridge to send messages.

        Scoped to the rule ARN via ``aws:SourceArn`` so only this rule can enqueue.
        """
        statement = iam.PolicyStatement(
            sid="AllowEventBridgeSendMessage",
            effect=iam.Effect.ALLOW,
            actions=["sqs:SendMessage"],
            principals=[iam.ServicePrincipal("events.amazonaws.com")],
            resources=[queue.queue_arn],
            conditions={"ArnEquals": {"aws:SourceArn": rule.rule_arn}},
        )

        sqs.CfnQueuePolicy(
            self,
            f"{rule_id}-target-queue-policy",
            queues=[queue.queue_url],
            policy_document=iam.PolicyDocument(statements=[statement]),
        )
