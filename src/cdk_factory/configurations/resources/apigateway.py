"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class ApiGatewayConfig:
    """API Gateway"""

    def __init__(self, config: dict) -> None:
        self.__config: dict = config

    def __get(self, key: str) -> str | dict | None:
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get(key)

        return None

    @property
    def route(self) -> str | None:
        """api route"""
        value = self.__get("route")
        if isinstance(value, str):
            return value

        return None

    @property
    def routes(self) -> str | None:
        """api routes"""
        value = self.__get("routes")
        if isinstance(value, str):
            return value

        return ""

    @property
    def method(self) -> str:
        """api method"""
        value = self.__get("method")
        if isinstance(value, str):
            return value

        return ""

    @property
    def enabled(self) -> bool:
        """api method"""
        enabled = self.__get("enabled")

        return str(enabled).lower() == "true"

    @property
    def skip_authorizer(self) -> bool:
        """api method"""
        skip_authorizer = self.__get("skip_authorizer") or ""
        return str(skip_authorizer).lower() == "true"
