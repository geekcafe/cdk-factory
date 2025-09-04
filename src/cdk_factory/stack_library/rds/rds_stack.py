"""
RDS Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ec2 as ec2
from aws_cdk import Duration
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.rds import RdsConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="RdsStack")


@register_stack("rds_library_module")
@register_stack("rds_stack")
class RdsStack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS RDS.
    Supports creating RDS instances with customizable configurations.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.rds_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.db_instance = None
        self.security_groups = []
        self._vpc = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the RDS stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the RDS stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.rds_config = RdsConfig(stack_config.dictionary.get("rds", {}), deployment)
        db_name = deployment.build_resource_name(self.rds_config.name)

        # Get VPC and security groups
        self.security_groups = self._get_security_groups()

        # Create RDS instance or import existing
        if self.rds_config.existing_instance_id:
            self.db_instance = self._import_existing_db(db_name)
        else:
            self.db_instance = self._create_db_instance(db_name)

        # Add outputs
        self._add_outputs(db_name)

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the RDS instance"""
        # Assuming VPC is provided by the workload
        if self._vpc:
            return self._vpc
        if self.rds_config.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.rds_config.vpc_id)
        if self.workload.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.workload.vpc_id)
        else:
            # Use default VPC if not provided
            raise ValueError(
                "VPC is not defined in the configuration.  "
                "You can provide it a the rds.vpc_id in the configuration "
                "or a top level workload.vpc_id in the workload configuration."
            )
        return self._vpc

    def _get_security_groups(self) -> List[ec2.ISecurityGroup]:
        """Get security groups for the RDS instance"""
        security_groups = []
        for sg_id in self.rds_config.security_group_ids:
            security_groups.append(
                ec2.SecurityGroup.from_security_group_id(
                    self, f"SecurityGroup-{sg_id}", sg_id
                )
            )
        return security_groups

    def _create_db_instance(self, db_name: str) -> rds.DatabaseInstance:
        """Create a new RDS instance"""
        # Configure subnet selection
        # Use private subnets for database placement
        subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)

        # Configure engine
        engine_version = None
        if self.rds_config.engine.lower() == "postgres":
            engine_version = rds.PostgresEngineVersion.of(
                self.rds_config.engine_version, self.rds_config.engine_version
            )
            engine = rds.DatabaseInstanceEngine.postgres(version=engine_version)
        elif self.rds_config.engine.lower() == "mysql":
            engine_version = rds.MysqlEngineVersion.of(
                self.rds_config.engine_version, self.rds_config.engine_version
            )
            engine = rds.DatabaseInstanceEngine.mysql(version=engine_version)
        elif self.rds_config.engine.lower() == "mariadb":
            engine_version = rds.MariaDbEngineVersion.of(
                self.rds_config.engine_version, self.rds_config.engine_version
            )
            engine = rds.DatabaseInstanceEngine.mariadb(version=engine_version)
        else:
            raise ValueError(f"Unsupported database engine: {self.rds_config.engine}")

        # Configure instance type
        instance_class = self.rds_config.instance_class
        instance_type = ec2.InstanceType(instance_class)

        # Configure removal policy
        removal_policy = None
        if self.rds_config.removal_policy.lower() == "destroy":
            removal_policy = cdk.RemovalPolicy.DESTROY
        elif self.rds_config.removal_policy.lower() == "snapshot":
            removal_policy = cdk.RemovalPolicy.SNAPSHOT
        elif self.rds_config.removal_policy.lower() == "retain":
            removal_policy = cdk.RemovalPolicy.RETAIN

        # Create the database instance
        db_instance = rds.DatabaseInstance(
            self,
            db_name,
            engine=engine,
            vpc=self.vpc,
            vpc_subnets=subnets,
            instance_type=instance_type,
            credentials=rds.Credentials.from_generated_secret(
                username=self.rds_config.username,
                secret_name=self.rds_config.secret_name,
            ),
            database_name=self.rds_config.database_name,
            multi_az=self.rds_config.multi_az,
            allocated_storage=self.rds_config.allocated_storage,
            storage_encrypted=self.rds_config.storage_encrypted,
            security_groups=self.security_groups if self.security_groups else None,
            deletion_protection=self.rds_config.deletion_protection,
            backup_retention=Duration.days(self.rds_config.backup_retention),
            cloudwatch_logs_exports=self.rds_config.cloudwatch_logs_exports,
            enable_performance_insights=self.rds_config.enable_performance_insights,
            removal_policy=removal_policy,
        )

        # Add tags
        for key, value in self.rds_config.tags.items():
            cdk.Tags.of(db_instance).add(key, value)

        return db_instance

    def _import_existing_db(self, db_name: str) -> rds.IDatabaseInstance:
        """Import an existing RDS instance"""
        return rds.DatabaseInstance.from_database_instance_attributes(
            self,
            db_name,
            instance_identifier=self.rds_config.existing_instance_id,
            instance_endpoint_address=f"{self.rds_config.existing_instance_id}.{self.region}.rds.amazonaws.com",
            port=5432,  # Default port, could be configurable
            security_groups=self.security_groups,
        )

    def _add_outputs(self, db_name: str) -> None:
        """Add CloudFormation outputs for the RDS instance"""
        if self.db_instance:
            # Database endpoint
            cdk.CfnOutput(
                self,
                f"{db_name}-endpoint",
                value=self.db_instance.db_instance_endpoint_address,
                export_name=f"{self.deployment.build_resource_name(db_name)}-endpoint",
            )

            # Database port
            cdk.CfnOutput(
                self,
                f"{db_name}-port",
                value=self.db_instance.db_instance_endpoint_port,
                export_name=f"{self.deployment.build_resource_name(db_name)}-port",
            )

            # Secret ARN (if available)
            if hasattr(self.db_instance, "secret") and self.db_instance.secret:
                cdk.CfnOutput(
                    self,
                    f"{db_name}-secret-arn",
                    value=self.db_instance.secret.secret_arn,
                    export_name=f"{self.deployment.build_resource_name(db_name)}-secret-arn",
                )
