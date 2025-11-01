"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class RumConfig(EnhancedBaseConfig):
    """
    RUM (Real User Monitoring) Configuration - supports CloudWatch RUM app monitor settings.
    Each property reads from the config dict and provides sensible defaults.
    """

    def __init__(self, config: dict = None) -> None:
        super().__init__(config or {}, resource_type="rum", resource_name=config.get("name", "rum") if config else "rum")
        self.__config = config or {}

    @property
    def name(self) -> str:
        """Name for the RUM app monitor"""
        return self.__config.get("name", "app-monitor")

    @property
    def domain(self) -> Optional[str]:
        """The top-level internet domain name for which your application has administrative authority"""
        return self.__config.get("domain")

    @property
    def domain_list(self) -> Optional[List[str]]:
        """A list of top-level internet domain names for which your application has administrative authority"""
        return self.__config.get("domain_list")

    @property
    def cw_log_enabled(self) -> bool:
        """Whether to send telemetry data to CloudWatch Logs (default: False)"""
        return bool(self.__config.get("cw_log_enabled", False))

    @property
    def custom_events_enabled(self) -> bool:
        """Whether custom events are enabled (default: False)"""
        return bool(self.__config.get("custom_events_enabled", False))

    # App Monitor Configuration Properties
    @property
    def allow_cookies(self) -> bool:
        """Whether to allow cookies for user tracking (default: True)"""
        return bool(self.__config.get("allow_cookies", True))

    @property
    def enable_xray(self) -> bool:
        """Whether to enable X-Ray tracing (default: False)"""
        return bool(self.__config.get("enable_xray", False))

    @property
    def excluded_pages(self) -> Optional[List[str]]:
        """List of URLs to exclude from RUM data collection"""
        return self.__config.get("excluded_pages")

    @property
    def included_pages(self) -> Optional[List[str]]:
        """List of URLs to include in RUM data collection"""
        return self.__config.get("included_pages")

    @property
    def favorite_pages(self) -> Optional[List[str]]:
        """List of pages to mark as favorites in the RUM console"""
        return self.__config.get("favorite_pages")

    @property
    def session_sample_rate(self) -> float:
        """Portion of user sessions to sample (0.0 to 1.0, default: 0.1)"""
        rate = self.__config.get("session_sample_rate", 0.1)
        return float(rate) if rate is not None else 0.1

    @property
    def telemetries(self) -> List[str]:
        """Types of telemetry data to collect (default: ['errors', 'performance', 'http'])"""
        return self.__config.get("telemetries", ["errors", "performance", "http"])

    # Cognito Integration Properties
    @property
    def cognito_identity_pool_id(self) -> Optional[str]:
        """Existing Cognito Identity Pool ID to use for authorization"""
        return self.__config.get("cognito_identity_pool_id")

    @property
    def cognito_user_pool_id(self) -> Optional[str]:
        """Existing Cognito User Pool ID to reference"""
        return self.__config.get("cognito_user_pool_id")

    @property
    def create_cognito_identity_pool(self) -> bool:
        """Whether to create a new Cognito Identity Pool if none provided (default: True)"""
        return bool(self.__config.get("create_cognito_identity_pool", True))

    @property
    def cognito_identity_pool_name(self) -> str:
        """Name for the Cognito Identity Pool if creating one"""
        return self.__config.get("cognito_identity_pool_name", f"{self.name}_identity_pool")

    @property
    def cognito_user_pool_name(self) -> str:
        """Name for the Cognito User Pool if creating one"""
        return self.__config.get("cognito_user_pool_name", f"{self.name}_user_pool")

    @property
    def create_cognito_user_pool(self) -> bool:
        """Whether to create a new Cognito User Pool if none provided (default: True)"""
        return bool(self.__config.get("create_cognito_user_pool", True))

    # Metric Destinations
    @property
    def metric_destinations(self) -> Optional[List[Dict[str, Any]]]:
        """List of metric destinations for extended metrics"""
        return self.__config.get("metric_destinations")

    # Tags
    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the RUM app monitor"""
        return self.__config.get("tags", {})

    # SSM Integration
    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration for importing/exporting resources"""
        return self.__config.get("ssm", {})

    @property 
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter paths for exporting RUM resources"""
        return self.ssm.get("exports", {})

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter paths for importing external resources"""
        return self.ssm.get("imports", {})
