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

        # Validate: if use_existing is true, name must be provided
        if self.db_config.use_existing:
            raw_name = stack_config.dictionary.get("dynamodb", {}).get("name")
            if not raw_name:
                raise ValueError(
                    "DynamoDB import requires 'name' when 'use_existing' is true"
                )

        # Determine if we're using an existing table or creating a new one
        if self.db_config.use_existing:
            self._import_existing_table()
            self._export_ssm_parameters()
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
            "point_in_time_recovery_specification": dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self.db_config.point_in_time_recovery
            ),
            "removal_policy": removal_policy,
        }

        if self.db_config.ttl_attribute:
            props["time_to_live_attribute"] = self.db_config.ttl_attribute

        if self.db_config.stream_specification:
            stream_view_type = self._STREAM_VIEW_TYPE_MAP.get(
                self.db_config.stream_specification
            )
            if stream_view_type:
                props["dynamodb_stream"] = stream_view_type

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

    _ATTRIBUTE_TYPE_MAP = {
        "S": dynamodb.AttributeType.STRING,
        "N": dynamodb.AttributeType.NUMBER,
        "B": dynamodb.AttributeType.BINARY,
        "STRING": dynamodb.AttributeType.STRING,
        "NUMBER": dynamodb.AttributeType.NUMBER,
        "BINARY": dynamodb.AttributeType.BINARY,
    }

    _PROJECTION_TYPE_MAP = {
        "ALL": dynamodb.ProjectionType.ALL,
        "KEYS_ONLY": dynamodb.ProjectionType.KEYS_ONLY,
        "INCLUDE": dynamodb.ProjectionType.INCLUDE,
    }

    _STREAM_VIEW_TYPE_MAP = {
        "NEW_AND_OLD_IMAGES": dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
        "NEW_IMAGE": dynamodb.StreamViewType.NEW_IMAGE,
        "OLD_IMAGE": dynamodb.StreamViewType.OLD_IMAGE,
        "KEYS_ONLY": dynamodb.StreamViewType.KEYS_ONLY,
    }

    def _configure_gsi(self) -> None:
        """Configure Global Secondary Indexes.

        Supports two mutually exclusive modes:
        - Simple: ``gsi_count`` creates numbered GSIs (gsi0, gsi1, ...) with
          auto-named pk/sk attributes (gsi0_pk, gsi0_sk).
        - Named: ``global_secondary_indexes`` array with explicit index names,
          partition/sort keys, types, and projection settings.

        Raises ValueError if both are specified.
        """
        if not self.table or self.db_config.use_existing:
            return

        gsi_count = self.db_config.gsi_count
        named_gsis = self.db_config.global_secondary_indexes

        if gsi_count > 0 and named_gsis:
            raise ValueError(
                f"Table '{self.db_config.name}' specifies both 'gsi_count' ({gsi_count}) "
                "and 'global_secondary_indexes'. Use one or the other, not both."
            )

        if named_gsis:
            self._configure_named_gsis(named_gsis)
        elif gsi_count > 0:
            self._configure_auto_gsis(gsi_count)

    def _configure_auto_gsis(self, gsi_count: int) -> None:
        """Create numbered GSIs with auto-generated attribute names."""
        logger.info(
            f"Table {self.db_config.name}: creating {gsi_count} auto-numbered GSIs"
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

    def _configure_named_gsis(self, gsis: list) -> None:
        """Create GSIs from explicit definitions."""
        logger.info(f"Table {self.db_config.name}: creating {len(gsis)} named GSIs")
        for gsi in gsis:
            index_name = gsi.get("index_name")
            if not index_name:
                raise ValueError(
                    "Each entry in 'global_secondary_indexes' must have an 'index_name'"
                )

            pk_config = gsi.get("partition_key")
            if not pk_config or not pk_config.get("name"):
                raise ValueError(
                    f"GSI '{index_name}' must have a 'partition_key' with a 'name'"
                )

            pk_type = self._resolve_attribute_type(
                pk_config.get("type", "S"), index_name
            )
            partition_key = dynamodb.Attribute(name=pk_config["name"], type=pk_type)

            sort_key = None
            sk_config = gsi.get("sort_key")
            if sk_config and sk_config.get("name"):
                sk_type = self._resolve_attribute_type(
                    sk_config.get("type", "S"), index_name
                )
                sort_key = dynamodb.Attribute(name=sk_config["name"], type=sk_type)

            projection_str = gsi.get("projection", "ALL").upper()
            projection_type = self._PROJECTION_TYPE_MAP.get(projection_str)
            if not projection_type:
                raise ValueError(
                    f"GSI '{index_name}' has invalid projection '{projection_str}'. "
                    f"Valid values: {', '.join(self._PROJECTION_TYPE_MAP.keys())}"
                )

            kwargs = {
                "index_name": index_name,
                "partition_key": partition_key,
                "projection_type": projection_type,
            }
            if sort_key:
                kwargs["sort_key"] = sort_key
            if projection_type == dynamodb.ProjectionType.INCLUDE:
                non_key_attrs = gsi.get("non_key_attributes", [])
                if not non_key_attrs:
                    raise ValueError(
                        f"GSI '{index_name}' uses INCLUDE projection but "
                        "'non_key_attributes' is empty or missing"
                    )
                kwargs["non_key_attributes"] = non_key_attrs

            self.table.add_global_secondary_index(**kwargs)

    def _resolve_attribute_type(
        self, type_str: str, index_name: str
    ) -> dynamodb.AttributeType:
        """Map a type string (S/N/B) to a DynamoDB AttributeType."""
        attr_type = self._ATTRIBUTE_TYPE_MAP.get(type_str.upper())
        if not attr_type:
            raise ValueError(
                f"GSI '{index_name}' has invalid attribute type '{type_str}'. "
                f"Valid values: S (string), N (number), B (binary)"
            )
        return attr_type

    def _export_ssm_parameters(self):
        """Export DynamoDB resources to SSM using standardized top-level SSM config"""
        if not self.table:
            return

        if not self.stack_config.ssm_auto_export:
            logger.info("SSM auto-export is not enabled for DynamoDB stack")
            return

        # Prepare resource values for export
        resource_values = {
            "table_name": self.table.table_name,
            "table_arn": self.table.table_arn,
        }

        # Only include stream ARN when streams are explicitly enabled in config
        if self.db_config.streams_enabled:
            resource_values["table_stream_arn"] = self.table.table_stream_arn

        # Add GSI names if available
        if hasattr(self, "_gsi_names") and self._gsi_names:
            resource_values["gsi_names"] = ",".join(self._gsi_names)

        # Filter out None values
        resource_values = {k: v for k, v in resource_values.items() if v is not None}

        # Path pattern: /{namespace}/{attribute}
        # The namespace in config should include the resource context,
        # e.g. "my-app/prod/dynamodb/app"
        namespace = self.stack_config.ssm_namespace
        if not namespace:
            raise ValueError(
                f"Stack '{self.stack_config.name}': "
                f"'ssm.namespace' is required when 'ssm.auto_export' is true. "
                f"Add 'ssm.namespace' to your stack config."
            )

        prefix = f"/{namespace}"

        for export_key, export_value in resource_values.items():
            parameter_path = f"{prefix}/{export_key}"
            self.export_ssm_parameter(
                scope=self,
                id=f"{self.node.id}-{export_key}",
                value=export_value,
                parameter_name=parameter_path,
                description=f"DynamoDB {export_key}",
            )

        logger.info(f"Auto-exported {len(resource_values)} DynamoDB parameters to SSM")
