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
    def resoure_type(self) -> str:
        """Resource Type"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("resource_type", "")

        return ""
