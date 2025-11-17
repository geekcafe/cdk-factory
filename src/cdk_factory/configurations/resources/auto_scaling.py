"""
AutoScalingConfig - supports EC2 Auto Scaling Group settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class AutoScalingConfig(EnhancedBaseConfig):
    """
    Auto Scaling Group Configuration - supports EC2 Auto Scaling Group settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict, deployment) -> None:
        super().__init__(config or {}, resource_type="auto-scaling", resource_name=config.get("name", "auto-scaling") if config else "auto-scaling")
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """Auto Scaling Group name"""
        return self.__config.get("name", "asg")

    @property
    def instance_type(self) -> str:
        """EC2 instance type"""
        return self.__config.get("instance_type", "t3.small")

    @property
    def min_capacity(self) -> int:
        """Minimum capacity of the Auto Scaling Group"""
        return self.__config.get("min_capacity", 2)

    @property
    def max_capacity(self) -> int:
        """Maximum capacity of the Auto Scaling Group"""
        return self.__config.get("max_capacity", 6)

    @property
    def desired_capacity(self) -> int:
        """Desired capacity of the Auto Scaling Group"""
        return self.__config.get("desired_capacity", 2)

    @property
    def subnet_group_name(self) -> str:
        """Subnet group name for instance placement"""
        return self.__config.get("subnet_group_name", "app")

    @property
    def health_check_type(self) -> str:
        """Health check type (EC2 or ELB)"""
        return self.__config.get("health_check_type", "ELB")

    @property
    def health_check_grace_period(self) -> int:
        """Health check grace period in seconds"""
        return self.__config.get("health_check_grace_period", 300)

    @property
    def cooldown(self) -> int:
        """Cooldown period in seconds"""
        return self.__config.get("cooldown", 300)

    @property
    def termination_policies(self) -> List[str]:
        """Termination policies"""
        return self.__config.get("termination_policies", ["DEFAULT"])

    @property
    def update_policy(self) -> Optional[Dict[str, Any]]:
        """Update policy configuration"""
        return self.__config.get("update_policy")

    @property
    def instance_refresh(self) -> Optional[Dict[str, Any]]:
        """Instance refresh configuration for rolling updates"""
        return self.__config.get("instance_refresh")

    @property
    def user_data_commands(self) -> List[str]:
        """User data commands to run on instance launch"""
        return self.__config.get("user_data_commands", [])

    @property
    def security_group_ids(self) -> List[str]:
        """Security group IDs for the instances"""
        return self.__config.get("security_group_ids", [])

    @property
    def managed_policies(self) -> List[str]:
        """Managed policies to attach to the instance role"""
        return self.__config.get(
            "managed_policies",
            [
                "AmazonEC2ContainerRegistryReadOnly",
                "AmazonSSMManagedInstanceCore",
                "CloudWatchAgentServerPolicy",
            ],
        )

    @property
    def ami_id(self) -> Optional[str]:
        """Custom AMI ID (if not using latest Amazon Linux)"""
        return self.__config.get("ami_id")

    @property
    def ami_type(self) -> str:
        """AMI type if not using custom AMI"""
        return self.__config.get("ami_type", "amazon-linux-2023")

    @property
    def detailed_monitoring(self) -> bool:
        """Whether to enable detailed monitoring"""
        return self.__config.get("detailed_monitoring", True)

    @property
    def block_devices(self) -> List[Dict[str, Any]]:
        """Block device mappings"""
        return self.__config.get("block_devices", [])

    @property
    def scaling_policies(self) -> List[Dict[str, Any]]:
        """Scaling policies"""
        return self.__config.get("scaling_policies", [])

    @property
    def scheduled_actions(self) -> List[Dict[str, Any]]:
        """Scheduled actions"""
        return self.__config.get("scheduled_actions", [])

    @property
    def container_config(self) -> Dict[str, Any]:
        """Container configuration for Docker-based deployments"""
        return self.__config.get("container_config", {})

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the Auto Scaling Group"""
        return self.__config.get("tags", {})

    @property
    def vpc_id(self) -> Optional[str]:
        """VPC ID for the Auto Scaling Group"""
        return self.__config.get("vpc_id")

    @property
    def target_group_arns(self) -> List[str]:
        """Target group ARNs for the Auto Scaling Group"""
        return self.__config.get("target_group_arns", [])

    @property
    def user_data_scripts(self) -> List[Dict[str, Any]]:
        """
        User data scripts to inject from files.
        Each script should have:
        - type: 'file' or 'inline'
        - path: path to script file (if type is 'file')
        - content: script content (if type is 'inline')
        - variables: dict of variables for substitution
        """
        return self.__config.get("user_data_scripts", [])

    @property
    def iam_inline_policies(self) -> List[Dict[str, Any]]:
        """
        IAM inline policies to attach to the instance role.
        Each policy should have:
        - name: policy name
        - statements: list of IAM policy statements
        """
        return self.__config.get("iam_inline_policies", [])

    @property
    def key_name(self) -> Optional[str]:
        """EC2 key pair name for SSH access"""
        return self.__config.get("key_name")

    @property
    def ssm_imports(self) -> Dict[str, Any]:
        """SSM imports for the Auto Scaling Group"""
        return self.__config.get("ssm", {}).get("imports", {})

    @property
    def associate_public_ip_address(self) -> bool | None:
        """
        Whether instances should have a public IP addresses associated with them.         
        Default: - Use subnet settings
        """
        return self.__config.get("associate_public_ip_address")
