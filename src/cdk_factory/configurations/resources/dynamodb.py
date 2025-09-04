"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class DynamoDBConfig(EnhancedBaseConfig):
    """DynamoDB Resource"""

    def __init__(self, config: dict, deployment) -> None:
        super().__init__(config or {}, resource_type="dynamodb", resource_name=config.get("name", "dynamodb") if config else "dynamodb")
        self.__config = config
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """DB Name"""
        table_name: str | None = None
        if self.__config and isinstance(self.__config, dict):
            table_name = self.__config.get("name")

        if not table_name:
            table_name = self.__deployment.build_resource_name("database")
        if not table_name:
            raise ValueError("No table name found")

        if not isinstance(table_name, str):
            raise ValueError("Table name must be a string")
        return table_name

    @property
    def use_existing(self) -> bool:
        """
        Returns if we should use an existing table
        """
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("use_existing", False)).lower() == "true"
        return False

    @property
    def replica_regions(self) -> List[str]:
        """
        Returns if we should use an existing table
        """

        regions: List[str] = []

        if self.__config and isinstance(self.__config, dict):
            regions = self.__config.get("replica_regions", [])

        if not isinstance(regions, list):
            regions = []
        return regions

    @property
    def enable_delete_protection(self) -> bool:
        """
        Returns if we should use an existing table
        """
        enabled: bool = True
        if self.__config and isinstance(self.__config, dict):
            enabled = (
                str(self.__config.get("enable_delete_protection", True)).lower()
                == "true"
            )
        return enabled

    @property
    def point_in_time_recovery(self) -> bool:
        """
        Returns if we should use an pitr
        """
        enabled: bool = True
        if self.__config and isinstance(self.__config, dict):
            enabled = (
                str(self.__config.get("point_in_time_recovery", True)).lower() == "true"
            )
        return enabled

    @property
    def gsi_count(self) -> int:
        """
        Returns the number of global secondary indexes
        """
        default_count: int = 5
        if self.__config and isinstance(self.__config, dict):
            return int(self.__config.get("gsi_count", default_count))
        return default_count
