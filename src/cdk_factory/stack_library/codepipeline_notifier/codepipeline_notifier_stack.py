"""
CodePipeline Notifier Stack Pattern for CDK-Factory

SELF-CONTAINED companion to ``codepipeline_monitor_stack``. Where the monitor
module is routing-only (it imports a foreign adapter Lambda by ARN and emits a
normalized event onto the geek-cafe event_bus spine), this module provisions the
WHOLE self-contained monitor-and-notify graph in ONE stack:

  - per-channel ``aws_sns.Topic`` + ``EmailSubscription`` for each channel that
    has at least one email address;
  - an OWNED notifier ``aws_lambda.Function`` packaged from the standalone
    project's ``src/devops_monitoring_lambdas`` via ``LambdaFunctionUtilities.create``;
  - the EventBridge rule(s) (CodePipeline, and optionally CodeBuild) targeting
    that owned Lambda; and
  - a scoped, opt-in IAM role (``secretsmanager:GetSecretValue`` on the one
    bot-token secret, ``sns:Publish`` on EXACTLY the created topics, Logs on the
    function's own log group — never ``*``).

Owned-function invoke permission: because the notifier is an owned ``IFunction``
created in this stack, ``rule.add_target(LambdaFunction(fn))`` auto-adds the
``AWS::Lambda::Permission`` for ``events.amazonaws.com`` scoped to the rule ARN
— so, unlike ``codepipeline_monitor_stack``, this module does NOT hand-roll a
``CfnPermission`` (design §3.3).

Role-finalization ordering is LOAD-BEARING (design §6.2 step 5 / §6.6):
``LambdaFunctionUtilities.create`` freezes the role via
``role.without_policy_updates()`` before attaching it to the function, so any
statement added AFTER ``create()`` silently does NOT attach (synth + rule-level
assertions still pass, but every delivery fails at runtime with AccessDenied).
The build sequence is therefore fixed: create SNS topics (so ``topic.topic_arn``
tokens exist) → FULLY populate the notifier role with every statement → create
the Lambda.

No live boto3 at synth, no ``value_from_lookup``: the secret is referenced by
name → constructed ARN string; the SNS topic ARNs are in-process CDK tokens.
Construct ids are explicit, slugged strings (never the builtin
randomized-per-process ``hash``; ``hashlib`` only if a suffix is ever needed),
so synthesized logical ids are reproducible across synths.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import json
import re
from typing import Dict, List, Optional

from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.codepipeline_notifier import (
    CodePipelineNotifierConfig,
)
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.utilities.lambda_function_utilities import LambdaFunctionUtilities
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="CodePipelineNotifierStack")

_CODEPIPELINE_SOURCE = "aws.codepipeline"
_CODEBUILD_SOURCE = "aws.codebuild"
_ACTION_EXECUTION_DETAIL_TYPE = "CodePipeline Action Execution State Change"
_VALID_PRIORITIES = {"critical", "normal"}

# SSM fallback-namespace literal. MUST be 'codepipeline-notifier' (the monitor
# module uses its own distinct literal) — a copy-paste of the old literal would
# be a defect (design §6.2 step 7 / §11 test 11).
_SSM_FALLBACK_SEGMENT = "codepipeline-notifier"


def _slug(value: str) -> str:
    """Slug a config value into a safe, deterministic construct-id segment.

    Never the builtin randomized-per-process ``hash`` function (if a suffix is
    ever needed, use ``hashlib``).
    """
    return re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()


@register_stack("codepipeline_notifier_library_module")
@register_stack("codepipeline_notifier_stack")
class CodePipelineNotifierStack(IStack):
    """
    Reusable, self-contained stack that provisions per-channel SNS topics, an
    owned notifier Lambda, the EventBridge rule(s) targeting it, and scoped IAM.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config: Optional[CodePipelineNotifierConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.topics: Dict[str, sns.Topic] = {}
        self.notifier_fn: Optional[_lambda.Function] = None
        self.rules: List[events.Rule] = []

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the CodePipeline notifier stack (ordered — see module docstring)."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        stack_dict = stack_config.dictionary
        stack_enabled = bool(stack_dict.get("enabled", True))
        self.config = CodePipelineNotifierConfig(
            stack_dict.get("codepipeline_notifier", {})
        )

        # (1) "none" selection / disabled stack -> emit nothing (no resources).
        if not self.config.is_enabled(stack_enabled):
            logger.warning(
                "🚨 codepipeline_notifier is disabled "
                "(pipelines.mode == 'none' or enabled == false); no resources created."
            )
            return

        # (2) Validate config (fail synth with clear messages).
        self._validate()

        base = self._base_name()
        slug = _slug(base)

        # (3) SNS topics per channel-with-emails (ARNs needed before the role).
        channel_topic_arns = self._build_sns_topics(slug)

        # (4) FULLY populate the scoped notifier role BEFORE Lambda creation.
        notifier_role = self._build_notifier_role(slug, channel_topic_arns)

        # (5) Env wire format (zips channels with topic ARNs + slack ids).
        environment = self._build_environment(channel_topic_arns)

        # (6) Create the OWNED notifier Lambda via the shared packaging helper.
        self.notifier_fn = self._create_notifier_lambda(
            slug, environment, notifier_role
        )

        # (7) Rule(s) -> owned Lambda target (auto invoke permission).
        self._build_codepipeline_rule(slug)
        if self.config.codebuild.enabled:
            self._build_codebuild_rule(slug)

        # (8) Export rule / topic / lambda ARNs to SSM.
        self._export_to_ssm(channel_topic_arns)

    # -- (1) naming --------------------------------------------------------

    def _base_name(self) -> str:
        """The construct-id / rule-name seed derived from config + deployment."""
        name = str(self.stack_config.dictionary.get("name", ""))
        if name:
            return name
        return (
            f"{self.deployment.workload_name}-"
            f"{self.deployment.environment}-codepipeline-notifier"
        )

    # -- (2) validation ----------------------------------------------------

    def _validate(self) -> None:
        """Fail synth on an unusable config (mirrors appsync_events discipline)."""
        channels = self.config.channels
        if not channels:
            raise ValueError(
                "codepipeline_notifier config requires at least one channel in 'channels'"
            )

        any_slack = False
        for name, channel in channels.items():
            has_slack = bool(channel.slack_channel_id)
            has_email = bool(channel.sns_emails)
            if not has_slack and not has_email:
                raise ValueError(
                    f"codepipeline_notifier channel '{name}' has neither a "
                    "'slack_channel_id' nor any 'sns_emails' — a channel must have "
                    "at least one delivery target."
                )
            any_slack = any_slack or has_slack

        central = self.config.central
        if not central:
            raise ValueError(
                "codepipeline_notifier config requires a 'central' channel name"
            )
        if central not in channels:
            raise ValueError(
                f"codepipeline_notifier 'central' channel '{central}' is not a key "
                "in 'channels'"
            )

        for pipeline, route_channels in self.config.pipeline_routes.items():
            for channel_name in route_channels:
                if channel_name not in channels:
                    raise ValueError(
                        f"codepipeline_notifier pipeline_routes['{pipeline}'] "
                        f"references channel '{channel_name}' which is not a key in "
                        "'channels'"
                    )

        self._validate_priorities(self.config.state_priority_map, "state_priority_map")
        self._validate_priorities(
            self.config.codebuild.build_status_priority_map,
            "codebuild.build_status_priority_map",
        )
        for priority in self.config.deliver_priorities:
            if priority not in _VALID_PRIORITIES:
                raise ValueError(
                    f"codepipeline_notifier deliver_priorities value '{priority}' "
                    f"must be one of {sorted(_VALID_PRIORITIES)}"
                )

        if any_slack and not self.config.slack_bot_token_secret_name:
            raise ValueError(
                "codepipeline_notifier config requires a non-empty "
                "'slack_bot_token_secret_name' because at least one channel posts "
                "to Slack."
            )

    @staticmethod
    def _validate_priorities(priority_map: Dict[str, str], label: str) -> None:
        for state, priority in priority_map.items():
            if priority not in _VALID_PRIORITIES:
                raise ValueError(
                    f"codepipeline_notifier {label}['{state}'] priority "
                    f"'{priority}' must be one of {sorted(_VALID_PRIORITIES)}"
                )

    # -- (3) SNS -----------------------------------------------------------

    def _build_sns_topics(self, slug: str) -> Dict[str, str]:
        """Create one SNS topic (+ email subscriptions) per channel-with-emails.

        Inlines the ``sns_stack`` create-topic+subscriptions logic (no
        intra-library stack coupling) so the per-channel topic ARNs are
        available in-process to pass into the role and the Lambda env.
        """
        channel_topic_arns: Dict[str, str] = {}
        for name, channel in self.config.channels.items():
            if not channel.sns_emails:
                continue
            topic_name = self.deployment.build_resource_name(f"{slug}-{_slug(name)}")
            topic = sns.Topic(
                self,
                f"sns-{topic_name}",
                topic_name=topic_name,
            )
            for email in channel.sns_emails:
                topic.add_subscription(subscriptions.EmailSubscription(email))
            self.topics[name] = topic
            channel_topic_arns[name] = topic.topic_arn
        return channel_topic_arns

    # -- (4) IAM -----------------------------------------------------------

    def _build_notifier_role(
        self, slug: str, channel_topic_arns: Dict[str, str]
    ) -> iam.Role:
        """Build and FULLY populate the scoped notifier role BEFORE Lambda creation.

        Load-bearing ordering (design §6.2 step 5 / §6.6): every statement must
        be attached here, before ``LambdaFunctionUtilities.create`` freezes the
        role via ``role.without_policy_updates()``.
        """
        role = iam.Role(
            self,
            f"{slug}-notifier-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Scoped execution role for the CodePipeline notifier Lambda",
        )

        # Logs on the function's own group (CDK also wires the log group grant,
        # but include the base managed policy so the function can create/put).
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # secretsmanager:GetSecretValue on the ONE bot-token secret ARN pattern
        # (trailing '*' for the random suffix) — never '*'.
        secret_name = self.config.slack_bot_token_secret_name
        if secret_name:
            secret_arn = (
                f"arn:aws:secretsmanager:{self.deployment.region}:"
                f"{self.deployment.account}:secret:{secret_name}*"
            )
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="SlackBotTokenGet",
                    effect=iam.Effect.ALLOW,
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[secret_arn],
                )
            )

        # sns:Publish on EXACTLY the created topic ARNs — never '*', never topic/*.
        topic_arns = list(channel_topic_arns.values())
        if topic_arns:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="NotifierSnsPublish",
                    effect=iam.Effect.ALLOW,
                    actions=["sns:Publish"],
                    resources=topic_arns,
                )
            )

        return role

    # -- (5) env -----------------------------------------------------------

    def _build_environment(self, channel_topic_arns: Dict[str, str]) -> Dict[str, str]:
        """Build the MONITOR_* handler env wire format (design §6.5 / §8.3).

        Scalars are plain strings; maps/lists are JSON-encoded strings the
        handler ``json.loads`` back. The module zips the channel list with the
        just-created topic ARNs + each channel's ``slack_channel_id`` into
        ``MONITOR_CHANNELS`` so the handler performs no AWS discovery.
        """
        monitor_channels: Dict[str, Dict[str, str]] = {}
        for name, channel in self.config.channels.items():
            entry = {
                "slack_channel_id": channel.slack_channel_id,
                "sns_topic_arn": channel_topic_arns.get(name, ""),
            }
            # Only emit the optional per-channel broadcast mention when set, so
            # channels without one keep today's exact 2-key shape.
            if channel.mention:
                entry["mention"] = channel.mention
            monitor_channels[name] = entry

        env: Dict[str, str] = {
            "MONITOR_CENTRAL_CHANNEL": self.config.central,
            "MONITOR_CHANNELS": json.dumps(monitor_channels),
            "MONITOR_STATE_PRIORITY_MAP": json.dumps(self.config.state_priority_map),
            "MONITOR_BUILD_STATUS_PRIORITY_MAP": json.dumps(
                self.config.codebuild.build_status_priority_map
            ),
            "MONITOR_DELIVER_PRIORITIES": json.dumps(self.config.deliver_priorities),
            "MONITOR_PIPELINE_ROUTES": json.dumps(self.config.pipeline_routes),
            "MONITOR_APPROVAL_REJECTION": json.dumps(
                self.config.approval_rejection.to_dict()
            ),
            "MONITOR_CONSOLE_BASE_URL": self.config.console_base_url,
        }

        # Required iff any channel posts to Slack (validated at synth); emit it
        # whenever a secret name is configured.
        if self.config.slack_bot_token_secret_name:
            env["MONITOR_SLACK_BOT_TOKEN_SECRET_ID"] = (
                self.config.slack_bot_token_secret_name
            )

        return env

    # -- (6) Lambda --------------------------------------------------------

    def _create_notifier_lambda(
        self,
        slug: str,
        environment: Dict[str, str],
        notifier_role: iam.Role,
    ) -> _lambda.Function:
        """Create the OWNED notifier Lambda via the shared packaging helper.

        Uses ``LambdaFunctionUtilities.create`` (the same path ``lambda_stack``
        uses), so the whole standalone package (``handlers/`` AND the sibling
        ``notify/`` package) is bundled from ``lambda.src`` (the PACKAGE root),
        not the handler sub-dir (design §4.1 / §6.2 step 5).
        """
        lambda_cfg_dict = dict(self.config.lambda_config)
        # Default a stable logical name if the config omits one.
        if not lambda_cfg_dict.get("name"):
            lambda_cfg_dict["name"] = f"{slug}-notifier"

        lambda_config = LambdaFunctionConfig(
            lambda_cfg_dict, deployment=self.deployment
        )

        utilities = LambdaFunctionUtilities(
            deployment=self.deployment, workload=self.workload
        )
        return utilities.create(
            self,
            f"{slug}-notifier-fn",
            lambda_config,
            environment=environment,
            role=notifier_role,
        )

    # -- (7) rules ---------------------------------------------------------

    def _build_codepipeline_rule(self, slug: str) -> None:
        """Create the CodePipeline events.Rule -> owned notifier Lambda target.

        Duplicates ``codepipeline_monitor_stack``'s event-pattern construction
        intentionally (the design permits duplicating the ~15 lines rather than
        risking the existing monitor test suite via a shared extract).
        """
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

        rule = events.Rule(
            self, f"{slug}-codepipeline-rule", event_pattern=event_pattern
        )
        rule.add_target(events_targets.LambdaFunction(self.notifier_fn))
        self.rules.append(rule)

    def _build_codebuild_rule(self, slug: str) -> None:
        """Create the CodeBuild events.Rule -> owned notifier Lambda target."""
        codebuild = self.config.codebuild

        event_pattern = events.EventPattern(
            source=[_CODEBUILD_SOURCE],
            detail_type=codebuild.detail_types,
            detail={"build-status": list(codebuild.build_status_priority_map.keys())},
        )

        rule = events.Rule(self, f"{slug}-codebuild-rule", event_pattern=event_pattern)
        rule.add_target(events_targets.LambdaFunction(self.notifier_fn))
        self.rules.append(rule)

    # -- (8) SSM export ----------------------------------------------------

    def _export_to_ssm(self, channel_topic_arns: Dict[str, str]) -> None:
        """Publish rule / topic / lambda ARNs to SSM.

        Uses the ``ssm.namespace`` prefix, falling back to the
        ``_SSM_FALLBACK_SEGMENT`` literal (``codepipeline-notifier``) under
        ``/{workload}/{environment}/`` — the notifier's own distinct namespace.
        """
        # The ``ssm`` block may live either at the stack top level (a sibling of
        # ``name`` / ``codepipeline_notifier`` — how the monitor config places it)
        # or nested inside the ``codepipeline_notifier`` sub-block. Prefer the
        # top-level placement, then fall back to the nested one, then to the
        # workload/environment literal. Reading only the nested block silently
        # drops a top-level ``ssm.namespace`` (e.g. the tenant-segmented prefix),
        # which would collapse two tenants' SSM parameters to identical names in a
        # shared account.
        stack_ssm = self.stack_config.dictionary.get("ssm")
        stack_ssm = stack_ssm if isinstance(stack_ssm, dict) else {}
        namespace = stack_ssm.get("namespace") or self.config.ssm.get("namespace")
        if namespace:
            prefix = f"/{namespace}"
        else:
            prefix = (
                f"/{self.deployment.workload_name}/"
                f"{self.deployment.environment}/{_SSM_FALLBACK_SEGMENT}"
            )

        for rule in self.rules:
            rule_slug = _slug(rule.node.id)
            ssm.StringParameter(
                self,
                f"ssm-{rule_slug}-arn",
                parameter_name=f"{prefix}/{rule_slug}/arn",
                string_value=rule.rule_arn,
                description=f"CodePipeline notifier rule ARN for {rule.node.id}",
            )

        for channel_name, topic in self.topics.items():
            topic_slug = _slug(channel_name)
            ssm.StringParameter(
                self,
                f"ssm-topic-{topic_slug}-arn",
                parameter_name=f"{prefix}/topics/{topic_slug}/arn",
                string_value=topic.topic_arn,
                description=f"CodePipeline notifier SNS topic ARN for {channel_name}",
            )

        if self.notifier_fn is not None:
            ssm.StringParameter(
                self,
                "ssm-notifier-lambda-arn",
                parameter_name=f"{prefix}/lambda/arn",
                string_value=self.notifier_fn.function_arn,
                description="CodePipeline notifier Lambda ARN",
            )
