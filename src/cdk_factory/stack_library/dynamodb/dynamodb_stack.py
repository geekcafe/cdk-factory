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
from aws_lambda_powertools import Logger
from cdk_factory.stack.stack_module_registry import register_stack
from typing import List, Dict, Any, Optional

logger = Logger(service="DynamoDBStack")


@register_stack("dynamodb_library_module")
class DynamoDBStack(IStack):
    """
    Reusable stack for AWS DynamoDB tables.
    Supports all major DynamoDB table parameters.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.db_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.table = None

    def build(self, stack_config, deployment, workload) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig

        self.db_config = DynamoDBConfig(
            stack_config.dictionary.get("dynamodb", {}),
            deployment
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
            self,
            id=f"{table_name}-imported",
            table_name=table_name
        )

    def _create_new_table(self) -> None:
        """Create a new DynamoDB table with the specified configuration"""
        table_name = self.db_config.name
        
        # Define table properties
        props = {
            "table_name": table_name,
            "partition_key": dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
            "deletion_protection": self.db_config.enable_delete_protection,
            "point_in_time_recovery": self.db_config.point_in_time_recovery,
        }
        
        # Add replica regions if specified
        replica_regions = self.db_config.replica_regions
        if replica_regions:
            props["replication_regions"] = replica_regions
            logger.info(f"Configuring table {table_name} with replicas in: {', '.join(replica_regions)}")
        
        # Create the table
        logger.info(f"Creating DynamoDB table: {table_name}")
        self.table = dynamodb.Table(
            self,
            id=table_name,
            **props
        )
        
        # Add GSIs if configured
        self._configure_gsis()
        
    def _configure_gsis(self) -> None:
        """Configure Global Secondary Indexes if specified in the config"""
        if not self.table or self.db_config.use_existing:
            return
            
        # In a real implementation, you would read GSI configurations from the config
        # For now, we'll just log the GSI count from the config
        gsi_count = self.db_config.gsi_count
        if gsi_count > 0:
            logger.info(f"Table {self.db_config.name} is configured to support up to {gsi_count} GSIs")
            
        # Example of how to add a GSI (commented out as it would need actual config data)
        # self.table.add_global_secondary_index(
        #     index_name="example-gsi",
        #     partition_key=dynamodb.Attribute(
        #         name="gsi_pk",
        #         type=dynamodb.AttributeType.STRING
        #     ),
        #     sort_key=dynamodb.Attribute(
        #         name="gsi_sk",
        #         type=dynamodb.AttributeType.STRING
        #     )
        # )