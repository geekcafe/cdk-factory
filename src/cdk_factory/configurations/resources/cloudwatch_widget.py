"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""


class CloudWatchWidgetConfig:
    """A CloudWatch Widget"""

    def __init__(self, config: dict) -> None:
        self.__config: dict = config

    @property
    def title(self) -> str:
        """Widget Title"""
        value: str = ""
        if self.__config:
            value = self.__config.get("title", "")

        return value

    @property
    def height(self) -> int:
        """
        The height of the widget. Defaults to 6
        The height is specified in grid units. Each grid unit corresponds to a row in the layout.
        """
        value: int = 6
        if self.__config:
            value = self.__config.get("height", value)

        return int(value)

    @property
    def width(self) -> int:
        """
        The width of the widget.  Defaults to 6 or 1/4 of the width space
        The width is specified in grid units. The total width of the dashboard is divided into 24 grid units.
        So, if you specify a widget width of 12, it will take up half the width of the dashboard.
        """
        value: int = 6
        if self.__config:
            value = self.__config.get("width", value)

        return int(value)
