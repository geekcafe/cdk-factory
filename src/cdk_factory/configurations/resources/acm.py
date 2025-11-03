"""
AcmConfig - supports ACM (AWS Certificate Manager) settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional


class AcmConfig:
    """
    ACM Configuration - supports AWS Certificate Manager settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """Certificate configuration name"""
        return self.__config.get("name", "certificate")

    @property
    def domain_name(self) -> str:
        """Primary domain name for the certificate"""
        domain = self.__config.get("domain_name")
        if not domain:
            raise ValueError("domain_name is required for ACM certificate")
        return domain

    @property
    def subject_alternative_names(self) -> List[str]:
        """Subject alternative names (SANs) for the certificate"""
        sans = self.__config.get("subject_alternative_names", [])
        # Also check for alternate_names for backward compatibility
        if not sans:
            sans = self.__config.get("alternate_names", [])
        return sans

    @property
    def hosted_zone_id(self) -> Optional[str]:
        """Route53 hosted zone ID for DNS validation"""
        return self.__config.get("hosted_zone_id")

    @property
    def hosted_zone_name(self) -> Optional[str]:
        """Route53 hosted zone name (used for looking up zone)"""
        return self.__config.get("hosted_zone_name")

    @property
    def validation_method(self) -> str:
        """Certificate validation method (DNS or EMAIL)"""
        return self.__config.get("validation_method", "DNS")

    @property
    def certificate_transparency_logging_preference(self) -> Optional[str]:
        """Certificate transparency logging preference (ENABLED or DISABLED)"""
        return self.__config.get("certificate_transparency_logging_preference")

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration for importing/exporting resources"""
        return self.__config.get("ssm", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter paths to export certificate details"""
        exports = self.ssm.get("exports", {})
        
        # Provide default SSM export path if not specified
        if not exports and self.__deployment:
            workload_env = self.__deployment.workload.get("environment", self.__deployment.environment)
            workload_name = self.__deployment.workload.get("name", self.__deployment.workload_name)
            exports = {
                "certificate_arn": f"/{workload_env}/{workload_name}/certificate/arn"
            }
        
        return exports

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the certificate"""
        return self.__config.get("tags", {})
