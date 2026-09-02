"""
SNS Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.sns import SNSConfig, SNSTopicConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SNSStack")


@register_stack("sns_library_module")
@register_stack("sns_stack")
class SNSStack(IStack):
    """
    Reusable stack for AWS Simple Notification Service (SNS).

    Creates one or more topics and, optionally, subscriptions (email, sms,
    https, etc.). Each topic's ARN is published to SSM Parameter Store and
    exported as a CloudFormation output so other stacks (e.g. a lambda_stack)
    can reference it.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.sns_config: SNSConfig | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.topics: dict[str, sns.Topic] = {}

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the SNS stack."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.sns_config = SNSConfig(stack_config.dictionary.get("sns", {}))

        if not self.sns_config.topics:
            logger.warning(
                "🚨 No SNS topics were defined in the sns_stack configuration."
            )
            return

        for topic_config in self.sns_config.topics:
            if not topic_config.name:
                raise ValueError(
                    "SNS topic config is missing the required 'name' field."
                )
            self._create_topic(topic_config)

        self._add_outputs()

    def _create_topic(self, topic_config: SNSTopicConfig) -> sns.Topic:
        """Create an SNS topic and attach any configured subscriptions."""
        # Resolve name once so the topic name, construct id, and SSM path all
        # use the fully-resolved value (no leftover {{placeholders}}).
        topic_name = self.deployment.build_resource_name(topic_config.name)

        # Use a stable construct id so the topic doesn't get recreated if the
        # stack is renamed (which would drop existing subscriptions).
        stable_id = topic_config.resource_id or f"sns-{topic_name}"

        topic_props: dict = {
            "topic_name": topic_name,
            "fifo": topic_config.fifo,
        }
        if topic_config.display_name:
            topic_props["display_name"] = topic_config.display_name

        topic = sns.Topic(self, stable_id, **topic_props)

        for index, sub in enumerate(topic_config.subscriptions):
            if not sub.endpoint:
                logger.warning(
                    f"Skipping subscription with empty endpoint on topic "
                    f"'{topic_name}' (protocol={sub.protocol})."
                )
                continue
            self._add_subscription(topic, topic_config, sub, index)

        self.topics[topic_name] = topic
        self._publish_topic_to_ssm(topic, topic_name)

        return topic

    def _add_subscription(self, topic, topic_config, sub, index: int) -> None:
        """Attach a single subscription to a topic based on its protocol."""
        protocol = sub.protocol.lower()

        if protocol in ("email", "email-json"):
            topic.add_subscription(
                subscriptions.EmailSubscription(
                    sub.endpoint,
                    json=(protocol == "email-json"),
                )
            )
        elif protocol == "sms":
            topic.add_subscription(subscriptions.SmsSubscription(sub.endpoint))
        elif protocol in ("https", "http"):
            topic.add_subscription(subscriptions.UrlSubscription(sub.endpoint))
        else:
            raise ValueError(
                f"Unsupported SNS subscription protocol '{sub.protocol}' on topic "
                f"'{topic_config.name}'. Supported: email, email-json, sms, https, http."
            )

    def _publish_topic_to_ssm(self, topic: sns.Topic, topic_name: str) -> None:
        """Publish the topic ARN to SSM Parameter Store.

        Uses the pattern /{namespace}/sns/{topic-name}/arn. Namespace comes from
        the stack config's ssm.namespace, falling back to
        {workload}/{environment} for parity with the SQS module.
        """
        ssm_config = (
            self.stack_config.dictionary.get("ssm", {}) if self.stack_config else {}
        )
        namespace = ssm_config.get("namespace")
        if namespace:
            prefix = f"/{namespace}"
        else:
            prefix = (
                f"/{self.deployment.workload_name}/{self.deployment.environment}/sns"
            )

        ssm.StringParameter(
            self,
            f"ssm-{topic_name}-arn",
            parameter_name=f"{prefix}/{topic_name}/arn",
            string_value=topic.topic_arn,
            description=f"SNS Topic ARN for {topic_name}",
        )

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for each created topic."""
        for topic_name, topic in self.topics.items():
            cdk.CfnOutput(
                self,
                f"{topic_name}-Arn",
                value=topic.topic_arn,
                description=f"SNS Topic ARN for {topic_name}",
            )
