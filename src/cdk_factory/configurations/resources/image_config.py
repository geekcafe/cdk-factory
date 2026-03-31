"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List, Optional


class ImageConfig:
    """Parses the image_config block from Lambda config JSON.

    Supports overriding the Docker CMD at deploy time via
    AWS Lambda's ImageConfig.Command property.

    Example JSON:
        {
            "image_config": {
                "command": ["my_package.handlers.app.lambda_handler"]
            }
        }
    """

    def __init__(self, config: dict = None) -> None:
        self.__config = config

    @property
    def command(self) -> Optional[List[str]]:
        """CMD override list for Docker image.

        Returns:
            List of strings for the CMD override, or None if not configured.
        """
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("command")
        return None
