"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class Route53HostedZoneConfig:
    """Route 53 Hosted ZOne"""

    def __init__(self, hosted_zone: dict) -> None:
        self.__hosted_zone: dict = hosted_zone

    @property
    def name(self) -> str | None:
        """Gets the hosted zone name eg. sub.domain.com"""
        return self.__hosted_zone.get("name")

    @property
    def id(self) -> str | None:
        """Gets the hosted zone id. The AWS Hosted Zone ID"""
        return self.__hosted_zone.get("id")

    @property
    def domain(self) -> str | None:
        """Gets the domain name"""
        return self.__hosted_zone.get("domain")

    @property
    def aliases(self) -> List[str]:
        """Gets the list of aliases"""
        return self.__hosted_zone.get("aliases", [])
