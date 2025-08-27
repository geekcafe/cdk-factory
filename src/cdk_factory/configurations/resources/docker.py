from typing import Dict

"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class DockerConfig:
    """
    DockerConfig Container Information

    """

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def name(self) -> str:
        """Name (Repository Name)"""

        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("name")
            if isinstance(value, str):
                return value

        return ""

    @property
    def uri(self) -> str:
        """uri"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("uri")
            if isinstance(value, str):
                return value

        return ""

    @property
    def arn(self) -> str:
        """arn"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("arn")
            if isinstance(value, str):
                return value

        return ""

    @property
    def file(self) -> str:
        """file"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("file")
            if isinstance(value, str):
                return value

        return ""

    @property
    def image(self) -> bool:
        """image"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("image")).lower() == "true"

        return False

    @property
    def build_args(self) -> Dict[str, str]:
        """build_args"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("build_args")
            if isinstance(value, dict):
                return value

        return {}

    @property
    def tag(self) -> str:
        """tag"""
        if self.__config and isinstance(self.__config, dict):
            value = (
                self.__config.get("tag") or self.__config.get("image_tag") or "latest"
            )
            if isinstance(value, str):
                return value

        return "latest"
