"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class CloudFrontConfig:
    """
    Static cloudfront information from AWS
    """

    def __init__(self, cloudfront: dict) -> None:
        self.__cloudfront = cloudfront

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
