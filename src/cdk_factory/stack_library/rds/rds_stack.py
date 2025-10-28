"""
RDS Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ssm as ssm
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
        # SSM imported values
        self.ssm_imported_values: Dict[str, str] = {}

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

        # Process SSM imports first
        self._process_ssm_imports()

        # Get VPC and security groups
        self.security_groups = self._get_security_groups()

        # Create RDS instance or import existing
        if self.rds_config.existing_instance_id:
            self.db_instance = self._import_existing_db(db_name)
        else:
            self.db_instance = self._create_db_instance(db_name)

        # Add outputs
        self._add_outputs(db_name)
        
        # Export to SSM Parameter Store
        self._export_ssm_parameters(db_name)

    def _process_ssm_imports(self) -> None:
        """Process SSM imports from configuration"""
        ssm_imports = self.rds_config.ssm_imports
        
        if not ssm_imports:
            logger.debug("No SSM imports configured for RDS")
            return
        
        logger.info(f"Processing {len(ssm_imports)} SSM imports for RDS")
        
        for param_key, param_path in ssm_imports.items():
            try:
                if not param_path.startswith('/'):
                    param_path = f"/{param_path}"
                
                construct_id = f"ssm-import-{param_key}-{hash(param_path) % 10000}"
                param = ssm.StringParameter.from_string_parameter_name(
                    self, construct_id, param_path
                )
                
                self.ssm_imported_values[param_key] = param.string_value
                logger.info(f"Imported SSM parameter: {param_key} from {param_path}")
                
            except Exception as e:
                logger.error(f"Failed to import SSM parameter {param_key} from {param_path}: {e}")
                raise

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the RDS instance"""
        if self._vpc:
            return self._vpc
        
        # Check SSM imported values first (tokens from SSM parameters)
        if "vpc_id" in self.ssm_imported_values:
            vpc_id = self.ssm_imported_values["vpc_id"]
            
            # When using tokens, we can't provide subnet lists to from_vpc_attributes
            # because CDK validates subnet count against AZ count at synthesis time
            # We'll create a DB subnet group separately instead
            vpc_attrs = {
                "vpc_id": vpc_id,
                "availability_zones": ["us-east-1a", "us-east-1b"]
            }
            
            # Use from_vpc_attributes() for SSM tokens
            self._vpc = ec2.Vpc.from_vpc_attributes(self, "VPC", **vpc_attrs)
        elif self.rds_config.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.rds_config.vpc_id)
        elif self.workload.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.workload.vpc_id)
        else:
            raise ValueError(
                "VPC is not defined in the configuration.  "
                "You can provide it a the rds.vpc_id in the configuration "
                "or a top level workload.vpc_id in the workload configuration."
            )
        return self._vpc

    def _get_security_groups(self) -> List[ec2.ISecurityGroup]:
        """Get security groups for the RDS instance"""
        security_groups = []
        
        # Check SSM imports first for security group ID
        if "security_group_rds_id" in self.ssm_imported_values:
            sg_id = self.ssm_imported_values["security_group_rds_id"]
            security_groups.append(
                ec2.SecurityGroup.from_security_group_id(
                    self, "RDSSecurityGroup", sg_id
                )
            )
        
        # Also check config for any additional security group IDs
        for idx, sg_id in enumerate(self.rds_config.security_group_ids):
            security_groups.append(
                ec2.SecurityGroup.from_security_group_id(
                    self, f"SecurityGroup-{idx}", sg_id
                )
            )
        
        return security_groups

    def _create_db_instance(self, db_name: str) -> rds.DatabaseInstance:
        """Create a new RDS instance"""
        # Configure subnet group
        # If we have subnet IDs from SSM, create a DB subnet group explicitly
        db_subnet_group = None
        if "subnet_ids" in self.ssm_imported_values:
            subnet_ids_str = self.ssm_imported_values["subnet_ids"]
            # Split the comma-separated token into a list
            subnet_ids_list = cdk.Fn.split(",", subnet_ids_str)
            
            # Create DB subnet group with the token-based subnet list
            db_subnet_group = rds.CfnDBSubnetGroup(
                self,
                "DBSubnetGroup",
                db_subnet_group_description=f"Subnet group for {db_name}",
                subnet_ids=subnet_ids_list,
                db_subnet_group_name=f"{db_name}-subnet-group"
            )
        
        # Configure subnet selection for VPC (when not using SSM imports)
        subnets = None if db_subnet_group else ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)

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
        # Strip 'db.' prefix if present since ec2.InstanceType expects just the instance family/size
        instance_class = self.rds_config.instance_class
        instance_class_name = instance_class.replace("db.", "") if instance_class.startswith("db.") else instance_class
        instance_type = ec2.InstanceType(instance_class_name)

        # Configure removal policy
        removal_policy = None
        if self.rds_config.removal_policy.lower() == "destroy":
            removal_policy = cdk.RemovalPolicy.DESTROY
        elif self.rds_config.removal_policy.lower() == "snapshot":
            removal_policy = cdk.RemovalPolicy.SNAPSHOT
        elif self.rds_config.removal_policy.lower() == "retain":
            removal_policy = cdk.RemovalPolicy.RETAIN

        # Create the database instance
        # Build common properties
        db_props = {
            "engine": engine,
            "vpc": self.vpc,
            "instance_type": instance_type,
            "credentials": rds.Credentials.from_generated_secret(
                username=self.rds_config.username,
                secret_name=self.rds_config.secret_name,
            ),
            "database_name": self.rds_config.database_name,
            "multi_az": self.rds_config.multi_az,
            "allocated_storage": self.rds_config.allocated_storage,
            "storage_encrypted": self.rds_config.storage_encrypted,
            "security_groups": self.security_groups if self.security_groups else None,
            "deletion_protection": self.rds_config.deletion_protection,
            "backup_retention": Duration.days(self.rds_config.backup_retention),
            "cloudwatch_logs_exports": self.rds_config.cloudwatch_logs_exports,
            "enable_performance_insights": self.rds_config.enable_performance_insights,
            "removal_policy": removal_policy,
        }
        
        # Use either subnet group or vpc_subnets depending on what's available
        if db_subnet_group:
            db_props["subnet_group"] = rds.SubnetGroup.from_subnet_group_name(
                self, "ImportedSubnetGroup", db_subnet_group.ref
            )
        else:
            db_props["vpc_subnets"] = subnets
        
        db_instance = rds.DatabaseInstance(self, db_name, **db_props)

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

    def _export_ssm_parameters(self, db_name: str) -> None:
        """Export RDS connection info and credentials to SSM Parameter Store"""
        ssm_exports = self.rds_config.ssm_exports
        
        if not ssm_exports:
            logger.debug("No SSM exports configured for RDS")
            return
        
        logger.info(f"Exporting {len(ssm_exports)} SSM parameters for RDS")
        
        # Export database endpoint
        if "db_endpoint" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportDbEndpoint",
                value=self.db_instance.db_instance_endpoint_address,
                parameter_name=ssm_exports["db_endpoint"],
                description=f"RDS endpoint for {db_name}",
            )
            logger.info(f"Exported SSM parameter: {ssm_exports['db_endpoint']}")
        
        # Export database port
        if "db_port" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportDbPort",
                value=self.db_instance.db_instance_endpoint_port,
                parameter_name=ssm_exports["db_port"],
                description=f"RDS port for {db_name}",
            )
            logger.info(f"Exported SSM parameter: {ssm_exports['db_port']}")
        
        # Export database name
        if "db_name" in ssm_exports and self.rds_config.database_name:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportDbName",
                value=self.rds_config.database_name,
                parameter_name=ssm_exports["db_name"],
                description=f"RDS database name for {db_name}",
            )
            logger.info(f"Exported SSM parameter: {ssm_exports['db_name']}")
        
        # Export secret ARN (contains username and password)
        if "db_secret_arn" in ssm_exports:
            if hasattr(self.db_instance, "secret") and self.db_instance.secret:
                self.export_ssm_parameter(
                    scope=self,
                    id="SsmExportDbSecretArn",
                    value=self.db_instance.secret.secret_arn,
                    parameter_name=ssm_exports["db_secret_arn"],
                    description=f"Secrets Manager ARN containing RDS credentials for {db_name}",
                )
                logger.info(f"Exported SSM parameter: {ssm_exports['db_secret_arn']}")
            else:
                logger.warning(f"Secret not found for RDS instance {db_name}, skipping secret ARN export")
