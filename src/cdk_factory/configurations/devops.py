"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Any, Dict, List
from cdk_factory.configurations.resources.code_repository import CodeRepositoryConfig
from cdk_factory.configurations.resources.lambda_layers import LambdaLayersConfig


class DevOps:
    """
    DevOps Configuration
    """

    def __init__(self, devops: dict) -> None:
        self.__devops = devops
        self.__lambda_layers = LambdaLayersConfig(devops.get("lambda_layers", {}))
        self.__code_repository: CodeRepositoryConfig | None = None
        self.__commands = devops.get("commands", [])

    @property
    def name(self) -> str | None:
        """
        Returns the devops name
        """
        return self.__devops["name"]

    @property
    def region(self) -> str | None:
        """
        Returns the devops name
        """
        return self.__devops["region"]

    @property
    def account(self) -> str | None:
        """
        Returns the devops name
        """
        return self.__devops["account"]

    @property
    def email(self) -> str | None:
        """
        Returns the devops name
        """
        return self.__devops.get("email")

    @property
    def lambda_layers(self) -> LambdaLayersConfig:
        """
        Returns and instance of LambdaLayersConfig
        """
        return self.__lambda_layers

    @property
    def code_repository(self) -> CodeRepositoryConfig:
        """The Code Repository"""
        if not self.__code_repository:
            self.__code_repository = CodeRepositoryConfig(
                self.__devops.get("code_repository", {})
            )
            if (
                not self.__code_repository.repository
                or not self.__code_repository.repository
            ):
                raise ValueError(
                    "Code Repository is not defined in the configuration "
                    "workload.devops.code_repository.repository: {}"
                )
        return self.__code_repository

    @property
    def commands(self) -> List[Dict[str, Any]]:
        """
        Returns the devops commands
        """
        return self.__commands

    @property
    def cdk_cli_version(self) -> str | None:
        """
        Returns the CDK CLI version
        """
        return self.__devops.get("cdk_cli_version")

    @property
    def pipeline_version(self) -> str:
        return self.__devops.get("pipeline_version", "v2")
