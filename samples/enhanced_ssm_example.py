#!/usr/bin/env python3
"""
Enhanced SSM Parameter Pattern Example
Demonstrates the new auto-discovery and flexible SSM parameter pattern.
"""

import os
import json
from aws_cdk import App, Stack, Environment
from constructs import Construct

# Example implementation of the enhanced SSM configuration classes
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum

class SsmMode(Enum):
    AUTO = "auto"
    MANUAL = "manual" 
    DISABLED = "disabled"

@dataclass
class SsmParameterDefinition:
    """Defines an SSM parameter with its metadata"""
    attribute: str
    path: Optional[str] = None
    description: Optional[str] = None
    parameter_type: str = "String"  # String, StringList, SecureString
    auto_export: bool = True
    auto_import: bool = True

# Resource type definitions for auto-discovery
RESOURCE_AUTO_EXPORTS = {
    "vpc": ["vpc_id", "vpc_cidr", "public_subnet_ids", "private_subnet_ids", "isolated_subnet_ids"],
    "security_group": ["security_group_id"],
    "rds": ["db_instance_id", "db_endpoint", "db_port", "db_secret_arn"],
    "api_gateway": ["api_gateway_id", "api_gateway_arn", "root_resource_id", "authorizer_id"],
    "cognito": ["user_pool_id", "user_pool_arn", "user_pool_client_id"],
    "lambda": ["function_name", "function_arn"],
    "s3": ["bucket_name", "bucket_arn"],
    "dynamodb": ["table_name", "table_arn"]
}

RESOURCE_AUTO_IMPORTS = {
    "security_group": ["vpc_id"],
    "rds": ["vpc_id", "security_group_ids", "subnet_group_name"],
    "lambda": ["vpc_id", "security_group_ids", "subnet_ids"],
    "api_gateway": ["cognito_user_pool_id", "cognito_user_pool_arn"],
    "ecs": ["vpc_id", "security_group_ids", "subnet_ids"],
    "alb": ["vpc_id", "security_group_ids", "subnet_ids"]
}

class EnhancedSsmConfig:
    """Enhanced SSM configuration with auto-discovery and flexible patterns"""
    
    def __init__(self, config: Dict, resource_type: str, resource_name: str):
        self.config = config.get("ssm", {})
        self.resource_type = resource_type
        self.resource_name = resource_name
        
    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)
    
    @property
    def organization(self) -> str:
        return self.config.get("organization", "cdk-factory")
    
    @property
    def environment(self) -> str:
        env = self.config.get("environment", "${ENVIRONMENT}")
        # Replace environment variables
        if env.startswith("${") and env.endswith("}"):
            env_var = env[2:-1]
            return os.getenv(env_var, "dev")
        return env
    
    @property
    def pattern(self) -> str:
        return self.config.get("pattern", "/{organization}/{environment}/{stack_type}/{resource_name}/{attribute}")
    
    @property
    def auto_export(self) -> bool:
        return self.config.get("auto_export", True)
    
    @property
    def auto_import(self) -> bool:
        return self.config.get("auto_import", True)
    
    def get_parameter_path(self, attribute: str, custom_path: Optional[str] = None) -> str:
        """Generate SSM parameter path using pattern or custom path"""
        if custom_path and custom_path.startswith("/"):
            return custom_path
            
        return self.pattern.format(
            organization=self.organization,
            environment=self.environment,
            stack_type=self.resource_type,
            resource_name=self.resource_name,
            attribute=attribute
        )
    
    def get_export_definitions(self) -> List[SsmParameterDefinition]:
        """Get list of parameters to export"""
        exports = self.config.get("exports", {})
        definitions = []
        
        # Add auto-discovered exports
        if self.auto_export:
            auto_exports = self._get_auto_exports()
            for attr in auto_exports:
                if attr not in exports:
                    exports[attr] = "auto"
        
        # Convert to parameter definitions
        for attr, path_config in exports.items():
            custom_path = None if path_config == "auto" else path_config
            definitions.append(SsmParameterDefinition(
                attribute=attr,
                path=self.get_parameter_path(attr, custom_path),
                auto_export=True
            ))
            
        return definitions
    
    def get_import_definitions(self) -> List[SsmParameterDefinition]:
        """Get list of parameters to import"""
        imports = self.config.get("imports", {})
        definitions = []
        
        # Add auto-discovered imports
        if self.auto_import:
            auto_imports = self._get_auto_imports()
            for attr in auto_imports:
                if attr not in imports:
                    imports[attr] = "auto"
        
        # Convert to parameter definitions
        for attr, path_config in imports.items():
            custom_path = None if path_config == "auto" else path_config
            definitions.append(SsmParameterDefinition(
                attribute=attr,
                path=self.get_parameter_path(attr, custom_path),
                auto_import=True
            ))
            
        return definitions
    
    def _get_auto_exports(self) -> List[str]:
        """Get auto-discovered exports based on resource type"""
        return RESOURCE_AUTO_EXPORTS.get(self.resource_type, [])
    
    def _get_auto_imports(self) -> List[str]:
        """Get auto-discovered imports based on resource type"""
        return RESOURCE_AUTO_IMPORTS.get(self.resource_type, [])


