"""
SQS Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_sqs as sqs
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.sqs import SQS as SQSConfig
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

    def build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Build the SQS stack"""
        self._build(stack_config, deployment, workload)

    def _build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Internal build method for the SQS stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Load SQS configuration
        self.sqs_config = SQSConfig(stack_config.dictionary.get("sqs", {}))
        
        # Process each queue in the configuration
        for queue_config in self.sqs_config.queues:
            queue_name = deployment.build_resource_name(queue_config.name)
            
            # Create dead letter queue if specified
            if queue_config.add_dead_letter_queue:
                self._create_dead_letter_queue(queue_config, queue_name)
            
            # Create the main queue
            self._create_queue(queue_config, queue_name)
            
        # Add outputs
        self._add_outputs()

    def _create_queue(self, queue_config: SQSConfig, queue_name: str) -> sqs.Queue:
        """Create an SQS queue with the specified configuration"""
        # Determine if this is a FIFO queue
        is_fifo = queue_name.endswith(".fifo")
        
        # Configure queue properties
        queue_props = {
            "queue_name": queue_name,
            "visibility_timeout": cdk.Duration.seconds(queue_config.visibility_timeout_seconds) if queue_config.visibility_timeout_seconds > 0 else None,
            "retention_period": cdk.Duration.days(queue_config.message_retention_period_days) if queue_config.message_retention_period_days > 0 else None,
            "delivery_delay": cdk.Duration.seconds(queue_config.delay_seconds) if queue_config.delay_seconds > 0 else None,
            "fifo": is_fifo,
        }
        
        # Add dead letter queue if it exists
        dlq_id = f"{queue_name}-dlq"
        if dlq_id in self.dead_letter_queues:
            queue_props["dead_letter_queue"] = sqs.DeadLetterQueue(
                max_receive_count=queue_config.max_receive_count,
                queue=self.dead_letter_queues[dlq_id]
            )
        
        # Remove None values
        queue_props = {k: v for k, v in queue_props.items() if v is not None}
        
        # Create the queue
        queue = sqs.Queue(
            self,
            queue_config.resource_id or queue_name,
            **queue_props
        )
        
        # Store the queue for later reference
        self.queues[queue_name] = queue
        
        return queue

    def _create_dead_letter_queue(self, queue_config: SQSConfig, queue_name: str) -> sqs.Queue:
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
        dlq = sqs.Queue(
            self,
            dlq_name,
            **dlq_props
        )
        
        # Store the DLQ for later reference
        self.dead_letter_queues[dlq_name] = dlq
        
        return dlq

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for the SQS queues"""
        for queue_name, queue in self.queues.items():
            # Queue ARN
            cdk.CfnOutput(
                self,
                f"{queue_name}-arn",
                value=queue.queue_arn,
                export_name=f"{self.deployment.build_resource_name(queue_name)}-arn"
            )
            
            # Queue URL
            cdk.CfnOutput(
                self,
                f"{queue_name}-url",
                value=queue.queue_url,
                export_name=f"{self.deployment.build_resource_name(queue_name)}-url"
            )
        
        # Also add outputs for DLQs
        for dlq_name, dlq in self.dead_letter_queues.items():
            # DLQ ARN
            cdk.CfnOutput(
                self,
                f"{dlq_name}-arn",
                value=dlq.queue_arn,
                export_name=f"{self.deployment.build_resource_name(dlq_name)}-arn"
            )
            
            # DLQ URL
            cdk.CfnOutput(
                self,
                f"{dlq_name}-url",
                value=dlq.queue_url,
                export_name=f"{self.deployment.build_resource_name(dlq_name)}-url"
            )
