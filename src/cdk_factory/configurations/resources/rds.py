"""
RdsConfig - supports RDS database settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Literal
from aws_lambda_powertools import Logger
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig

logger = Logger(service="RdsConfig")

# Supported RDS engines
Engine = Literal["mysql", "mariadb", "postgres", "aurora-mysql", "aurora-postgres", "sqlserver", "oracle"]


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
    def default_database_name(self) -> str:
        """RDS instance name"""
        return self.__config.get("name", self.database_name)
    
    @property
    def instance_identifier(self) -> Optional[str]:
        """RDS DB instance identifier (sanitized)"""
        raw_id = self.__config.get("instance_identifier")
        if not raw_id:
            return None
        return self._sanitize_instance_identifier(raw_id)
    
    def _sanitize_instance_identifier(self, identifier: str) -> str:
        """
        Sanitize DB instance identifier to meet RDS requirements:
        - 1-63 chars, lowercase letters/digits/hyphen
        - Must start with letter, can't end with hyphen, no consecutive hyphens
        """
        if not identifier:
            raise ValueError("Instance identifier cannot be empty")
        
        sanitized, notes = self._sanitize_instance_identifier_impl(identifier)
        
        if notes:
            logger.info(f"Sanitized instance identifier from '{identifier}' to '{sanitized}': {', '.join(notes)}")
        
        return sanitized
    
    def _sanitize_instance_identifier_impl(self, identifier: str) -> Tuple[str, List[str]]:
        """
        DB instance identifier rules (all engines):
        - 1-63 chars, lowercase letters/digits/hyphen
        - Must start with letter
        - Can't end with hyphen
        - No consecutive hyphens (--)
        """
        notes: List[str] = []
        s = identifier.lower()
        
        # Keep only lowercase letters, digits, hyphen
        s_clean = re.sub(r"[^a-z0-9-]", "", s)
        if s_clean != s:
            notes.append("removed invalid characters (only a-z, 0-9, '-' allowed)")
        s = s_clean
        
        if not s:
            raise ValueError(f"Instance identifier '{identifier}' contains no valid characters")
        
        # Must start with letter
        if not re.match(r"^[a-z]", s):
            s = f"db{s}"
            notes.append("prefixed with 'db' to start with a letter")
        
        # Collapse consecutive hyphens
        s_collapsed = re.sub(r"-{2,}", "-", s)
        if s_collapsed != s:
            s = s_collapsed
            notes.append("collapsed consecutive hyphens")
        
        # Can't end with hyphen
        if s.endswith("-"):
            s = s.rstrip("-")
            notes.append("removed trailing hyphen")
        
        # Truncate to 63 characters
        if len(s) > 63:
            s = s[:63]
            # Make sure we didn't truncate to a trailing hyphen
            if s.endswith("-"):
                s = s.rstrip("-")
            notes.append("truncated to 63 characters")
        
        return s, notes

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
    def database_name(self) -> str | None:
        """
        Name of the database to create (sanitized for RDS requirements)
        Optional and not required
        """
        raw_name = self.__config.get("database_name")
        if not raw_name:
            return None
        return self._sanitize_database_name(raw_name)

    @property
    def master_username(self) -> str:
        """Master username for the database (sanitized for RDS requirements)"""
        raw_username = self.__config.get("master_username") 
        if not raw_username:
            raise ValueError("No master username found. Please add the master username to the config.")
        return self._sanitize_username(raw_username)

    @property
    def secret_name(self) -> str:
        """Name of the secret to store credentials (includes workload to prevent collisions)"""
        if "secret_name" in self.__config:
            return self.__config["secret_name"]
        
        # Build a unique secret name using environment and workload
        if not self.__deployment:
            raise ValueError("No deployment context found for RDS secret name")
        
        env_name = self.__deployment.environment
        workload_name = self.__deployment.workload_name
        
        if not env_name:
            raise ValueError("No environment found for RDS secret name. Please add an environment to the deployment.")
        if not workload_name:
            raise ValueError("No workload name found for RDS secret name. Please add a workload name to the deployment.")
        
        # Default pattern: /{environment}/{workload}/rds/credentials
        return f"/{env_name}/{workload_name}/rds/credentials"

    @property
    def allocated_storage(self) -> int:
        """Allocated storage in GB"""
        # Ensure we return an integer
        return int(self.__config.get("allocated_storage", 20))
    
    @property
    def max_allocated_storage(self) -> Optional[int]:
        """Maximum storage for auto-scaling in GB (enables storage auto-scaling if set)"""
        max_storage = self.__config.get("max_allocated_storage")
        return int(max_storage) if max_storage is not None else None

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
    def allow_major_version_upgrade(self) -> bool:
        """Whether to allow major version upgrades"""
        return self.__config.get("allow_major_version_upgrade", False)

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
        """
        Log types to export to CloudWatch (engine-specific).
        Returns configured log types or engine-specific defaults.
        """
        # If explicitly configured, use that
        if "cloudwatch_logs_exports" in self.__config:
            return self.__config["cloudwatch_logs_exports"]
        
        # Otherwise, return engine-specific defaults
        engine = self.engine.lower()
        
        # MySQL / MariaDB
        if engine in ("mysql", "mariadb", "aurora-mysql"):
            return ["error", "general", "slowquery"]
        
        # PostgreSQL
        elif engine in ("postgres", "postgresql", "aurora-postgres", "aurora-postgresql"):
            return ["postgresql"]
        
        # SQL Server
        elif engine in ("sqlserver", "sqlserver-ee", "sqlserver-se", "sqlserver-ex", "sqlserver-web"):
            return ["error", "agent"]
        
        # Oracle
        elif engine in ("oracle", "oracle-ee", "oracle-se2", "oracle-se1"):
            return ["alert", "audit", "trace"]
        
        # Default to empty list for unknown engines (safer than guessing)
        else:
            logger.warning(f"Unknown engine '{engine}', disabling CloudWatch logs exports by default")
            return []

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
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self.__config.get("ssm", {})

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter imports for the RDS instance"""
        return self.ssm.get("imports", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports for the RDS instance"""
        return self.ssm.get("exports", {})
    
    def _sanitize_database_name(self, name: str) -> str:
        """
        Sanitize database name to meet RDS requirements (engine-specific).
        Implements rules from RDS documentation for each engine type.
        
        Args:
            name: Raw database name from config
            
        Returns:
            Sanitized database name
            
        Raises:
            ValueError: If name cannot be sanitized to meet requirements
        """
        if not name:
            raise ValueError("Database name cannot be empty")
        
        engine = self.engine.lower()
        sanitized, notes = self._sanitize_db_name_impl(engine, name)
        
        if notes:
            logger.info(f"Sanitized database name from '{name}' to '{sanitized}': {', '.join(notes)}")
        
        return sanitized
    
    def _sanitize_db_name_impl(self, engine: str, name: str) -> Tuple[str, List[str]]:
        """
        Engine-specific database name sanitization.
        Based on AWS RDS naming requirements:
        - MySQL/MariaDB: 1-64 chars, start with letter, letters/digits/underscore
        - PostgreSQL: 1-63 chars, start with letter, letters/digits/underscore
        - SQL Server: 1-128 chars, start with letter, letters/digits/underscore
        - Oracle: 1-8 chars (SID), alphanumeric only, start with letter
        """
        notes: List[str] = []
        
        # Determine engine-specific limits
        if engine in ("mysql", "mariadb", "aurora-mysql"):
            allowed_chars = r"A-Za-z0-9_"
            max_len = 64
        elif engine in ("postgres", "postgresql", "aurora-postgres", "aurora-postgresql"):
            allowed_chars = r"A-Za-z0-9_"
            max_len = 63
        elif engine in ("sqlserver", "sqlserver-ee", "sqlserver-se", "sqlserver-ex", "sqlserver-web"):
            allowed_chars = r"A-Za-z0-9_"
            max_len = 128
        elif engine in ("oracle", "oracle-ee", "oracle-se2", "oracle-se1"):
            allowed_chars = r"A-Za-z0-9"  # No underscore for Oracle SID
            max_len = 8
        else:
            # Default to conservative rules
            allowed_chars = r"A-Za-z0-9_"
            max_len = 64
            notes.append(f"unknown engine '{engine}', using default MySQL rules")
        
        # Replace hyphens with underscores (except Oracle which doesn't allow underscores)
        s = name
        if "oracle" not in engine:
            s = s.replace("-", "_")
            if "_" in name and "-" in name:
                notes.append("replaced hyphens with underscores")
        
        # Strip disallowed characters
        s_clean = re.sub(f"[^{allowed_chars}]", "", s)
        if s_clean != s:
            notes.append("removed invalid characters")
        s = s_clean
        
        if not s:
            raise ValueError(f"Database name '{name}' contains no valid characters after sanitization")
        
        # Must start with a letter
        if not re.match(r"^[A-Za-z]", s):
            s = f"db{s}"
            notes.append("prefixed with 'db' to start with a letter")
        
        # Truncate to max length
        if len(s) > max_len:
            s = s[:max_len]
            notes.append(f"truncated to {max_len} characters")
        
        # SQL Server: can't start with 'rdsadmin'
        if "sqlserver" in engine and s.lower().startswith("rdsadmin"):
            s = f"db_{s}"
            notes.append("prefixed to avoid 'rdsadmin' (SQL Server restriction)")
        
        return s, notes
    
    def _sanitize_username(self, username: str) -> str:
        """
        Sanitize master username to meet RDS requirements:
        - Must begin with a letter (a-z, A-Z)
        - Can contain alphanumeric characters and underscores
        - Max 16 characters (AWS RDS master username limit)
        - Cannot be a reserved word
        
        Args:
            username: Raw username from config
            
        Returns:
            Sanitized username
            
        Raises:
            ValueError: If username is invalid
        """
        if not username:
            raise ValueError("Username cannot be empty")
        
        sanitized, notes = self._sanitize_master_username_impl(username)
        
        if notes:
            logger.info(f"Sanitized username from '{username}' to '{sanitized}': {', '.join(notes)}")
        
        return sanitized
    
    def _sanitize_master_username_impl(self, username: str) -> Tuple[str, List[str]]:
        """
        Sanitize master username according to AWS RDS rules:
        - 1-16 characters
        - Start with a letter
        - Letters, digits, underscore only
        - Not a reserved word
        """
        notes: List[str] = []
        s = username
        
        # Replace hyphens with underscores, remove other invalid chars
        s = s.replace("-", "_")
        s_clean = re.sub(r"[^A-Za-z0-9_]", "", s)
        if s_clean != s:
            notes.append("removed invalid characters")
        s = s_clean
        
        if not s:
            raise ValueError(f"Username '{username}' contains no valid characters after sanitization")
        
        # Must start with a letter
        if not re.match(r"^[A-Za-z]", s):
            s = f"user{s}"
            notes.append("prefixed with 'user' to start with a letter")
        
        # Truncate to 16 characters
        if len(s) > 16:
            s = s[:16]
            notes.append("truncated to 16 characters")
        
        # Check against common reserved words
        reserved = {"postgres", "mysql", "root", "admin", "rdsadmin", "system", "sa", "user"}
        if s.lower() in reserved:
            s = f"{s}_usr"
            # Re-truncate if needed after adding suffix
            if len(s) > 16:
                s = s[:16]
            notes.append("appended '_usr' to avoid reserved username")
        
        return s, notes
