"""
CodePipeline Monitor Stack Pattern for CDK-Factory

Config-driven monitor that watches AWS CodePipeline (and optionally CodeBuild)
state-change events and routes them to an adapter Lambda, which in turn emits a
normalized ``EventEnvelope`` onto the geek-cafe event_bus spine. This stack is
purely about **routing**: it builds its own ``events.Rule`` + a
``aws_events_targets.LambdaFunction`` target, importing the adapter Lambda ARN
from SSM as a deploy-time CloudFormation token. The adapter Lambda resource
(packaging, role, env vars, SSM ARN export) is deployed by an ordinary
``lambda_stack`` elsewhere.

Why its own module (not ``eventbridge_stack``): ``eventbridge_stack`` is
SQS-target-only (it attaches an ``AWS::SQS::QueuePolicy``). A Lambda target needs
an ``AWS::Lambda::Permission`` instead, and this module is the clean home for
CodePipeline/CodeBuild-specific config validation.

Lambda invoke permission: because the adapter Lambda is imported by ARN (not an
``IFunction`` owned by this stack), ``add_target`` cannot mutate its resource
policy. The stack attaches an explicit ``aws_lambda.CfnPermission`` granting
``lambda:InvokeFunction`` to ``events.amazonaws.com`` scoped via ``source_arn``
to the rule ARN — mirroring ``eventbridge_stack._grant_events_send_message`` and
``appsync_events_stack._grant_appsync_invoke_authorizer``.

Cross-stack ids (the adapter Lambda ARN) are resolved at DEPLOY time as
CloudFormation tokens via ``aws_ssm.StringParameter.value_for_string_parameter``
— no live boto3, no ``value_from_lookup`` at synth. Construct IDs are explicit,
slugged strings (never the builtin randomized-per-process ``hash`` function), so
synthesized logical IDs are reproducible across synths.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import re
from typing import List, Optional

from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.codepipeline_monitor import (
    CodePipelineMonitorConfig,
)
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="CodePipelineMonitorStack")

_CODEPIPELINE_SOURCE = "aws.codepipeline"
_CODEBUILD_SOURCE = "aws.codebuild"
_ACTION_EXECUTION_DETAIL_TYPE = "CodePipeline Action Execution State Change"


def _slug(value: str) -> str:
    """Slug a config value into a safe, deterministic construct-id segment.

    Never the builtin randomized-per-process ``hash`` function (if a suffix is
    ever needed, use ``hashlib``).
    """
    return re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()


@register_stack("codepipeline_monitor_library_module")
@register_stack("codepipeline_monitor_stack")
class CodePipelineMonitorStack(IStack):
    """
    Reusable stack that wires CodePipeline/CodeBuild state-change events to an
    adapter Lambda imported by ARN from SSM.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config: Optional[CodePipelineMonitorConfig] = None
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
        """Build the CodePipeline monitor stack."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        stack_dict = stack_config.dictionary
        stack_enabled = bool(stack_dict.get("enabled", True))
        self.config = CodePipelineMonitorConfig(
            stack_dict.get("codepipeline_monitor", {})
        )

        # "none" selection / disabled stack -> emit nothing (no resources).
        if not self.config.is_enabled(stack_enabled):
            logger.warning(
                "🚨 codepipeline_monitor is disabled "
                "(pipelines.mode == 'none' or enabled == false); no resources created."
            )
            return

        # Required cross-stack SSM path (fatal if missing — fail synth).
        if not self.config.adapter_lambda_arn_ssm_path:
            raise ValueError(
                "codepipeline_monitor config requires 'adapter_lambda_arn_ssm_path'"
            )

        # Resolve the adapter Lambda ARN at DEPLOY time (CF token, never a literal
        # and never live boto3).
        adapter_fn_arn = ssm.StringParameter.value_for_string_parameter(
            self, self.config.adapter_lambda_arn_ssm_path
        )

        base = self._base_name()
        slug = _slug(base)

        adapter_fn = _lambda.Function.from_function_arn(
            self, f"{slug}-adapter-fn", adapter_fn_arn
        )

        self._build_codepipeline_rule(slug, adapter_fn, adapter_fn_arn)
        if self.config.codebuild.enabled:
            self._build_codebuild_rule(slug, adapter_fn, adapter_fn_arn)

        self._export_to_ssm(base)

    def _base_name(self) -> str:
        """The construct-id / rule-name seed derived from config + deployment."""
        name = str(self.stack_config.dictionary.get("name", ""))
        if name:
            return name
        return (
            f"{self.deployment.workload_name}-"
            f"{self.deployment.environment}-codepipeline-monitor"
        )

    def _build_codepipeline_rule(
        self, slug: str, adapter_fn: _lambda.IFunction, adapter_fn_arn: str
    ) -> None:
        """Create the CodePipeline events.Rule -> adapter Lambda target."""
        pipelines = self.config.pipelines

        detail_types = list(self.config.detail_types)
        if self.config.approval_rejection.subscribe_action_execution:
            if _ACTION_EXECUTION_DETAIL_TYPE not in detail_types:
                detail_types.append(_ACTION_EXECUTION_DETAIL_TYPE)

        detail = {"state": list(self.config.state_priority_map.keys())}

        if pipelines.mode == "selected":
            detail["pipeline"] = pipelines.names
        elif pipelines.mode == "all" and pipelines.exclude_names:
            detail["pipeline"] = [{"anything-but": pipelines.exclude_names}]
        # mode == "all" with no exclude_names -> omit detail.pipeline entirely.

        event_pattern = events.EventPattern(
            source=[_CODEPIPELINE_SOURCE],
            detail_type=detail_types,
            detail=detail,
        )

        rule_id = f"{slug}-codepipeline-rule"
        rule = events.Rule(self, rule_id, event_pattern=event_pattern)
        rule.add_target(events_targets.LambdaFunction(adapter_fn))
        self._grant_events_invoke(rule_id, adapter_fn_arn, rule)
        self.rules.append(rule)

    def _build_codebuild_rule(
        self, slug: str, adapter_fn: _lambda.IFunction, adapter_fn_arn: str
    ) -> None:
        """Create the CodeBuild events.Rule -> adapter Lambda target."""
        codebuild = self.config.codebuild

        event_pattern = events.EventPattern(
            source=[_CODEBUILD_SOURCE],
            detail_type=codebuild.detail_types,
            detail={"build-status": list(codebuild.build_status_priority_map.keys())},
        )

        rule_id = f"{slug}-codebuild-rule"
        rule = events.Rule(self, rule_id, event_pattern=event_pattern)
        rule.add_target(events_targets.LambdaFunction(adapter_fn))
        self._grant_events_invoke(rule_id, adapter_fn_arn, rule)
        self.rules.append(rule)

    def _grant_events_invoke(
        self, rule_id: str, adapter_fn_arn: str, rule: events.Rule
    ) -> None:
        """Grant EventBridge permission to invoke the ARN-imported adapter Lambda.

        The Lambda is imported by ARN (a deploy-time SSM token), so there is no
        owned ``IFunction`` to mutate; use an L1 ``CfnPermission`` scoped via
        ``source_arn`` to this rule's ARN (never ``*``) — mirroring
        ``eventbridge_stack._grant_events_send_message`` and
        ``appsync_events_stack._grant_appsync_invoke_authorizer``.
        """
        _lambda.CfnPermission(
            self,
            f"{rule_id}-invoke-permission",
            action="lambda:InvokeFunction",
            function_name=adapter_fn_arn,
            principal="events.amazonaws.com",
            source_arn=rule.rule_arn,
        )

    def _export_to_ssm(self, base: str) -> None:
        """Publish each rule ARN to SSM.

        Uses the ``ssm.namespace`` prefix, falling back to
        ``/{workload}/{environment}/codepipeline-monitor`` for parity with the
        appsync_events / SQS / SNS modules.
        """
        ssm_config = self.config.ssm
        namespace = ssm_config.get("namespace")
        if namespace:
            prefix = f"/{namespace}"
        else:
            prefix = (
                f"/{self.deployment.workload_name}/"
                f"{self.deployment.environment}/codepipeline-monitor"
            )

        for rule in self.rules:
            rule_slug = _slug(rule.node.id)
            ssm.StringParameter(
                self,
                f"ssm-{rule_slug}-arn",
                parameter_name=f"{prefix}/{rule_slug}/arn",
                string_value=rule.rule_arn,
                description=f"CodePipeline monitor rule ARN for {rule.node.id}",
            )
