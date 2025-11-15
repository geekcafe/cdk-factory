"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
from typing import Dict, List, Any, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class CloudFrontConfig(EnhancedBaseConfig):
    """
    CloudFront Distribution Configuration
    Supports both S3 origins (static sites) and custom origins (ALB, API Gateway, etc.)
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        super().__init__(
            config or {}, 
            resource_type="cloudfront", 
            resource_name=config.get("name", "cloudfront") if config else "cloudfront"
        )
        self._config = config or {}
        self._deployment = deployment

    @property
    def name(self) -> str:
        """Distribution name"""
        return self._config.get("name", "cloudfront")

    @property
    def description(self) -> str:
        """Distribution description"""
        return self._config.get("description", "CloudFront Distribution")

    @property
    def comment(self) -> str:
        """Distribution comment"""
        return self._config.get("comment", "")

    @property
    def enabled(self) -> bool:
        """Whether distribution is enabled"""
        return self._config.get("enabled", True)

    @property
    def aliases(self) -> List[str]:
        """Alternate domain names (CNAMEs)"""
        return self._config.get("aliases", [])

    @property
    def price_class(self) -> str:
        """Price class for edge locations"""
        return self._config.get("price_class", "PriceClass_100")

    @property
    def http_version(self) -> str:
        """HTTP version (http2, http2_and_3)"""
        return self._config.get("http_version", "http2_and_3")

    @property
    def certificate(self) -> Optional[Dict[str, Any]]:
        """ACM certificate configuration"""
        return self._config.get("certificate")

    @property
    def origins(self) -> List[Dict[str, Any]]:
        """Origin configurations"""
        return self._config.get("origins", [])

    @property
    def default_cache_behavior(self) -> Dict[str, Any]:
        """Default cache behavior"""
        return self._config.get("default_cache_behavior", {})

    @property
    def cache_behaviors(self) -> List[Dict[str, Any]]:
        """Additional cache behaviors"""
        return self._config.get("cache_behaviors", [])

    @property
    def custom_error_responses(self) -> List[Dict[str, Any]]:
        """Custom error responses"""
        return self._config.get("custom_error_responses", [])

    @property
    def logging(self) -> Optional[Dict[str, Any]]:
        """Logging configuration"""
        return self._config.get("logging")

    @property
    def waf_web_acl_id(self) -> Optional[str]:
        """WAF Web ACL ID"""
        return self._config.get("waf_web_acl_id")

    @property
    def default_root_object(self) -> str | None:
        """Default root object"""
        return self._config.get("default_root_object")

    @property
    def tags(self) -> Dict[str, str]:
        """Resource tags"""
        return self._config.get("tags", {})

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self._config.get("ssm", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports"""
        return self.ssm.get("exports", {})

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter imports"""
        return self.ssm.get("imports", {})

    @property
    def hosted_zone_id(self) -> str:
        """
        Returns the hosted_zone_id for cloudfront
        Use this when making dns changes when you want your custom domain
        to be route through cloudfront.

        As far as I know this Id is static and used for all of cloudfront
        """
        return self._config.get("hosted_zone_id", "Z2FDTNDATAQYW2")
