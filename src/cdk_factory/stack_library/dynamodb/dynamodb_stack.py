"""
DynamoDB Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from pathlib import Path
import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from aws_lambda_powertools import Logger
from cdk_factory.stack.stack_module_registry import register_stack
from typing import List, Dict, Any, Optional
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig

logger = Logger(service="DynamoDBStack")


@register_stack("dynamodb_stack")
@register_stack("dynamodb_library_module")
class DynamoDBStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for AWS DynamoDB tables.
    Supports all major DynamoDB table parameters.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.db_config: DynamoDBConfig | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.table: dynamodb.TableV2 | None = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.db_config = DynamoDBConfig(
            stack_config.dictionary.get("dynamodb", {}), deployment
        )

        # Determine if we're using an existing table or creating a new one
        if self.db_config.use_existing:
            self._import_existing_table()
        else:
            self._create_new_table()

    def _import_existing_table(self) -> None:
        """Import an existing DynamoDB table"""
        table_name = self.db_config.name

        logger.info(f"Importing existing DynamoDB table: {table_name}")

        self.table = dynamodb.Table.from_table_name(
            self, id=f"{table_name}-imported", table_name=table_name
        )

    def _create_new_table(self) -> None:
        """Create a new DynamoDB table with the specified configuration"""
        table_name = self.db_config.name

        # Define table properties
        removal_policy = (
            cdk.RemovalPolicy.DESTROY
            if "dev" in self.deployment.environment
            else cdk.RemovalPolicy.RETAIN
        )

        if self.db_config.enable_delete_protection:
            removal_policy = cdk.RemovalPolicy.RETAIN

        props = {
            "table_name": table_name,
            "partition_key": dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING
            ),
            "billing": dynamodb.Billing.on_demand(),
            "deletion_protection": self.db_config.enable_delete_protection,
            "point_in_time_recovery": self.db_config.point_in_time_recovery,
            "removal_policy": removal_policy,
        }

        # Create the table
        logger.info(f"Creating DynamoDB table: {table_name}")
        self.table = dynamodb.TableV2(self, id=table_name, **props)

        # Add GSIs if configured
        self._configure_gsi()
        # add replicas if configured
        self._configure_replicas()

        # Export SSM parameters
        self._export_ssm_parameters()

    def _configure_replicas(self) -> None:
        """Configure replicas if specified in the config"""
        if not self.table or self.db_config.use_existing:
            return

        replica_regions = self.db_config.replica_regions
        if replica_regions:
            logger.info(
                f"Configuring table {self.db_config.name} with replicas in: {', '.join(replica_regions)}"
            )
            for region in replica_regions:
                self.table.add_replica(region=region)

    def _configure_gsi(self) -> None:
        """Configure Global Secondary Indexes if specified in the config"""
        if not self.table or self.db_config.use_existing:
            return

        # TODO: allow for custom GSI configuration
        gsi_count = self.db_config.gsi_count
        if gsi_count > 0:
            logger.info(
                f"Table {self.db_config.name} is configured to support up to {gsi_count} GSIs"
            )

        for i in range(gsi_count):
            self.table.add_global_secondary_index(
                index_name=f"gsi{i}",
                partition_key=dynamodb.Attribute(
                    name=f"gsi{i}_pk", type=dynamodb.AttributeType.STRING
                ),
                sort_key=dynamodb.Attribute(
                    name=f"gsi{i}_sk", type=dynamodb.AttributeType.STRING
                ),
                projection_type=dynamodb.ProjectionType.ALL,
            )

    def _export_ssm_parameters(self):
        """Export DynamoDB resources to SSM using enhanced SSM parameter mixin"""
        if not self.table:
            return

        # Setup enhanced SSM integration with proper resource type and name
        # Use "app-table" as resource identifier for SSM paths, not the full table name

        self.setup_ssm_integration(
            scope=self,
            config=self.stack_config.dictionary.get("dynamodb", {}),
            resource_type="dynamodb",
            resource_name="app-table",
        )

        # Prepare resource values for export
        resource_values = {
            "table_name": self.table.table_name,
            "table_arn": self.table.table_arn,
            "table_stream_arn": (
                self.table.table_stream_arn
                if hasattr(self.table, "table_stream_arn")
                else None
            ),
        }

        # Add GSI names if available
        if hasattr(self, "_gsi_names") and self._gsi_names:
            resource_values["gsi_names"] = ",".join(self._gsi_names)

        # Filter out None values
        resource_values = {k: v for k, v in resource_values.items() if v is not None}

        # Use enhanced SSM parameter export
        exported_params = self.export_ssm_parameters(resource_values)

        if exported_params:
            logger.info(f"Exported {len(exported_params)} DynamoDB parameters to SSM")
        else:
            logger.info("No SSM parameters configured for export")
