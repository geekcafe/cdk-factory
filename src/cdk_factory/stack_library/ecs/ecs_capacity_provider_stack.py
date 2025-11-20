"""ECS Capacity Provider Stack for associating capacity providers with clusters."""

import logging

from aws_cdk import Stack
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.ecs_capacity_provider import EcsCapacityProviderConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = logging.getLogger(__name__)


@register_stack("ecs_capacity_provider_stack")
class EcsCapacityProviderStack(IStack):
    """
    Stack for creating and associating ECS Capacity Providers with clusters.
    
    This stack should be deployed AFTER:
    - ECS Cluster stack
    - Auto Scaling Group stack
    
    It creates the capacity provider and associates it with the cluster,
    enabling automatic ASG scaling based on ECS task placement needs.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        stack_config: StackConfig = None,
        deployment: DeploymentConfig = None,
        workload: WorkloadConfig = None,
        **kwargs,
    ) -> None:
        """Initialize the ECS Capacity Provider stack."""
        super().__init__(scope, id, **kwargs)

        if stack_config and deployment and workload:
            self.build(
                stack_config=stack_config,
                deployment=deployment,
                workload=workload,
            )

    def build(
        self,
        *,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the ECS Capacity Provider stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Load capacity provider configuration
        cp_dict = stack_config.dictionary.get("capacity_provider", {})
        # Merge SSM config from root level
        if "ssm" in stack_config.dictionary:
            cp_dict["ssm"] = stack_config.dictionary["ssm"]

        self.cp_config: EcsCapacityProviderConfig = EcsCapacityProviderConfig(cp_dict)

        cp_name = deployment.build_resource_name(self.cp_config.name)

        logger.info(f"Creating ECS Capacity Provider stack: {cp_name}")

        # Setup standardized SSM integration
        self.setup_ssm_integration(
            scope=self,
            config=self.cp_config,
            resource_type="capacity_provider",
            resource_name=cp_name,
            deployment=deployment,
            workload=workload
        )

        # Process SSM imports
        self.process_ssm_imports()

        # Create the capacity provider
        self._create_capacity_provider()

        # Export SSM parameters
        logger.info("Starting SSM parameter export for capacity provider")
        self._export_ssm_parameters()
        logger.info("Completed SSM parameter export for capacity provider")

        logger.info(f"ECS Capacity Provider stack created: {cp_name}")

    def _create_capacity_provider(self):
        """Create the ECS capacity provider and associate with cluster."""
        cp_name = self.cp_config.name
        cluster_name = self.cp_config.cluster_name
        asg_identifier = self.cp_config.auto_scaling_group_arn  # Can be ARN or name

        if not cp_name or not cluster_name or not asg_identifier:
            raise ValueError(
                "Capacity provider requires name, cluster_name, and auto_scaling_group_arn (or name)"
            )

        # Resolve SSM parameter if ASG identifier is a reference
        resolved_asg_identifier = self.resolve_ssm_value(
            scope=self,
            value=asg_identifier,
            unique_id="asg-identifier"
        )

        logger.info(
            f"Creating capacity provider '{cp_name}' for cluster '{cluster_name}' "
            f"with target_capacity={self.cp_config.target_capacity}%"
        )

        # Create the capacity provider
        # Note: auto_scaling_group_arn accepts either the full ARN or just the ASG name
        self.capacity_provider = ecs.CfnCapacityProvider(
            self,
            "CapacityProvider",
            name=cp_name,
            auto_scaling_group_provider=ecs.CfnCapacityProvider.AutoScalingGroupProviderProperty(
                auto_scaling_group_arn=resolved_asg_identifier,
                managed_scaling=ecs.CfnCapacityProvider.ManagedScalingProperty(
                    status="ENABLED",
                    target_capacity=self.cp_config.target_capacity,
                    minimum_scaling_step_size=self.cp_config.minimum_scaling_step_size,
                    maximum_scaling_step_size=self.cp_config.maximum_scaling_step_size,
                    instance_warmup_period=self.cp_config.instance_warmup_period
                ),
                managed_termination_protection=self.cp_config.managed_termination_protection
            )
        )

        logger.info(f"Created capacity provider: {cp_name}")

        # Associate capacity provider with cluster
        self._associate_with_cluster()

    def _associate_with_cluster(self):
        """Associate the capacity provider with the ECS cluster."""
        cluster_name = self.cp_config.cluster_name

        # Build capacity provider strategy
        strategies = []
        if self.cp_config.capacity_provider_strategy:
            for strategy_config in self.cp_config.capacity_provider_strategy:
                strategy = ecs.CfnClusterCapacityProviderAssociations.CapacityProviderStrategyProperty(
                    capacity_provider=strategy_config.get("capacity_provider", self.cp_config.name),
                    weight=strategy_config.get("weight", 1),
                    base=strategy_config.get("base", 0)
                )
                strategies.append(strategy)
        else:
            # Default strategy: use this provider with weight 1
            strategies.append(
                ecs.CfnClusterCapacityProviderAssociations.CapacityProviderStrategyProperty(
                    capacity_provider=self.cp_config.name,
                    weight=1,
                    base=0
                )
            )

        logger.info(f"Associating capacity provider with cluster: {cluster_name}")

        # Associate with cluster
        self.cluster_association = ecs.CfnClusterCapacityProviderAssociations(
            self,
            "ClusterCapacityProviderAssociation",
            cluster=cluster_name,
            capacity_providers=[self.capacity_provider.ref],
            default_capacity_provider_strategy=strategies
        )

        logger.info(
            f"Capacity provider '{self.cp_config.name}' associated with cluster '{cluster_name}'"
        )

    def _export_ssm_parameters(self) -> None:
        """Export SSM parameters using standardized approach"""
        if not self.capacity_provider:
            logger.warning("No capacity provider to export")
            return

        # Prepare resource values for export
        # Note: Capacity providers don't have a separate ARN attribute
        # The .ref returns the ARN of the capacity provider
        resource_values = {
            "capacity_provider_name": self.cp_config.name,
            "capacity_provider_arn": self.capacity_provider.ref,
        }

        # Export using standardized SSM mixin
        exported_params = self.export_ssm_parameters(resource_values)

        logger.info(f"Exported SSM parameters: {exported_params}")
