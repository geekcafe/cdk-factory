"""
SecurityGroupConfig - supports Security Group settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class SecurityGroupConfig(EnhancedBaseConfig):
    """
    Security Group Configuration - supports Security Group settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict, deployment) -> None:
        super().__init__(config or {}, resource_type="security-group", resource_name=config.get("name", "security-group") if config else "security-group")
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """Security Group name"""
        return self.__config.get("name", "sg")

    @property
    def description(self) -> str:
        """Security Group description"""
        return self.__config.get("description", "Security Group")

    @property
    def vpc_id(self) -> Optional[str]:
        """VPC ID for the Security Group"""
        return self.__config.get("vpc_id")

    @property
    def allow_all_outbound(self) -> bool:
        """Whether to allow all outbound traffic"""
        return self.__config.get("allow_all_outbound", True)

    @property
    def ingress_rules(self) -> List[Dict[str, Any]]:
        """Ingress rules for the Security Group"""
        return self.__config.get("ingress_rules", [])

    @property
    def egress_rules(self) -> List[Dict[str, Any]]:
        """Egress rules for the Security Group"""
        return self.__config.get("egress_rules", [])

    @property
    def peer_security_groups(self) -> List[Dict[str, Any]]:
        """Peer security group rules"""
        return self.__config.get("peer_security_groups", [])

    @property
    def existing_security_group_id(self) -> Optional[str]:
        """Existing security group ID to import (if using existing)"""
        return self.__config.get("existing_security_group_id")

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the Security Group"""
        return self.__config.get("tags", {})