class DemoInfrastructureStack(Stack):
    """
    Demo infrastructure stack that exports VPC and Cognito resources
    Uses minimal configuration with auto-discovery
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Minimal configuration - uses all defaults
        config = {
            "ssm": {
                "enabled": True,
                "organization": "demo-app",
                "environment": os.getenv("DEPLOY_ENV", "dev")
            },
            "vpc": {
                "name": "infrastructure",
                "cidr": "10.0.0.0/16"
            },
            "cognito": {
                "name": "user-auth"
            }
        }
        
        self._deploy_vpc(config)
        self._deploy_cognito(config)
    
    def _deploy_vpc(self, config: Dict):
        """Deploy VPC with auto SSM export"""
        ssm_config = EnhancedSsmConfig(config, "vpc", config["vpc"]["name"])
        
        print(f"VPC SSM Configuration:")
        print(f"  Enabled: {ssm_config.enabled}")
        print(f"  Organization: {ssm_config.organization}")
        print(f"  Environment: {ssm_config.environment}")
        print(f"  Pattern: {ssm_config.pattern}")
        
        # Simulate VPC creation
        vpc_resources = {
            "vpc_id": "vpc-12345678",
            "vpc_cidr": "10.0.0.0/16",
            "public_subnet_ids": ["subnet-pub1", "subnet-pub2"],
            "private_subnet_ids": ["subnet-priv1", "subnet-priv2"]
        }
        
        # Show what would be exported
        export_definitions = ssm_config.get_export_definitions()
        print(f"\nVPC Auto-Export Definitions:")
        for definition in export_definitions:
            if definition.attribute in vpc_resources:
                print(f"  {definition.attribute} -> {definition.path}")
    
    def _deploy_cognito(self, config: Dict):
        """Deploy Cognito with auto SSM export"""
        ssm_config = EnhancedSsmConfig(config, "cognito", config["cognito"]["name"])
        
        # Simulate Cognito creation
        cognito_resources = {
            "user_pool_id": "us-east-1_ABC123",
            "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC123",
            "user_pool_client_id": "client123"
        }
        
        # Show what would be exported
        export_definitions = ssm_config.get_export_definitions()
        print(f"\nCognito Auto-Export Definitions:")
        for definition in export_definitions:
            if definition.attribute in cognito_resources:
                print(f"  {definition.attribute} -> {definition.path}")


class DemoApplicationStack(Stack):
    """
    Demo application stack that imports from infrastructure and exports its own resources
    Uses mixed auto and manual configuration
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Mixed configuration - auto imports with some custom exports
        config = {
            "ssm": {
                "enabled": True,
                "organization": "demo-app",
                "environment": os.getenv("DEPLOY_ENV", "dev"),
                "auto_import": True,
                "exports": {
                    "api_gateway_id": "auto",
                    "api_gateway_arn": "auto",
                    "custom_endpoint": "/demo-app/api/custom-endpoint"
                }
            },
            "api_gateway": {
                "name": "main-api"
            },
            "lambda": {
                "name": "api-handler"
            }
        }
        
        self._deploy_api_gateway(config)
        self._deploy_lambda(config)
    
    def _deploy_api_gateway(self, config: Dict):
        """Deploy API Gateway with auto import of Cognito and auto export"""
        ssm_config = EnhancedSsmConfig(config, "api_gateway", config["api_gateway"]["name"])
        
        # Show what would be imported
        import_definitions = ssm_config.get_import_definitions()
        print(f"\nAPI Gateway Auto-Import Definitions:")
        for definition in import_definitions:
            print(f"  {definition.attribute} <- {definition.path}")
        
        # Simulate API Gateway creation
        api_resources = {
            "api_gateway_id": "api123456",
            "api_gateway_arn": "arn:aws:apigateway:us-east-1::/restapis/api123456",
            "root_resource_id": "root123",
            "custom_endpoint": "https://api123456.execute-api.us-east-1.amazonaws.com/prod"
        }
        
        # Show what would be exported
        export_definitions = ssm_config.get_export_definitions()
        print(f"\nAPI Gateway Export Definitions:")
        for definition in export_definitions:
            if definition.attribute in api_resources:
                print(f"  {definition.attribute} -> {definition.path}")
    
    def _deploy_lambda(self, config: Dict):
        """Deploy Lambda with auto import of VPC resources"""
        ssm_config = EnhancedSsmConfig(config, "lambda", config["lambda"]["name"])
        
        # Show what would be imported
        import_definitions = ssm_config.get_import_definitions()
        print(f"\nLambda Auto-Import Definitions:")
        for definition in import_definitions:
            print(f"  {definition.attribute} <- {definition.path}")
        
        # Simulate Lambda creation
        lambda_resources = {
            "function_name": "demo-app-api-handler",
            "function_arn": "arn:aws:lambda:us-east-1:123456789012:function:demo-app-api-handler"
        }
        
        # Show what would be exported
        export_definitions = ssm_config.get_export_definitions()
        print(f"\nLambda Export Definitions:")
        for definition in export_definitions:
            if definition.attribute in lambda_resources:
                print(f"  {definition.attribute} -> {definition.path}")


