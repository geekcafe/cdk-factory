"""
ECS Cluster Stack Module (Standardized SSM Version)

Provides a dedicated stack for creating and configuring ECS clusters
with proper configurability, explicit resource management, and standardized SSM integration.
"""

import logging
from typing import Optional, Dict, Any

from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
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
        
        # Load ECS cluster configuration with full stack config for SSM access
        ecs_cluster_dict = stack_config.dictionary.get("ecs_cluster", {})
        # Merge SSM config from root level into ECS config for VPC resolution
        if "ssm" in stack_config.dictionary:
            ecs_cluster_dict["ssm"] = stack_config.dictionary["ssm"]
        
        self.ecs_config: EcsClusterConfig = EcsClusterConfig(ecs_cluster_dict)
        
        cluster_name = deployment.build_resource_name(self.ecs_config.name)
        
        logger.info(f"Creating ECS Cluster stack: {cluster_name}")
        
        # Setup standardized SSM integration
        self.setup_ssm_integration(
            scope=self,
            config=self.ecs_config,
            resource_type="ecs_cluster",
            resource_name=cluster_name,
            deployment=deployment,
            workload=workload
        )

        # Process SSM imports using standardized method
        self.process_ssm_imports()
        
        # Create the ECS cluster
        self._create_ecs_cluster()
        
        # Create IAM roles if needed
        self._create_iam_roles()
        
        # Create capacity providers if configured
        self._create_capacity_providers()
        
        # Export cluster information
        self._export_cluster_info()
        
        # Export SSM parameters
        logger.info("Starting SSM parameter export for ECS cluster")
        self._export_ssm_parameters()
        logger.info("Completed SSM parameter export for ECS cluster")
        
        logger.info(f"ECS Cluster stack created: {cluster_name}")

    def _create_ecs_cluster(self):
        """Create the ECS cluster with explicit configuration."""
        logger.info(f"Creating ECS cluster: {self.ecs_config.name}")

        # Build cluster settings
        cluster_settings = []

        # Add container insights if enabled
        if self.ecs_config.container_insights:
            cluster_settings.append({"name": "containerInsightsV2", "value": "enabled"})

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
            container_insights_v2=ecs.ContainerInsights.ENABLED if self.ecs_config.container_insights else ecs.ContainerInsights.DISABLED,
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
        Get VPC using the centralized VPC provider mixin.
        """
        
        # Use the stack_config (not ecs_config) to ensure SSM imports are available
        return self.resolve_vpc(
            config=self.ecs_config,
            deployment=self.deployment,
            workload=self.workload
        )

    def _create_iam_roles(self):
        """Create IAM roles for the ECS cluster if configured."""
        logger.info(f"create_instance_role setting: {self.ecs_config.create_instance_role}")
        
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
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
            role_name=f"{self.ecs_config.name}-ecs-instance-role",
        )

        logger.info(f"Created ECS instance role: {self.instance_role.role_name}")

        # Create instance profile
        self.instance_profile = iam.CfnInstanceProfile(
            self,
            "ECSInstanceProfile",
            instance_profile_name=f"{self.ecs_config.name}-ecs-instance-profile",
            roles=[self.instance_role.role_name],
        )

        logger.info(f"Created ECS instance profile: {self.instance_profile.instance_profile_name}")

        logger.info("ECS instance role and profile created")

    def _create_capacity_providers(self):
        """Create ECS capacity providers for ASG-based auto-scaling."""
        if not self.ecs_config.capacity_providers:
            logger.info("No capacity providers configured - skipping")
            return
        
        logger.info(f"Creating {len(self.ecs_config.capacity_providers)} capacity provider(s)")
        
        capacity_provider_names = []
        
        for cp_config in self.ecs_config.capacity_providers:
            cp_name = cp_config.get("name")
            asg_arn = cp_config.get("auto_scaling_group_arn")
            
            if not cp_name or not asg_arn:
                logger.warning(f"Skipping capacity provider - missing name or ASG ARN: {cp_config}")
                continue
            
            # Resolve SSM parameter if ASG ARN is an SSM reference            
            resolved_asg_arn = self.resolve_ssm_value(scope=self, value=asg_arn, unique_id=asg_arn)
            
            # Extract configuration with defaults
            target_capacity = cp_config.get("target_capacity", 100)
            min_scaling_step = cp_config.get("minimum_scaling_step_size", 1)
            max_scaling_step = cp_config.get("maximum_scaling_step_size", 10)
            instance_warmup = cp_config.get("instance_warmup_period", 300)
            
            logger.info(
                f"Creating capacity provider '{cp_name}' with target_capacity={target_capacity}%, "
                f"scaling_steps={min_scaling_step}-{max_scaling_step}, warmup={instance_warmup}s"
            )
            
            # Create the capacity provider
            capacity_provider = ecs.CfnCapacityProvider(
                self,
                f"CapacityProvider-{cp_name}",
                name=cp_name,
                auto_scaling_group_provider=ecs.CfnCapacityProvider.AutoScalingGroupProviderProperty(
                    auto_scaling_group_arn=resolved_asg_arn,
                    managed_scaling=ecs.CfnCapacityProvider.ManagedScalingProperty(
                        status="ENABLED",
                        target_capacity=target_capacity,
                        minimum_scaling_step_size=min_scaling_step,
                        maximum_scaling_step_size=max_scaling_step,
                        instance_warmup_period=instance_warmup
                    ),
                    managed_termination_protection="ENABLED"
                )
            )
            
            capacity_provider_names.append(capacity_provider.ref)
            logger.info(f"Created capacity provider: {cp_name}")
        
        # Associate capacity providers with cluster if any were created
        if capacity_provider_names and self.ecs_config.default_capacity_provider_strategy:
            logger.info(f"Associating {len(capacity_provider_names)} capacity provider(s) with cluster")
            
            # Build capacity provider strategy
            strategies = []
            for strategy_config in self.ecs_config.default_capacity_provider_strategy:
                strategy = ecs.CfnClusterCapacityProviderAssociations.CapacityProviderStrategyProperty(
                    capacity_provider=strategy_config.get("capacity_provider"),
                    weight=strategy_config.get("weight", 1),
                    base=strategy_config.get("base", 0)
                )
                strategies.append(strategy)
            
            # Associate with cluster
            ecs.CfnClusterCapacityProviderAssociations(
                self,
                "ClusterCapacityProviderAssociations",
                cluster=self.ecs_cluster.cluster_name,
                capacity_providers=capacity_provider_names,
                default_capacity_provider_strategy=strategies
            )
            
            logger.info(f"Capacity providers associated with cluster: {', '.join(capacity_provider_names)}")
        elif capacity_provider_names:
            logger.warning(
                "Capacity providers created but no default strategy defined. "
                "Services must explicitly specify capacity provider strategy."
            )

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
        logger.info("=== Starting SSM Parameter Export ===")
        
        if not self.ecs_cluster:
            logger.warning("No ECS cluster to export")
            return

        logger.info(f"ECS cluster found: {self.ecs_cluster.cluster_name}")
        logger.info(f"SSM exports configured: {self.ssm_config.get('exports', {})}")

        # Prepare resource values for export
        resource_values = {
            "cluster_name": self.ecs_cluster.cluster_name,
            "cluster_arn": self.ecs_cluster.cluster_arn,
        }
        
        # Add instance role ARN if created
        if self.instance_role:
            resource_values["instance_role_arn"] = self.instance_role.role_arn
            logger.info(f"Instance role ARN added: {self.instance_role.role_name}")
        else:
            logger.info("No instance role to export")
        
        # Add security group ID if available
        if hasattr(self.ecs_cluster, 'connections') and self.ecs_cluster.connections:
            security_groups = self.ecs_cluster.connections.security_groups
            if security_groups:
                resource_values["security_group_id"] = security_groups[0].security_group_id
                logger.info(f"Security group ID added: {security_groups[0].security_group_id}")
        
        # Add instance profile ARN if created
        if self.instance_profile:
            resource_values["instance_profile_arn"] = self.instance_profile.attr_arn
            logger.info(f"Instance profile ARN added: {self.instance_profile.instance_profile_name}")

        # Export using standardized SSM mixin
        logger.info(f"Resource values available for export: {list(resource_values.keys())}")
        for key, value in resource_values.items():
            logger.info(f"  {key}: {value}")
            
        try:
            exported_params = self.export_ssm_parameters(resource_values)
            logger.info(f"Successfully exported SSM parameters: {exported_params}")
        except Exception as e:
            logger.error(f"Failed to export SSM parameters: {str(e)}")
            raise

    # Backward compatibility alias
EcsClusterStackStandardized = EcsClusterStack
