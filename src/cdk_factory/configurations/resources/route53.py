"""
Route53Config - supports Route53 DNS settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional


class Route53Config:
    """
    Route53 Configuration - supports Route53 DNS settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        self.__config = config or {}
        self.__deployment = config

    @property
    def name(self) -> str:
        """Route53 configuration name"""
        return self.__config.get("name", "dns")

    @property
    def hosted_zone_id(self) -> Optional[str]:
        """Hosted zone ID"""
        return self.__config.get("hosted_zone_id")
    
    @property
    def existing_hosted_zone_id(self) -> Optional[str]:
        """Existing hosted zone ID (alias for hosted_zone_id)"""
        return self.__config.get("existing_hosted_zone_id") or self.__config.get("hosted_zone_id")

    @property
    def domain_name(self) -> Optional[str]:
        """Domain name (also checks hosted_zone_name)"""
        return self.__config.get("domain_name") or self.__config.get("hosted_zone_name")

    @property
    def record_names(self) -> List[str]:
        """List of record names to create"""
        return self.__config.get("record_names", [])

    @property
    def create_hosted_zone(self) -> bool:
        """Whether to create a new hosted zone"""
        return self.__config.get("create_hosted_zone", False)

    @property
    def comment(self) -> str:
        """Comment for the hosted zone"""
        return self.__config.get("comment", "")

    @property
    def private_zone(self) -> bool:
        """Whether the hosted zone is private"""
        return self.__config.get("private_zone", False)

    @property
    def vpc_id(self) -> Optional[str]:
        """VPC ID for private hosted zone"""
        return self.__config.get("vpc_id")

    @property
    def certificate_arn(self) -> Optional[str]:
        """Certificate ARN for HTTPS"""
        return self.__config.get("certificate_arn")

    @property
    def create_certificate(self) -> bool:
        """Whether to create a new certificate"""
        return self.__config.get("create_certificate", False)

    @property
    def validation_method(self) -> str:
        """Certificate validation method"""
        return self.__config.get("validation_method", "DNS")

    @property
    def subject_alternative_names(self) -> List[str]:
        """Subject alternative names for the certificate"""
        return self.__config.get("subject_alternative_names", [])

    @property
    def aliases(self) -> List[Dict[str, Any]]:
        """Alias records to create"""
        return self.__config.get("aliases", [])

    @property
    def cname_records(self) -> List[Dict[str, Any]]:
        """CNAME records to create"""
        return self.__config.get("cname_records", [])

    @property
    def a_records(self) -> List[Dict[str, Any]]:
        """A records to create"""
        return self.__config.get("a_records", [])

    @property
    def aaaa_records(self) -> bool:
        """Whether to create AAAA records alongside A records"""
        return self.__config.get("aaaa_records", True)

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the Route53 resources"""
        return self.__config.get("tags", {})
    
    @property
    def records(self) -> List[Dict[str, Any]]:
        """Records to create"""
        return self.__config.get("records", [])
