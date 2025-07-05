class LambdaTriggersConfig:
    """Lambda Triggers"""

    def __init__(self, config: dict) -> None:
        self.__config = config

    @property
    def name(self) -> str:
        """Name"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("name", "")

        return ""

    @property
    def resource_type(self) -> str:
        """Resource Type"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("resource_type", "")

        return ""

    @property
    def schedule(self) -> dict:
        """Schedule, used for event bridge"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("schedule")
            if isinstance(value, dict):
                return value

        return {}
