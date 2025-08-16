"""
CodeArtifact Configuration for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

from cdk_factory.configurations.deployment import DeploymentConfig


class CodeArtifactConfig:
    """AWS CodeArtifact Configuration"""

    def __init__(
        self, config: dict, deployment: DeploymentConfig | None = None
    ) -> None:
        self.__config = config
        self.__deployment = deployment

    @property
    def domain_name(self) -> str:
        """CodeArtifact Domain Name"""
        if self.__config and isinstance(self.__config, dict):
            name = self.__config.get("domain_name", "")
            if not name:
                raise RuntimeError('CodeArtifact Configuration is missing the "domain_name" key/value pair')
            
            if not self.__deployment:
                raise RuntimeError("Deployment is not defined")

            return self.__deployment.build_resource_name(name)

        raise RuntimeError('CodeArtifact Configuration is missing the "domain_name" key/value pair')

    @property
    def domain_description(self) -> Optional[str]:
        """CodeArtifact Domain Description"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("domain_description")
        return None

    @property
    def repositories(self) -> List[Dict[str, Any]]:
        """List of repositories in the domain"""
        if self.__config and isinstance(self.__config, dict):
            repos = self.__config.get("repositories", [])
            if not isinstance(repos, list):
                return []
            return repos
        return []

    @property
    def upstream_repositories(self) -> List[str]:
        """List of upstream repositories"""
        if self.__config and isinstance(self.__config, dict):
            repos = self.__config.get("upstream_repositories", [])
            if not isinstance(repos, list):
                return []
            return repos
        return []

    @property
    def external_connections(self) -> List[str]:
        """List of external connections (e.g., npm, pypi)"""
        if self.__config and isinstance(self.__config, dict):
            connections = self.__config.get("external_connections", [])
            if not isinstance(connections, list):
                return []
            return connections
        return []

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
