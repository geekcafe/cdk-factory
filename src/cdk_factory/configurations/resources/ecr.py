"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from cdk_factory.configurations.deployment import DeploymentConfig


class ECRConfig:
    """ECR Configuration"""

    def __init__(
        self, config: dict, deployment: DeploymentConfig | None = None
    ) -> None:
        self.__config = config
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """Repository Name"""
        if self.__config and isinstance(self.__config, dict):
            name = self.__config.get("name", "")
            if not self.__deployment:
                raise RuntimeError("Deployment is not defined")

            return self.__deployment.build_resource_name(name)

        raise RuntimeError('ECR Configuration is missing the "name" key/value pair')

    @property
    def uri(self) -> str:
        """Repository Uri"""
        uri = None
        if self.__config and isinstance(self.__config, dict):
            uri = self.__config.get("uri")

        if not uri:
            uri = f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{self.name}"
        return uri

    @property
    def arn(self) -> str:
        """Repository Arn"""
        arn = None
        if self.__config and isinstance(self.__config, dict):
            arn = self.__config.get("arn")
        if not arn:
            arn = f"arn:aws:ecr:{self.region}:{self.account}:repository/{self.name}"
        return arn

    @property
    def image_scan_on_push(self) -> bool:
        """Perform an image scan on Push"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("image_scan_on_push")).lower() == "true"

        return False

    @property
    def empty_on_delete(self) -> bool:
        """Empty a repository on a detele request."""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("empty_on_delete")).lower() == "true"

        return False

    @property
    def auto_delete_untagged_images_in_days(self) -> int | None:
        """
        Clear out untagged images after x days.  This helps save costs.
        Untagged images will stay forever if you don't clean them out.
        """
        if self.__config and isinstance(self.__config, dict):
            days = self.__config.get("auto_delete_untagged_images_in_days")
            if days:
                days = int(days)

        return None

    @property
    def use_existing(self) -> bool:
        """
        Use Existing Repository
        """
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("use_existing")).lower() == "true"

        return False

    @property
    def account(self) -> str:
        """Account"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("account")

        if not value and self.__deployment:
            value = self.__deployment.account

        if not value:
            raise RuntimeError("Account is not defined")
        return value

    @property
    def region(self) -> str:
        """Region"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("region")

        if not value and self.__deployment:
            value = self.__deployment.region

        if not value:
            raise RuntimeError("Region is not defined")
        return value
