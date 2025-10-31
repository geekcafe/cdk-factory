"""
ECS Cluster Stack Module

Provides a dedicated stack for creating and configuring ECS clusters
with proper configurability and explicit resource management.
"""

import logging
from typing import Optional, Dict, Any, List

from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    RemovalPolicy,
    Stack,
    CfnOutput
)
from constructs import Construct

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin
from cdk_factory.configurations.resources.ecs_cluster import EcsClusterConfig


logger = logging.getLogger(__name__)


class EcsClusterStack(Stack, SsmParameterMixin):
    """
    A dedicated stack for creating and managing ECS clusters.
    
    This stack provides explicit configuration of ECS clusters including:
    - Cluster naming
    - Container insights
    - Cluster settings
    - SSM parameter exports
    - IAM role configurations
    """
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
        **kwargs
    ):
        """
        Initialize the ECS Cluster stack.
        
        Args:
            scope: The CDK construct scope
            construct_id: The construct ID
            stack_config: Stack configuration
            deployment: Deployment configuration
            workload: Workload configuration
        """
        super().__init__(scope, construct_id, **kwargs)
        
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        
        # Load ECS cluster configuration
        self.ecs_config: EcsClusterConfig = EcsClusterConfig(
            stack_config.dictionary.get("ecs_cluster", {})
        )
        
        logger.info(f"Creating ECS Cluster stack: {construct_id}")
        
        # Create the ECS cluster
        self._create_ecs_cluster()
        
        # Create IAM roles if needed
        self._create_iam_roles()
        
        # Export cluster information
        self._export_cluster_info()
        
        logger.info(f"ECS Cluster stack created: {construct_id}")
    
    def _create_ecs_cluster(self):
        """Create the ECS cluster with explicit configuration."""
        logger.info(f"Creating ECS cluster: {self.ecs_config.name}")
        
        # Build cluster settings
        cluster_settings = []
        
        # Add container insights if enabled
        if self.ecs_config.container_insights:
            cluster_settings.append({
                "name": "containerInsights",
                "value": "enabled"
            })
        
        # Add custom cluster settings
        if self.ecs_config.cluster_settings:
            cluster_settings.extend(self.ecs_config.cluster_settings)
        
        # Create the ECS cluster
        self.ecs_cluster = ecs.Cluster(
            self,
            "ECSCluster",
            cluster_name=self.ecs_config.name,
            vpc=self._get_vpc(),
            container_insights=self.ecs_config.container_insights,
            default_cloud_map_namespace=(
                self.ecs_config.cloud_map_namespace 
                if self.ecs_config.cloud_map_namespace else None
            ),
            execute_command_configuration=(
                self.ecs_config.execute_command_configuration 
                if self.ecs_config.execute_command_configuration else None
            )
        )
        
        logger.info(f"Created ECS cluster: {self.ecs_config.name}")
    
    def _create_iam_roles(self):
        """Create IAM roles for the ECS cluster if configured."""
        if not self.ecs_config.create_instance_role:
            return
        
        logger.info("Creating ECS instance role")
        
        # Create the instance role
        self.instance_role = iam.Role(
            self,
            "ECSInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=self.ecs_config.instance_role_name or f"{self.ecs_config.name}-instance-role"
        )
        
        # Add managed policies
        for policy in self.ecs_config.managed_policies:
            self.instance_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy)
            )
        
        # Add inline policies if provided
        if self.ecs_config.inline_policies:
            for policy_name, policy_document in self.ecs_config.inline_policies.items():
                self.instance_role.add_to_policy(
                    iam.PolicyStatement.from_json(policy_document)
                )
        
        # Create instance profile
        self.instance_profile = iam.CfnInstanceProfile(
            self,
            "ECSInstanceProfile",
            roles=[self.instance_role.role_name],
            instance_profile_name=self.ecs_config.instance_profile_name or f"{self.ecs_config.name}-instance-profile"
        )
        
        logger.info("Created ECS instance role and profile")
    
    def _get_vpc(self):
        """Get the VPC for the ECS cluster."""
        if self.ecs_config.vpc_id:
            # Import VPC by ID
            return ec2.Vpc.from_lookup(
                self,
                "VPC",
                vpc_id=self.ecs_config.vpc_id
            )
        elif self.ecs_config.ssm_vpc_id:
            # Import VPC from SSM
            vpc_id = self._import_ssm_parameter_value(
                self.ecs_config.ssm_vpc_id,
                required=True
            )
            return ec2.Vpc.from_lookup(
                self,
                "VPC", 
                vpc_id=vpc_id
            )
        else:
            # Use default VPC
            return ec2.Vpc.from_lookup(
                self,
                "VPC",
                is_default=True
            )
    
    def _export_cluster_info(self):
        """Export cluster information via SSM parameters and CloudFormation outputs."""
        logger.info("Exporting ECS cluster information")
        
        # Export cluster name
        self.export_ssm_parameter(
            f"/{self.deployment.name}/{self.workload.name}/ecs/cluster/name",
            self.ecs_config.name,
            "ECS Cluster Name"
        )
        
        # Export cluster ARN
        self.export_ssm_parameter(
            f"/{self.deployment.name}/{self.workload.name}/ecs/cluster/arn",
            self.ecs_cluster.cluster_arn,
            "ECS Cluster ARN"
        )
        
        # Export instance role ARN if created
        if hasattr(self, 'instance_role'):
            self.export_ssm_parameter(
                f"/{self.deployment.name}/{self.workload.name}/ecs/instance-role/arn",
                self.instance_role.role_arn,
                "ECS Instance Role ARN"
            )
        
        # CloudFormation outputs
        CfnOutput(
            self,
            "cluster-name",
            value=self.ecs_config.name,
            description=f"Name of the ECS cluster: {self.ecs_config.name}",
            export_name=f"{self.deployment.name}-ecs-cluster-name"
        )
        
        CfnOutput(
            self,
            "cluster-arn",
            value=self.ecs_cluster.cluster_arn,
            description=f"ARN of the ECS cluster: {self.ecs_config.name}",
            export_name=f"{self.deployment.name}-ecs-cluster-arn"
        )
        
        if hasattr(self, 'instance_role'):
            CfnOutput(
                self,
                "instance-role-arn",
                value=self.instance_role.role_arn,
                description=f"ARN of the ECS instance role: {self.ecs_config.name}",
                export_name=f"{self.deployment.name}-ecs-instance-role-arn"
            )
