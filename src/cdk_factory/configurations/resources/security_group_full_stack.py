"""
SecurityGroupFullStackConfig - supports Security Group settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional


class SecurityGroupFullStackConfig:
    """
    Security Group Configuration - supports Security Group settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        self.__config = config or {}
        self.__deployment = config

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

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self.__config.get("ssm", {})

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter imports for the Security Group"""
        return self.ssm.get("imports", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports for the Security Group"""
        return self.ssm.get("exports", {})

    @property
    def security_groups(self) -> List[Dict[str, Any]]:
        """List of security groups to create"""
        return self.__config.get("security_groups", [])
