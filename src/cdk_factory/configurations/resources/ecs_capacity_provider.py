"""Configuration for ECS Capacity Provider resources."""

from typing import Any, Dict, List

from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class EcsCapacityProviderConfig(EnhancedBaseConfig):
    """Configuration for ECS Capacity Provider stack."""

    def __init__(self, config: dict) -> None:
        """Initialize the ECS Capacity Provider configuration."""
        super().__init__(
            config or {},
            resource_type="capacity-provider",
            resource_name=config.get("name", "capacity-provider") if config else "capacity-provider"
        )
        self.__config = config or {}

    @property
    def name(self) -> str:
        """Capacity provider name"""
        return self.__config.get("name", "")

    @property
    def cluster_name(self) -> str:
        """ECS cluster name to associate with"""
        return self.__config.get("cluster_name", "")

    @property
    def auto_scaling_group_arn(self) -> str:
        """
        ARN or name of the Auto Scaling Group to manage.
        ECS accepts either the full ARN or just the ASG name.
        Can be a direct value or SSM parameter reference like {{ssm:/path/to/name}}
        
        Note: CloudFormation doesn't expose the ASG ARN attribute, so typically
        you'll use the ASG name here.
        """
        return self.__config.get("auto_scaling_group_arn", "")

    @property
    def target_capacity(self) -> int:
        """
        Target cluster capacity utilization percentage.
        Range: 1-100
        Default: 100
        Higher = more efficient, lower = more buffer capacity
        """
        return self.__config.get("target_capacity", 100)

    @property
    def minimum_scaling_step_size(self) -> int:
        """
        Minimum number of instances to add/remove per scaling event.
        Range: 1-10000
        Default: 1
        """
        return self.__config.get("minimum_scaling_step_size", 1)

    @property
    def maximum_scaling_step_size(self) -> int:
        """
        Maximum number of instances to add/remove per scaling event.
        Range: 1-10000
        Default: 10
        """
        return self.__config.get("maximum_scaling_step_size", 10)

    @property
    def instance_warmup_period(self) -> int:
        """
        Seconds to wait after instance launch before considering it ready.
        Default: 300 (5 minutes)
        """
        return self.__config.get("instance_warmup_period", 300)

    @property
    def managed_termination_protection(self) -> str:
        """
        Enable managed termination protection.
        Valid values: ENABLED, DISABLED
        Default: ENABLED
        """
        return self.__config.get("managed_termination_protection", "ENABLED")

    @property
    def capacity_provider_strategy(self) -> List[Dict[str, Any]]:
        """
        Capacity provider strategy to set as cluster default.
        Each strategy should have:
        - capacity_provider: Name of this provider
        - weight: Relative weight (default: 1)
        - base: Number of tasks to run before distributing (default: 0)
        """
        return self.__config.get("capacity_provider_strategy", [])

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self.__config.get("ssm", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports"""
        return self.ssm.get("exports", {})

    @property
    def ssm_imports(self) -> Dict[str, Any]:
        """SSM parameter imports"""
        return self.ssm.get("imports", {})
