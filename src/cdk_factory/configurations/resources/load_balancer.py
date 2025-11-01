"""
LoadBalancerConfig - supports load balancer settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class LoadBalancerConfig(EnhancedBaseConfig):
    """
    Load Balancer Configuration - supports Application and Network Load Balancer settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict, deployment) -> None:
        super().__init__(config or {}, resource_type="load-balancer", resource_name=config.get("name", "load-balancer") if config else "load-balancer")
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """Load Balancer name"""
        return self.__config.get("name", "load-balancer")

    @property
    def type(self) -> str:
        """Load Balancer type (APPLICATION or NETWORK)"""
        lb_type = self.__config.get("type", "APPLICATION")
        return lb_type.upper()

    @property
    def internet_facing(self) -> bool:
        """Whether the load balancer is internet-facing"""
        return self.__config.get("internet_facing", True)

    @property
    def vpc_id(self) -> str:
        """VPC ID for the load balancer"""
        return self.__config.get("vpc_id")

    @property
    def subnets(self) -> List[str]:
        """Subnet IDs for the load balancer"""
        return self.__config.get("subnets", [])

    @property
    def security_groups(self) -> List[str]:
        """Security group IDs for the load balancer"""
        return self.__config.get("security_groups", [])

    @property
    def deletion_protection(self) -> bool:
        """Whether deletion protection is enabled"""
        return self.__config.get("deletion_protection", False)

    @property
    def idle_timeout(self) -> int:
        """Idle timeout in seconds (for Application Load Balancer)"""
        return self.__config.get("idle_timeout", 60)

    @property
    def http2_enabled(self) -> bool:
        """Whether HTTP/2 is enabled (for Application Load Balancer)"""
        return self.__config.get("http2_enabled", True)

    @property
    def listeners(self) -> List[Dict[str, Any]]:
        """Load balancer listeners configuration"""
        return self.__config.get("listeners", [])

    @property
    def target_groups(self) -> List[Dict[str, Any]]:
        """Target groups configuration"""
        return self.__config.get("target_groups", [])

    @property
    def health_check(self) -> Dict[str, Any]:
        """Health check configuration"""
        return self.__config.get("health_check", {})

    @property
    def ssl_policy(self) -> str:
        """SSL policy for HTTPS listeners"""
        return self.__config.get("ssl_policy", "RECOMMENDED_TLS")

    @property
    def certificate_arns(self) -> List[str]:
        """Certificate ARNs for HTTPS listeners"""
        return self.__config.get("certificate_arns", [])

    @property
    def hosted_zone(self) -> Dict[str, Any]:
        """Route53 hosted zone configuration"""
        return self.__config.get("hosted_zone", {})

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the load balancer"""
        return self.__config.get("tags", {})

    @property
    def vpc_id(self) -> str | None:
        """Returns the VPC ID for the Security Group"""
        return self.__config.get("vpc_id")

    @vpc_id.setter
    def vpc_id(self, value: str):
        """Sets the VPC ID for the Security Group"""
        self.__config["vpc_id"] = value

    @property
    def ssl_cert_arn(self) -> str | None:
        """Returns the SSL certificate ARN for the Load Balancer"""
        return self.__config.get("ssl_cert_arn")

    @property
    def ip_whitelist_enabled(self) -> bool:
        """Whether IP whitelisting is enabled"""
        return self.__config.get("ip_whitelist", {}).get("enabled", False)

    @property
    def ip_whitelist_cidrs(self) -> List[str]:
        """List of CIDR blocks to allow access"""
        return self.__config.get("ip_whitelist", {}).get("allowed_cidrs", [])

    @property
    def ip_whitelist_block_action(self) -> str:
        """Action to take for blocked IPs (fixed_response or redirect)"""
        return self.__config.get("ip_whitelist", {}).get(
            "block_action", "fixed_response"
        )

    @property
    def ip_whitelist_block_response(self) -> Dict[str, Any]:
        """Response configuration for blocked requests"""
        default_response = {
            "status_code": 403,
            "content_type": "text/plain",
            "message_body": "Access Denied",
        }
        return self.__config.get("ip_whitelist", {}).get(
            "block_response", default_response
        )

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self.__config.get("ssm", {})

    @property
    def ssm_imports(self) -> Dict[str, Any]:
        """SSM parameter imports for the Load Balancer"""
        return self.ssm.get("imports", {})

    @property
    def ssm_exports(self) -> Dict[str, Any]:
        """SSM parameter exports for the Load Balancer"""
        return self.ssm.get("exports", {})
    
    @property
    def ssm_parameters(self) -> Dict[str, Any]:
        """SSM parameters for the Load Balancer (only exports, not imports)"""
        # For LoadBalancer, only return exports to prevent trying to export imported values
        return self.ssm_exports
