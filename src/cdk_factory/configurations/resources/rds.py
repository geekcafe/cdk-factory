"""
RdsConfig - supports RDS database settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any, Dict, List, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class RdsConfig(EnhancedBaseConfig):
    """
    RDS Configuration - supports RDS database settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict, deployment) -> None:
        super().__init__(config or {}, resource_type="rds", resource_name=config.get("name", "rds") if config else "rds")
        self.__config = config or {}
        self.__deployment = deployment

    @property
    def name(self) -> str:
        """RDS instance name"""
        return self.__config.get("name", "database")

    @property
    def engine(self) -> str:
        """Database engine"""
        return self.__config.get("engine", "postgres")

    @property
    def engine_version(self) -> str:
        """Database engine version"""
        engine_version = self.__config.get("engine_version")
        if not engine_version:
            raise ValueError("No engine version found")
        return engine_version

    @property
    def instance_class(self) -> str:
        """Database instance class"""
        return self.__config.get("instance_class", "t3.micro")

    @property
    def database_name(self) -> str:
        """Name of the database to create"""
        return self.__config.get("database_name", "appdb")

    @property
    def username(self) -> str:
        """Master username for the database"""
        return self.__config.get("username", "appuser")

    @property
    def secret_name(self) -> str:
        """Name of the secret to store credentials"""
        env_name = self.__deployment.environment if self.__deployment else "dev"
        return self.__config.get("secret_name", f"/{env_name}/db/creds")

    @property
    def allocated_storage(self) -> int:
        """Allocated storage in GB"""
        # Ensure we return an integer
        return int(self.__config.get("allocated_storage", 20))

    @property
    def storage_encrypted(self) -> bool:
        """Whether storage is encrypted"""
        return self.__config.get("storage_encrypted", True)

    @property
    def multi_az(self) -> bool:
        """Whether to enable Multi-AZ deployment"""
        return self.__config.get("multi_az", False)

    @property
    def backup_retention(self) -> int:
        """Backup retention period in days"""
        return self.__config.get("backup_retention", 7)

    @property
    def deletion_protection(self) -> bool:
        """Whether deletion protection is enabled"""
        return self.__config.get("deletion_protection", False)

    @property
    def enable_performance_insights(self) -> bool:
        """Whether to enable Performance Insights"""
        return self.__config.get("enable_performance_insights", True)

    @property
    def subnet_group_name(self) -> str:
        """Subnet group name for database placement"""
        return self.__config.get("subnet_group_name", "db")

    @property
    def security_group_ids(self) -> List[str]:
        """Security group IDs for the database"""
        return self.__config.get("security_group_ids", [])

    @property
    def cloudwatch_logs_exports(self) -> List[str]:
        """Log types to export to CloudWatch"""
        return self.__config.get("cloudwatch_logs_exports", ["postgresql"])

    @property
    def removal_policy(self) -> str:
        """Removal policy for the database"""
        return self.__config.get("removal_policy", "retain")

    @property
    def existing_instance_id(self) -> Optional[str]:
        """Existing RDS instance ID to import (if using existing)"""
        return self.__config.get("existing_instance_id")

    @property
    def tags(self) -> Dict[str, str]:
        """Tags to apply to the RDS instance"""
        return self.__config.get("tags", {})

    @property
    def vpc_id(self) -> str | None:
        """Returns the VPC ID for the Security Group"""
        return self.__config.get("vpc_id")

    @vpc_id.setter
    def vpc_id(self, value: str):
        """Sets the VPC ID for the Security Group"""
        self.__config["vpc_id"] = value
