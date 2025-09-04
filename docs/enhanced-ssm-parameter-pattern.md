# Enhanced SSM Parameter Pattern for CDK Factory

## Overview

This enhanced pattern provides both prescriptive defaults for easy adoption and flexible customization for advanced use cases. It supports automatic export/import with multi-environment patterns while maintaining backward compatibility.

## Design Principles

1. **Convention over Configuration**: Sensible defaults that work out of the box
2. **Environment-Aware**: Built-in support for multi-environment deployments
3. **Flexible Override**: Allow custom patterns when needed
4. **Automatic Discovery**: Auto-detect what to export/import based on resource types
5. **Type Safety**: Strongly typed parameter definitions

## Core Components

### 1. SSM Parameter Conventions

#### Default Pattern
```
/{organization}/{environment}/{stack-type}/{resource-name}/{attribute}
```

#### Examples
```
/cdk-factory/dev/vpc/main/id
/cdk-factory/prod/api-gateway/main/id
/cdk-factory/staging/rds/user-db/endpoint
```

### 2. Enhanced Configuration Structure

```json
{
  "ssm": {
    "enabled": true,
    "organization": "cdk-factory",
    "environment": "${ENVIRONMENT}",
    "auto_export": true,
    "auto_import": true,
    "pattern": "/{organization}/{environment}/{stack_type}/{resource_name}/{attribute}",
    "exports": {
      "vpc_id": "auto",
      "vpc_cidr": "auto",
      "custom_value": "/custom/path/to/parameter"
    },
    "imports": {
      "vpc_id": "auto",
      "security_group_id": "/custom/path/from/another/stack"
    }
  }
}
```

### 3. Auto-Discovery Mechanism

The system automatically determines what to export/import based on:
- Resource type (VPC, RDS, API Gateway, etc.)
- Standard attributes for each resource type
- Configuration hints from the user

## Implementation

### Enhanced Base Configuration

```python
# src/cdk_factory/configurations/enhanced_ssm_config.py
from typing import Dict, List, Optional, Union
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
            import os
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
```

### Enhanced SSM Parameter Mixin

```python
# src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py
from typing import Dict, List, Any, Optional
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from .enhanced_ssm_config import EnhancedSsmConfig, SsmParameterDefinition

class EnhancedSsmParameterMixin:
    """Enhanced SSM parameter mixin with auto-discovery and flexible patterns"""
    
    def setup_ssm_integration(self, scope: Construct, config: Dict, resource_type: str, resource_name: str):
        """Setup SSM integration for a resource"""
        self.ssm_config = EnhancedSsmConfig(config, resource_type, resource_name)
        self.scope = scope
        
    def auto_export_resources(self, resource_values: Dict[str, Any]) -> Dict[str, str]:
        """Automatically export resources based on configuration"""
        if not self.ssm_config.enabled:
            return {}
            
        exported_params = {}
        export_definitions = self.ssm_config.get_export_definitions()
        
        for definition in export_definitions:
            if definition.attribute in resource_values:
                value = resource_values[definition.attribute]
                if value is not None:
                    param = self._create_ssm_parameter(
                        definition.path,
                        value,
                        definition.description or f"{definition.attribute} for {self.ssm_config.resource_name}",
                        definition.parameter_type
                    )
                    exported_params[definition.attribute] = definition.path
                    
        return exported_params
    
    def auto_import_resources(self) -> Dict[str, Any]:
        """Automatically import resources based on configuration"""
        if not self.ssm_config.enabled:
            return {}
            
        imported_values = {}
        import_definitions = self.ssm_config.get_import_definitions()
        
        for definition in import_definitions:
            try:
                value = self._import_ssm_parameter(definition.path)
                if value:
                    imported_values[definition.attribute] = value
            except Exception as e:
                # Log warning but continue - allows for optional imports
                print(f"Warning: Could not import {definition.path}: {e}")
                
        return imported_values
    
    def _create_ssm_parameter(self, path: str, value: Any, description: str, param_type: str = "String") -> ssm.StringParameter:
        """Create an SSM parameter"""
        # Handle different value types
        if isinstance(value, list):
            string_value = ",".join(str(v) for v in value)
            param_type = "StringList"
        else:
            string_value = str(value)
            
        return ssm.StringParameter(
            self.scope,
            f"ssm-param-{path.replace('/', '-')}",
            parameter_name=path,
            string_value=string_value,
            description=description,
            type=ssm.ParameterType.STRING_LIST if param_type == "StringList" else ssm.ParameterType.STRING
        )
    
    def _import_ssm_parameter(self, path: str) -> Optional[str]:
        """Import an SSM parameter value"""
        try:
            param = ssm.StringParameter.from_string_parameter_name(
                self.scope,
                f"imported-param-{path.replace('/', '-')}",
                path
            )
            return param.string_value
        except Exception:
            return None
```

