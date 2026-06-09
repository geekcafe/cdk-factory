"""
SQS Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.sqs import SQS as SQSConfig
from cdk_factory.constructs.sqs.policies.sqs_policies import SqsPolicies
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SQSStack")


@register_stack("sqs_library_module")
@register_stack("sqs_stack")
class SQSStack(IStack):
    """
    Reusable stack for AWS Simple Queue Service (SQS).
    Supports creating standard and FIFO queues with customizable settings.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.sqs_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.queues = {}
        self.dead_letter_queues = {}

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the SQS stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the SQS stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Load SQS configuration — consumer queues are already populated by
        # CdkConfig._resolve_lambda_config_paths() during config resolution.
        self.sqs_config = SQSConfig(stack_config.dictionary.get("sqs", {}))

        # Load standalone queue configs from directory (new)
        queue_config_dir = stack_config.dictionary.get("queue_config_dir", "")
        if queue_config_dir:
            standalone_configs = self._load_standalone_queue_configs(queue_config_dir)
            for config in standalone_configs:
                resolved = self._resolve_template_variables(config)
                # Map standalone config fields to what SQSConfig expects
                normalized = self._normalize_standalone_config(resolved)
                queue_config = SQSConfig(normalized)
                if not queue_config.name:
                    raise ValueError(
                        f"Standalone queue config is missing required 'queue_name' "
                        f"(or 'name') field: {config}"
                    )
                self.sqs_config.queues.append(queue_config)

        # Validate discovered consumer queues have required fields
        for queue_config in self.sqs_config.queues:
            if queue_config.is_consumer:
                if queue_config.visibility_timeout_seconds <= 0:
                    raise ValueError(
                        f"Consumer queue '{queue_config.name}' is missing or has "
                        f"invalid 'visibility_timeout_seconds' (must be > 0)"
                    )
                if queue_config.message_retention_period_days <= 0:
                    raise ValueError(
                        f"Consumer queue '{queue_config.name}' is missing or has "
                        f"invalid 'message_retention_period_days' (must be > 0)"
                    )

        # Process each queue in the configuration
        for queue_config in self.sqs_config.queues:
            queue_name = deployment.build_resource_name(queue_config.name)

            # Create dead letter queue if specified
            if queue_config.add_dead_letter_queue:
                self._create_dead_letter_queue(queue_config, queue_name)

            # Create the main queue
            self._create_queue(queue_config, queue_name, deployment)

        # Add outputs
        self._add_outputs()

    def _publish_queue_to_ssm(
        self, queue: sqs.Queue, queue_config: SQSConfig, is_dlq: bool = False
    ) -> None:
        """Publish queue ARN and URL to SSM Parameter Store.

        Uses the pattern /{namespace}/sqs/{queue-name}/arn
        and /{namespace}/sqs/{queue-name}/url.
        For DLQs, the suffix is {queue-name}-dlq.

        Namespace is read from the stack config's ssm.namespace field,
        falling back to {workload}/{environment} for backward compatibility.
        """
        ssm_config = (
            self.stack_config.dictionary.get("ssm", {}) if self.stack_config else {}
        )
        namespace = ssm_config.get("namespace")
        if namespace:
            prefix = f"/{namespace}"
        else:
            prefix = (
                f"/{self.deployment.workload_name}/{self.deployment.environment}/sqs"
            )
        suffix = f"{queue_config.name}-dlq" if is_dlq else queue_config.name

        ssm.StringParameter(
            self,
            f"ssm-{suffix}-arn",
            parameter_name=f"{prefix}/{suffix}/arn",
            string_value=queue.queue_arn,
            description=f"SQS {'DLQ ' if is_dlq else ''}Queue ARN for {suffix}",
        )

        ssm.StringParameter(
            self,
            f"ssm-{suffix}-url",
            parameter_name=f"{prefix}/{suffix}/url",
            string_value=queue.queue_url,
            description=f"SQS {'DLQ ' if is_dlq else ''}Queue URL for {suffix}",
        )

    def _create_queue(
        self, queue_config: SQSConfig, queue_name: str, deployment: DeploymentConfig
    ) -> sqs.Queue:
        """Create an SQS queue with the specified configuration"""
        # Determine if this is a FIFO queue
        is_fifo = queue_name.endswith(".fifo")

        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        # Queue recreation would cause message loss, so construct ID must be stable
        stable_queue_id = (
            queue_config.resource_id
            or f"{deployment.workload_name}-{deployment.environment}-sqs-{queue_config.name}"
        )

        # Configure queue properties
        queue_props = {
            "queue_name": queue_name,
            "visibility_timeout": (
                cdk.Duration.seconds(queue_config.visibility_timeout_seconds)
                if queue_config.visibility_timeout_seconds > 0
                else None
            ),
            "retention_period": (
                cdk.Duration.days(queue_config.message_retention_period_days)
                if queue_config.message_retention_period_days > 0
                else None
            ),
            "delivery_delay": (
                cdk.Duration.seconds(queue_config.delay_seconds)
                if queue_config.delay_seconds > 0
                else None
            ),
            "fifo": is_fifo,
        }

        # Add dead letter queue if it exists
        dlq_id = f"{queue_name}-dlq"
        if dlq_id in self.dead_letter_queues:
            queue_props["dead_letter_queue"] = sqs.DeadLetterQueue(
                max_receive_count=queue_config.max_receive_count,
                queue=self.dead_letter_queues[dlq_id],
            )

        # Remove None values
        queue_props = {k: v for k, v in queue_props.items() if v is not None}

        # Create the queue
        queue = sqs.Queue(self, stable_queue_id, **queue_props)

        # Enforce TLS policy on the queue
        result = queue.add_to_resource_policy(SqsPolicies.get_tls_policy(queue))
        assert result.statement_added, f"Failed to add TLS policy to queue {queue_name}"

        # Store the queue for later reference
        self.queues[queue_name] = queue

        # Publish queue ARN and URL to SSM Parameter Store
        self._publish_queue_to_ssm(queue, queue_config, is_dlq=False)

        return queue

    def _create_dead_letter_queue(
        self, queue_config: SQSConfig, queue_name: str
    ) -> sqs.Queue:
        """Create a dead letter queue for the specified queue"""
        # Determine if this is a FIFO queue
        is_fifo = queue_name.endswith(".fifo")

        # Create DLQ name
        dlq_name = f"{queue_name}-dlq"

        # Configure DLQ properties
        dlq_props = {
            "queue_name": dlq_name,
            "retention_period": cdk.Duration.days(14),  # Default 14 days for DLQ
            "fifo": is_fifo,
        }

        # Create the DLQ
        dlq = sqs.Queue(self, dlq_name, **dlq_props)

        # Enforce TLS policy on the DLQ
        result = dlq.add_to_resource_policy(SqsPolicies.get_tls_policy(dlq))
        assert result.statement_added, f"Failed to add TLS policy to DLQ {dlq_name}"

        # CloudWatch alarm: fires when any message lands in the DLQ
        cloudwatch.Alarm(
            self,
            id=f"{dlq_name}-alarm",
            alarm_name=f"{dlq_name}-messages",
            alarm_description=(
                f"DLQ alarm for {dlq_name}. "
                f"Messages in this queue indicate Lambda failures "
                f"that exhausted SQS retries."
            ),
            metric=dlq.metric_approximate_number_of_messages_visible(
                period=cdk.Duration.minutes(1),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Store the DLQ for later reference
        self.dead_letter_queues[dlq_name] = dlq

        # Publish DLQ ARN and URL to SSM Parameter Store
        self._publish_queue_to_ssm(dlq, queue_config, is_dlq=True)

        return dlq

    def _load_standalone_queue_configs(self, config_dir: str) -> list[dict]:
        """Load all JSON files from the standalone queue config directory.

        Args:
            config_dir: Path to directory containing standalone queue JSON config files.

        Returns:
            List of parsed config dictionaries, sorted alphabetically by filename.
            Returns an empty list if the directory does not exist.
        """
        configs: list[dict] = []
        dir_path = Path(config_dir)
        if not dir_path.exists():
            return configs
        for json_file in sorted(dir_path.glob("*.json")):
            with open(json_file, "r") as f:
                config = json.load(f)
                configs.append(config)
        return configs

    def _resolve_template_variables(self, config: dict) -> dict:
        """Resolve template variables like {{WORKLOAD_NAME}} in config values.

        Serializes the config to a JSON string, performs string replacements
        for known template variables, then deserializes back to a dict.

        Args:
            config: A queue config dictionary potentially containing template variables.

        Returns:
            A new dict with all known template variables replaced.
        """
        variables = {
            "WORKLOAD_NAME": self.deployment.workload_name,
            "DEPLOYMENT_NAMESPACE": self.deployment.environment,
        }
        config_str = json.dumps(config)
        for key, value in variables.items():
            config_str = config_str.replace(f"{{{{{key}}}}}", value)
        return json.loads(config_str)

    def _normalize_standalone_config(self, config: dict) -> dict:
        """Normalize a standalone queue config to the format expected by SQSConfig.

        Standalone configs use `name` for the queue name and a `dead_letter_queue`
        object for DLQ settings. The SQSConfig model expects `queue_name` and
        `add_dead_letter_queue` (boolean). This method bridges the two formats.

        Args:
            config: A resolved standalone queue config dictionary.

        Returns:
            A new dict compatible with SQSConfig constructor expectations.
        """
        normalized = dict(config)

        # Map 'name' to 'queue_name' if 'queue_name' is not already present
        if "name" in normalized and "queue_name" not in normalized:
            normalized["queue_name"] = normalized.pop("name")

        # Map 'dead_letter_queue' object to 'add_dead_letter_queue' boolean
        # and extract max_receive_count from the DLQ object
        dlq_config = normalized.pop("dead_letter_queue", None)
        if dlq_config and isinstance(dlq_config, dict):
            normalized["add_dead_letter_queue"] = "true"
            # Use DLQ's max_receive_count if provided, otherwise keep default
            if "max_receive_count" in dlq_config:
                normalized["max_receive_count"] = dlq_config["max_receive_count"]
            # Store DLQ retention for the _create_dead_letter_queue method
            if "message_retention_period_days" in dlq_config:
                normalized["dlq_message_retention_period_days"] = dlq_config[
                    "message_retention_period_days"
                ]

        return normalized

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for the SQS queues"""
        # Export primary queues
        for q_name, queue in self.queues.items():
            cdk.CfnOutput(
                self,
                f"{q_name}-Arn",
                value=queue.queue_arn,
                description=f"SQS Queue ARN for {q_name}",
            )
            cdk.CfnOutput(
                self,
                f"{q_name}-Url",
                value=queue.queue_url,
                description=f"SQS Queue URL for {q_name}",
            )
        # Export DLQs
        for dlq_name, dlq in self.dead_letter_queues.items():
            cdk.CfnOutput(
                self,
                f"{dlq_name}-Arn",
                value=dlq.queue_arn,
                description=f"SQS DLQ ARN for {dlq_name}",
            )
            cdk.CfnOutput(
                self,
                f"{dlq_name}-Url",
                value=dlq.queue_url,
                description=f"SQS DLQ URL for {dlq_name}",
            )
        return
