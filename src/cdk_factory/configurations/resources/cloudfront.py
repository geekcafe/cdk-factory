"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class CloudFrontConfig(EnhancedBaseConfig):
    """
    Static cloudfront information from AWS
    """

    def __init__(self, config: dict = None) -> None:
        super().__init__(config or {}, resource_type="cloudfront", resource_name=config.get("name", "cloudfront") if config else "cloudfront")
        self.__cloudfront = config

    @property
    def description(self):
        """
        Returns the description
        """
        return self.__cloudfront.get("description")

    @property
    def hosted_zone_id(self):
        """
        Returns the hosted_zone_id for cloudfront
        Use this when making dns changes when you want your custom domain
        to be route through cloudfront.

        As far as I know this Id is static and used for all of cloudfront
        """
        return self.__cloudfront.get("hosted_zone_id", "Z2FDTNDATAQYW2")