## Usage Examples

### 1. Minimal Configuration (Uses All Defaults)

```json
{
  "vpc": {
    "name": "main-vpc",
    "cidr": "10.0.0.0/16",
    "ssm": {
      "enabled": true
    }
  }
}
```

This automatically:
- Exports: `vpc_id`, `vpc_cidr`, `public_subnet_ids`, `private_subnet_ids`
- Uses pattern: `/cdk-factory/dev/vpc/main-vpc/{attribute}`

### 2. Environment-Specific Configuration

```json
{
  "ssm": {
    "enabled": true,
    "environment": "${DEPLOY_ENV}",
    "organization": "mycompany"
  },
  "vpc": {
    "name": "main-vpc",
    "cidr": "10.0.0.0/16"
  }
}
```

With `DEPLOY_ENV=production`, exports to:
- `/mycompany/production/vpc/main-vpc/vpc_id`
- `/mycompany/production/vpc/main-vpc/vpc_cidr`

### 3. Custom Pattern Configuration

```json
{
  "ssm": {
    "enabled": true,
    "pattern": "/{organization}/{environment}/{resource_name}-{attribute}",
    "organization": "acme",
    "environment": "prod"
  },
  "api_gateway": {
    "name": "main-api"
  }
}
```

Exports to:
- `/acme/prod/main-api-api_gateway_id`
- `/acme/prod/main-api-root_resource_id`

### 4. Mixed Auto and Manual Configuration

```json
{
  "ssm": {
    "enabled": true,
    "auto_export": true,
    "exports": {
      "vpc_id": "auto",
      "vpc_cidr": "auto", 
      "custom_tag": "/custom/path/vpc-tag"
    },
    "imports": {
      "security_group_id": "/external/system/sg-id"
    }
  },
  "rds": {
    "name": "user-db"
  }
}
```

### 5. Cross-Stack Reference Pattern

**Infrastructure Stack:**
```json
{
  "ssm": {
    "enabled": true,
    "organization": "myapp",
    "environment": "prod"
  },
  "vpc": {
    "name": "infrastructure"
  }
}
```

**Application Stack:**
```json
{
  "ssm": {
    "enabled": true,
    "organization": "myapp", 
    "environment": "prod",
    "imports": {
      "vpc_id": "auto"
    }
  },
  "lambda": {
    "name": "api-handler"
  }
}
```

The Lambda stack automatically imports from `/myapp/prod/vpc/infrastructure/vpc_id`.

## Stack Implementation Example

```python
class VpcStack(IStack, EnhancedSsmParameterMixin):
    def build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig):
        # Setup SSM integration
        self.setup_ssm_integration(
            scope=self,
            config=stack_config.dictionary,
            resource_type="vpc",
            resource_name=stack_config.vpc.name
        )
        
        # Import any required resources
        imported_resources = self.auto_import_resources()
        
        # Create VPC (implementation details...)
        vpc = self._create_vpc(stack_config.vpc)
        
        # Auto-export resources
        resource_values = {
            "vpc_id": vpc.vpc_id,
            "vpc_cidr": vpc.vpc_cidr_block,
            "public_subnet_ids": [subnet.subnet_id for subnet in vpc.public_subnets],
            "private_subnet_ids": [subnet.subnet_id for subnet in vpc.private_subnets]
        }
        
        exported_params = self.auto_export_resources(resource_values)
        print(f"Exported SSM parameters: {exported_params}")
```

## Migration Path

### Phase 1: Backward Compatibility
- Keep existing `ssm_exports`/`ssm_imports` working
- Add enhanced configuration as opt-in

### Phase 2: Enhanced Defaults
- Enable auto-discovery by default
- Provide migration utilities

### Phase 3: Full Adoption
- Deprecate old pattern (with warnings)
- Enhanced pattern becomes default

## Benefits

1. **Zero Configuration**: Works out of the box with sensible defaults
2. **Environment Aware**: Built-in multi-environment support
3. **Flexible**: Can override any part of the pattern
4. **Type Safe**: Strongly typed parameter definitions
5. **Auto-Discovery**: Automatically determines what to export/import
6. **Consistent**: Enforces consistent naming patterns across teams
7. **Backward Compatible**: Existing configurations continue to work

This enhanced pattern provides the best of both worlds - prescriptive defaults for easy adoption and flexible customization for advanced use cases.
