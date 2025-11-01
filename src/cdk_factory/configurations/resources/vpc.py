"""
VpcConfig - supports VPC settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class VpcConfig(EnhancedBaseConfig):
    """
    VPC Configuration - supports VPC settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        super().__init__(config or {}, resource_type="vpc", resource_name=config.get("name", "vpc") if config else "vpc")
        self.__deployment = config

    @property
    def name(self) -> str:
        """VPC name"""
        return self.get("name", "vpc")

    @property
    def cidr(self) -> str:
        """VPC CIDR block"""
        return self.get("cidr", "10.0.0.0/16")

    @property
    def max_azs(self) -> int:
        """Maximum number of Availability Zones"""
        return self.get("max_azs", 3)

    @property
    def enable_dns_hostnames(self) -> bool:
        """Enable DNS hostnames"""
        return self.get("enable_dns_hostnames", True)

    @property
    def enable_dns_support(self) -> bool:
        """Enable DNS support"""
        return self.get("enable_dns_support", True)

    @property
    def public_subnets(self) -> bool:
        """Whether to create public subnets"""
        return self.get("public_subnets", True)

    @property
    def private_subnets(self) -> bool:
        """Whether to create private subnets"""
        return self.get("private_subnets", True)

    @property
    def isolated_subnets(self) -> bool:
        """Whether to create isolated subnets"""
        return self.get("isolated_subnets", False)

    @property
    def public_subnet_mask(self) -> int:
        """CIDR mask for public subnets"""
        return self.get("public_subnet_mask", 24)

    @property
    def private_subnet_mask(self) -> int:
        """CIDR mask for private subnets"""
        return self.get("private_subnet_mask", 24)

    @property
    def isolated_subnet_mask(self) -> int:
        """CIDR mask for isolated subnets"""
        return self.get("isolated_subnet_mask", 24)

    @property
    def nat_gateways(self) -> Dict[str, Any]:
        """NAT gateway configuration"""
        return self.get("nat_gateways", {"count": 1})

    @property
    def enable_s3_endpoint(self) -> bool:
        """Whether to enable S3 gateway endpoint"""
        return self.get("enable_s3_endpoint", True)

    @property
    def enable_interface_endpoints(self) -> bool:
        """Whether to enable VPC interface endpoints"""
        return self.get("enable_interface_endpoints", False)

    @property
    def interface_endpoints(self) -> List[str]:
        """List of interface endpoints to create"""
        return self.get("interface_endpoints", [])

    @property
    def flow_logs(self) -> Dict[str, Any]:
        """VPC flow logs configuration"""
        return self.get("flow_logs", {})

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the VPC"""
        return self.get("tags", {})

    @property
    def ssm_parameters(self) -> Dict[str, str]:
        """SSM parameter paths for VPC resources (legacy compatibility)"""
        return self.get("ssm_parameters", {})

    @property
    def public_subnet_name(self) -> str:
        """Custom name for public subnets"""
        return self.get("public_subnet_name", "public")

    @property
    def private_subnet_name(self) -> str:
        """Custom name for private subnets"""
        return self.get("private_subnet_name", "private")

    @property
    def isolated_subnet_name(self) -> str:
        """Custom name for isolated subnets"""
        return self.get("isolated_subnet_name", "isolated")

    @property
    def subnets(self) -> Dict[str, Any]:
        """Subnet configuration for the VPC"""
        return self.get("subnets", {
            "public": {
                "enabled": self.public_subnets,
                "cidr_mask": self.public_subnet_mask,
                "map_public_ip": True
            },
            "private": {
                "enabled": self.private_subnets,
                "cidr_mask": self.private_subnet_mask
            },
            "isolated": {
                "enabled": self.isolated_subnets,
                "cidr_mask": self.isolated_subnet_mask
            }
        })
