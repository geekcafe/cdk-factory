"""
RdsConfig - supports RDS database settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

import re
from typing import Any, Dict, List, Optional
from aws_lambda_powertools import Logger
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig

logger = Logger(service="RdsConfig")


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
        """Name of the database to create (sanitized for RDS requirements)"""
        raw_name = self.__config.get("database_name", "appdb")
        return self._sanitize_database_name(raw_name)

    @property
    def username(self) -> str:
        """Master username for the database (sanitized for RDS requirements)"""
        raw_username = self.__config.get("username", "appuser") 
        return self._sanitize_username(raw_username)

    @property
    def secret_name(self) -> str:
        """Name of the secret to store credentials"""
        env_name = self.__deployment.environment if self.__deployment else None
        if not env_name:
            raise ValueError("No environment found for RDS secret name.  Please add an environment to the deployment.")
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

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter imports for the RDS instance"""
        # Check both nested and flat structures for backwards compatibility
        if "ssm" in self.__config and "imports" in self.__config["ssm"]:
            return self.__config["ssm"]["imports"]
        return self.__config.get("ssm_imports", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports for the RDS instance"""
        # Check both nested and flat structures for backwards compatibility
        if "ssm" in self.__config and "exports" in self.__config["ssm"]:
            return self.__config["ssm"]["exports"]
        return self.__config.get("ssm_exports", {})
    
    def _sanitize_database_name(self, name: str) -> str:
        """
        Sanitize database name to meet RDS requirements:
        - Must begin with a letter (a-z, A-Z)
        - Can contain alphanumeric characters and underscores
        - Max 64 characters
        
        Args:
            name: Raw database name from config
            
        Returns:
            Sanitized database name
            
        Raises:
            ValueError: If name starts with a number or is empty after sanitization
        """
        if not name:
            raise ValueError("Database name cannot be empty")
        
        # Replace hyphens with underscores, remove other invalid chars
        sanitized = name.replace('-', '_')
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)
        
        if not sanitized:
            raise ValueError(f"Database name '{name}' contains no valid characters")
        
        # Check if it starts with a number
        if sanitized[0].isdigit():
            raise ValueError(
                f"Database name '{name}' (sanitized to '{sanitized}') cannot start with a number. "
                f"Please ensure the database name begins with a letter."
            )
        
        # Truncate to 64 characters if needed
        if len(sanitized) > 64:
            sanitized = sanitized[:64]
        
        # Log if sanitization changed the name
        if sanitized != name:
            logger.info(f"Sanitized database name from '{name}' to '{sanitized}'")
        
        return sanitized
    
    def _sanitize_username(self, username: str) -> str:
        """
        Sanitize username to meet RDS requirements:
        - Must begin with a letter (a-z, A-Z)
        - Can contain alphanumeric characters and underscores
        - Max 16 characters for MySQL
        
        Args:
            username: Raw username from config
            
        Returns:
            Sanitized username
            
        Raises:
            ValueError: If username is invalid
        """
        if not username:
            raise ValueError("Username cannot be empty")
        
        # Replace hyphens with underscores, remove other invalid chars
        sanitized = username.replace('-', '_')
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)
        
        if not sanitized:
            raise ValueError(f"Username '{username}' contains no valid characters")
        
        # Check if it starts with a number
        if sanitized[0].isdigit():
            raise ValueError(
                f"Username '{username}' (sanitized to '{sanitized}') cannot start with a number. "
                f"Please ensure the username begins with a letter."
            )
        
        # Truncate to 16 characters for MySQL (other engines may vary)
        if len(sanitized) > 16:
            sanitized = sanitized[:16]
        
        # Log if sanitization changed the username
        if sanitized != username:
            logger.info(f"Sanitized username from '{username}' to '{sanitized}'")
        
        return sanitized
