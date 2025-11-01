"""
ECS Cluster Stack Module (Standardized SSM Version)

Provides a dedicated stack for creating and configuring ECS clusters
with proper configurability, explicit resource management, and standardized SSM integration.
"""

import logging
from typing import Optional, Dict, Any

from aws_cdk import (
    aws_ecs as ecs,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.interfaces.vpc_provider_mixin import VPCProviderMixin
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.configurations.resources.ecs_cluster import EcsClusterConfig
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.interfaces.istack import IStack

logger = logging.getLogger(__name__)


@register_stack("ecs_cluster_stack")
class EcsClusterStack(IStack, VPCProviderMixin, StandardizedSsmMixin):
    """
    A dedicated stack for creating and managing ECS clusters with standardized SSM integration.

    This stack provides explicit configuration of ECS clusters including:
    - Cluster naming
    - Container insights
    - Cluster settings
    - Standardized SSM parameter exports
    - IAM role configurations
    - Template variable resolution
    - Comprehensive validation
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        """
        Initialize the ECS Cluster stack.
        
        Args:
            scope: The CDK construct scope
            id: The construct ID
        """
        super().__init__(scope, id, **kwargs)
        
        self._initialize_vpc_cache()
        
        self.ecs_config: Optional[EcsClusterConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.ecs_cluster: Optional[ecs.Cluster] = None
        self.instance_role: Optional[iam.Role] = None
        self.instance_profile: Optional[iam.CfnInstanceProfile] = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the ECS Cluster stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the ECS Cluster stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        
        # Initialize VPC cache from mixin
        self._initialize_vpc_cache()
        
        # Load ECS cluster configuration
        self.ecs_config: EcsClusterConfig = EcsClusterConfig(
            stack_config.dictionary.get("ecs_cluster", {})
        )
        
        cluster_name = deployment.build_resource_name(self.ecs_config.name)
        
        logger.info(f"Creating ECS Cluster stack: {cluster_name}")
        
        # Setup standardized SSM integration
        self.setup_standardized_ssm_integration(
            scope=self,
            config=self.ecs_config,
            resource_type="ecs_cluster",
            resource_name=cluster_name,
            deployment=deployment,
            workload=workload
        )

        # Process SSM imports using standardized method
        self.process_standardized_ssm_imports()
        
        # Create the ECS cluster
        self._create_ecs_cluster()
        
        # Create IAM roles if needed
        self._create_iam_roles()
        
        # Export cluster information
        self._export_cluster_info()
        
        # Export SSM parameters
        self._export_ssm_parameters()
        
        logger.info(f"ECS Cluster stack created: {cluster_name}")

    def _create_ecs_cluster(self):
        """Create the ECS cluster with explicit configuration."""
        logger.info(f"Creating ECS cluster: {self.ecs_config.name}")

        # Build cluster settings
        cluster_settings = []

        # Add container insights if enabled
        if self.ecs_config.container_insights:
            cluster_settings.append({"name": "containerInsights", "value": "enabled"})

        # Add custom cluster settings
        if self.ecs_config.cluster_settings:
            cluster_settings.extend(self.ecs_config.cluster_settings)

        # Get VPC using standardized approach
        self.vpc = self._get_vpc()
        
        # Create the ECS cluster
        self.ecs_cluster = ecs.Cluster(
            self,
            "ECSCluster",
            cluster_name=self.ecs_config.name,
            vpc=self.vpc,
            container_insights=self.ecs_config.container_insights,
            default_cloud_map_namespace=(
                self.ecs_config.cloud_map_namespace
                if self.ecs_config.cloud_map_namespace
                else None
            ),
            execute_command_configuration=(
                self.ecs_config.execute_command_configuration
                if self.ecs_config.execute_command_configuration
                else None
            ),
        )

        logger.info(f"ECS cluster created: {self.ecs_config.name}")

    def _get_vpc(self):
        """
        Get VPC using standardized SSM approach.
        """
        # Primary method: Use standardized SSM imports
        ssm_imports = self.ecs_config.ssm_imports
        if "vpc_id" in ssm_imports:
            vpc_id = ssm_imports["vpc_id"]
            return ecs.Vpc.from_vpc_attributes(
                self, "ImportedVPC",
                vpc_id=vpc_id
            )
        
        # Fallback: Use VPC provider mixin (backward compatibility)
        elif hasattr(self, 'resolve_vpc'):
            return self.resolve_vpc(
                config=self.ecs_config,
                deployment=self.deployment,
                workload=self.workload
            )
        
        # Final fallback: Direct configuration
        elif hasattr(self.ecs_config, 'vpc_id') and self.ecs_config.vpc_id:
            return ecs.Vpc.from_vpc_attributes(
                self, "DirectVPC",
                vpc_id=self.ecs_config.vpc_id
            )
        
        else:
            raise ValueError("VPC not found in SSM imports, VPC provider, or direct configuration")

    def _create_iam_roles(self):
        """Create IAM roles for the ECS cluster if configured."""
        if not self.ecs_config.create_instance_role:
            logger.info("Skipping instance role creation (disabled in config)")
            return

        logger.info("Creating ECS instance role")

        # Create the instance role
        self.instance_role = iam.Role(
            self,
            "ECSInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonECSWorkerNodePolicy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
            role_name=f"{self.ecs_config.name}-ecs-instance-role",
        )

        # Create instance profile
        self.instance_profile = iam.CfnInstanceProfile(
            self,
            "ECSInstanceProfile",
            roles=[self.instance_role.role_name],
            instance_profile_name=f"{self.ecs_config.name}-ecs-instance-profile",
        )

        logger.info("ECS instance role and profile created")

    def _export_cluster_info(self):
        """Export cluster information as CloudFormation outputs."""
        if not self.ecs_cluster:
            return

        cluster_name = self.deployment.build_resource_name(self.ecs_config.name)

        # Export cluster name
        CfnOutput(
            self,
            f"{cluster_name}-ClusterName",
            value=self.ecs_cluster.cluster_name,
            description=f"ECS Cluster Name for {cluster_name}",
            export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-ecs-cluster-name",
        )

        # Export cluster ARN
        CfnOutput(
            self,
            f"{cluster_name}-ClusterArn",
            value=self.ecs_cluster.cluster_arn,
            description=f"ECS Cluster ARN for {cluster_name}",
            export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-ecs-cluster-arn",
        )

        # Export security group if available
        if hasattr(self.ecs_cluster, 'connections') and self.ecs_cluster.connections:
            security_groups = self.ecs_cluster.connections.security_groups
            if security_groups:
                CfnOutput(
                    self,
                    f"{cluster_name}-SecurityGroupId",
                    value=security_groups[0].security_group_id,
                    description=f"ECS Cluster Security Group ID for {cluster_name}",
                    export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-ecs-cluster-sg-id",
                )

        # Export instance profile if created
        if self.instance_profile:
            CfnOutput(
                self,
                f"{cluster_name}-InstanceProfileArn",
                value=self.instance_profile.attr_arn,
                description=f"ECS Instance Profile ARN for {cluster_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-ecs-instance-profile-arn",
            )

        logger.info("ECS cluster information exported as outputs")

    def _export_ssm_parameters(self) -> None:
        """Export SSM parameters using standardized approach"""
        if not self.ecs_cluster:
            logger.warning("No ECS cluster to export")
            return

        # Prepare resource values for export
        resource_values = {
            "ecs_cluster_name": self.ecs_cluster.cluster_name,
            "ecs_cluster_arn": self.ecs_cluster.cluster_arn,
        }
        
        # Add security group ID if available
        if hasattr(self.ecs_cluster, 'connections') and self.ecs_cluster.connections:
            security_groups = self.ecs_cluster.connections.security_groups
            if security_groups:
                resource_values["ecs_cluster_security_group_id"] = security_groups[0].security_group_id
        
        # Add instance profile ARN if created
        if self.instance_profile:
            resource_values["ecs_instance_profile_arn"] = self.instance_profile.attr_arn

        # Export using standardized SSM mixin
        exported_params = self.export_standardized_ssm_parameters(resource_values)
        
        logger.info(f"Exported SSM parameters: {exported_params}")

    # Backward compatibility methods
    def process_ssm_imports(self, config: Any, deployment: DeploymentConfig, resource_type: str = "resource") -> None:
        """Backward compatibility method for existing modules."""
        # Extract SSM configuration from old format
        if hasattr(config, 'ssm_imports'):
            # Convert old ssm_imports format to new format
            old_imports = config.ssm_imports
            new_imports = {}
            
            for key, value in old_imports.items():
                # Resolve template variables using old method
                if isinstance(value, str) and not value.startswith('/'):
                    value = f"/{deployment.environment}/{deployment.workload_name}/{value}"
                new_imports[key] = value
            
            # Update SSM config
            self.ssm_config = {"imports": new_imports}
        
        # Process imports using standardized method
        self.process_standardized_ssm_imports()


# Backward compatibility alias
EcsClusterStackStandardized = EcsClusterStack
