"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class ExistingResources:
    """Existing Resources"""

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def workload_bucket(self) -> str | None:
        """Gets the s3 bucket name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("workload_bucket")
        return None
