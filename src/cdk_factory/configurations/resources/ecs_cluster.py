"""
ECS Cluster Configuration

Defines the configuration schema for ECS cluster stacks.
"""

from typing import Optional, Dict, Any, List


class EcsClusterConfig:
    """
    Configuration for an ECS cluster.
    
    This class defines all the configurable parameters for an ECS cluster,
    providing explicit control over cluster creation and settings.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config or {}
    
    @property
    def dictionary(self) -> Dict[str, Any]:
        """Access to the underlying configuration dictionary (for compatibility with SSM mixin)"""
        return self._config
    
    @property
    def name(self) -> str:
        """Name of the ECS cluster. Supports template variables like {{ENVIRONMENT}}-{{WORKLOAD_NAME}}-cluster"""
        return self._config.get("name", "cluster")
    
    @property
    def container_insights(self) -> bool:
        """Enable container insights for the cluster"""
        return self._config.get("container_insights", True)
    
    @property
    def cluster_settings(self) -> Optional[List[Dict[str, str]]]:
        """Additional cluster settings as name-value pairs"""
        return self._config.get("cluster_settings")
    
    @property
    def cloud_map_namespace(self) -> Optional[Dict[str, Any]]:
        """Cloud Map namespace configuration for service discovery"""
        return self._config.get("cloud_map_namespace")
    
    @property
    def execute_command_configuration(self) -> Optional[Dict[str, Any]]:
        """Execute command configuration for ECS"""
        return self._config.get("execute_command_configuration")
    
    @property
    def vpc_id(self) -> Optional[str]:
        """VPC ID where the cluster should be created"""
        return self._config.get("vpc_id")
    
    @property
    def ssm_vpc_id(self) -> Optional[str]:
        """SSM parameter path to import VPC ID"""
        return self._config.get("ssm_vpc_id")
    
    @property
    def create_instance_role(self) -> bool:
        """Whether to create an ECS instance role"""
        return self._config.get("create_instance_role", True)
    
    @property
    def instance_role_name(self) -> Optional[str]:
        """Custom name for the ECS instance role"""
        return self._config.get("instance_role_name")
    
    @property
    def instance_profile_name(self) -> Optional[str]:
        """Custom name for the ECS instance profile"""
        return self._config.get("instance_profile_name")
    
    @property
    def managed_policies(self) -> List[str]:
        """List of AWS managed policies to attach to the instance role"""
        return self._config.get("managed_policies", [
            "service-role/AmazonEC2ContainerServiceforEC2Role",
            "AmazonSSMManagedInstanceCore"
        ])
    
    @property
    def inline_policies(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Inline IAM policies to attach to the instance role"""
        return self._config.get("inline_policies")
    
    @property
    def export_ssm_parameters(self) -> bool:
        """Whether to export cluster information to SSM parameters"""
        return self._config.get("export_ssm_parameters", True)

    
    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self._config.get("ssm", {})
    
    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports"""
        return self.ssm.get("exports", {})

    @property
    def ssm_imports(self) -> Dict[str, Any]:
        """SSM parameter imports"""
        return self.ssm.get("imports", {})