class DemoCustomPatternStack(Stack):
    """
    Demo stack showing custom pattern configuration
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Custom pattern configuration
        config = {
            "ssm": {
                "enabled": True,
                "organization": "acme-corp",
                "environment": "production",
                "pattern": "/{organization}/{environment}/{resource_name}-{attribute}",
                "auto_export": True,
                "exports": {
                    "db_instance_id": "auto",
                    "db_endpoint": "auto",
                    "legacy_connection_string": "/legacy/database/connection-string"
                }
            },
            "rds": {
                "name": "user-database"
            }
        }
        
        self._deploy_rds(config)
    
    def _deploy_rds(self, config: Dict):
        """Deploy RDS with custom pattern"""
        ssm_config = EnhancedSsmConfig(config, "rds", config["rds"]["name"])
        
        print(f"\nCustom Pattern Configuration:")
        print(f"  Pattern: {ssm_config.pattern}")
        
        # Show what would be imported
        import_definitions = ssm_config.get_import_definitions()
        print(f"\nRDS Auto-Import Definitions:")
        for definition in import_definitions:
            print(f"  {definition.attribute} <- {definition.path}")
        
        # Simulate RDS creation
        rds_resources = {
            "db_instance_id": "user-db-prod",
            "db_endpoint": "user-db-prod.cluster-xyz.us-east-1.rds.amazonaws.com",
            "db_port": "5432",
            "legacy_connection_string": "postgresql://user:pass@host:5432/db"
        }
        
        # Show what would be exported
        export_definitions = ssm_config.get_export_definitions()
        print(f"\nRDS Export Definitions (Custom Pattern):")
        for definition in export_definitions:
            if definition.attribute in rds_resources:
                print(f"  {definition.attribute} -> {definition.path}")


def main():
    """Demonstrate the enhanced SSM parameter pattern"""
    
    print("=" * 80)
    print("Enhanced SSM Parameter Pattern Demo")
    print("=" * 80)
    
    app = App()
    
    # Set environment for demo
    os.environ["DEPLOY_ENV"] = "dev"
    
    print("\n1. Infrastructure Stack (Minimal Config - Auto Discovery)")
    print("-" * 60)
    DemoInfrastructureStack(app, "DemoInfrastructureStack")
    
    print("\n2. Application Stack (Mixed Auto/Manual Config)")
    print("-" * 60)
    DemoApplicationStack(app, "DemoApplicationStack")
    
    print("\n3. Custom Pattern Stack")
    print("-" * 60)
    DemoCustomPatternStack(app, "DemoCustomPatternStack")
    
    print("\n" + "=" * 80)
    print("Demo Complete - Review the SSM parameter paths above")
    print("=" * 80)


if __name__ == "__main__":
    main()
