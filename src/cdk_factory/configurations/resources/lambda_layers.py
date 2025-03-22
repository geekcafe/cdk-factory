"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class LambdaLayersConfig:
    """
    Standard Known Lambda Layers
    TODO: Let's review this to see if we want to just get a list from the config
    """

    def __init__(self, lambda_layers: dict) -> None:
        self.__lambda_layers: dict = lambda_layers

    @property
    def power_tools_arn(self) -> str | None:
        """Power Tools Lambda Layer Arn"""
        if self.__lambda_layers and isinstance(self.__lambda_layers, dict):
            return self.__lambda_layers.get("power_tools_arn")
        return None
