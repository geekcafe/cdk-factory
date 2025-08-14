"""
VpcConfig - supports VPC settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional


class VpcConfig:
    """
    VPC Configuration - supports VPC settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """VPC name"""
        return self.__config.get("name", "vpc")

    @property
    def cidr(self) -> str:
        """VPC CIDR block"""
        return self.__config.get("cidr", "10.0.0.0/16")

    @property
    def max_azs(self) -> int:
        """Maximum number of Availability Zones"""
        return self.__config.get("max_azs", 3)

    @property
    def enable_dns_hostnames(self) -> bool:
        """Enable DNS hostnames"""
        return self.__config.get("enable_dns_hostnames", True)

    @property
    def enable_dns_support(self) -> bool:
        """Enable DNS support"""
        return self.__config.get("enable_dns_support", True)

    @property
    def public_subnets(self) -> bool:
        """Whether to create public subnets"""
        return self.__config.get("public_subnets", True)

    @property
    def private_subnets(self) -> bool:
        """Whether to create private subnets"""
        return self.__config.get("private_subnets", True)

    @property
    def isolated_subnets(self) -> bool:
        """Whether to create isolated subnets"""
        return self.__config.get("isolated_subnets", False)

    @property
    def public_subnet_mask(self) -> int:
        """CIDR mask for public subnets"""
        return self.__config.get("public_subnet_mask", 24)

    @property
    def private_subnet_mask(self) -> int:
        """CIDR mask for private subnets"""
        return self.__config.get("private_subnet_mask", 24)

    @property
    def isolated_subnet_mask(self) -> int:
        """CIDR mask for isolated subnets"""
        return self.__config.get("isolated_subnet_mask", 24)

    @property
    def nat_gateways(self) -> Dict[str, Any]:
        """NAT gateway configuration"""
        return self.__config.get("nat_gateways", {"count": 1})

    @property
    def enable_s3_endpoint(self) -> bool:
        """Whether to enable S3 gateway endpoint"""
        return self.__config.get("enable_s3_endpoint", True)

    @property
    def enable_interface_endpoints(self) -> bool:
        """Whether to enable VPC interface endpoints"""
        return self.__config.get("enable_interface_endpoints", False)

    @property
    def interface_endpoints(self) -> List[str]:
        """List of interface endpoints to create"""
        return self.__config.get("interface_endpoints", [])

    @property
    def flow_logs(self) -> Dict[str, Any]:
        """VPC flow logs configuration"""
        return self.__config.get("flow_logs", {})

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the VPC"""
        return self.__config.get("tags", {})
