# SSM Parameter Pattern for CDK Factory

## Overview

This document describes the standardized pattern for exporting and consuming AWS SSM Parameter Store values across multiple CDK stacks in the CDK Factory framework. Using SSM parameters enables lighter coupling between stacks compared to CloudFormation Outputs, making stacks more modular and independently deployable.

## Implementation Components

### 1. Base Configuration Class

The `BaseConfig` class provides a foundation for all resource configurations with standardized access to SSM parameter paths:

```python
# src/cdk_factory/configurations/base_config.py
class BaseConfig:
    # ...
    
    @property
    def ssm_exports(self) -> Dict[str, str]:
        """
        Get the SSM parameter paths for values this resource exports.
        
        The SSM exports dictionary maps resource attributes to SSM parameter paths
        where this resource's values will be published.
        
        For example:
        {
            "vpc_id_path": "/my-app/vpc/id",
            "subnet_ids_path": "/my-app/vpc/subnet-ids"
        }
        """
        return self.__config.get("ssm_exports", {})
    
    @property
    def ssm_imports(self) -> Dict[str, str]:
        """
        Get the SSM parameter paths for values this resource imports/consumes.
        
        The SSM imports dictionary maps resource attributes to SSM parameter paths
        where this resource will look for values published by other stacks.
        
        For example:
        {
            "vpc_id_path": "/my-app/vpc/id",
            "user_pool_arn_path": "/my-app/cognito/user-pool-arn"
        }
        """
        return self.__config.get("ssm_imports", {})
    
    @property
    def ssm_parameters(self) -> Dict[str, str]:
        """
        Get all SSM parameter path mappings (both exports and imports).
        This is provided for backward compatibility.
        """
        # Merge exports and imports, with exports taking precedence
        combined = {**self.ssm_imports, **self.ssm_exports}
        # Also include any parameters directly under ssm_parameters for backward compatibility
        combined.update(self.__config.get("ssm_parameters", {}))
        return combined
    
    def get_export_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for exporting a specific attribute.
        """
        path_key = f"{key}_path"
        return self.ssm_exports.get(path_key)
    
    def get_import_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for importing a specific attribute.
        """
        path_key = f"{key}_path"
        return self.ssm_imports.get(path_key)
    
    def get_ssm_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for a specific attribute (checks both exports and imports).
        This is provided for backward compatibility.
        """
        path_key = f"{key}_path"
        # Check exports first, then imports, then the legacy ssm_parameters
        return self.ssm_exports.get(path_key) or self.ssm_imports.get(path_key) or self.__config.get("ssm_parameters", {}).get(path_key)
```

### 2. SSM Parameter Mixin

The `SsmParameterMixin` class provides reusable methods for exporting and importing SSM parameters:

```python
# src/cdk_factory/interfaces/ssm_parameter_mixin.py
class SsmParameterMixin:
    def export_ssm_parameter(self, scope, id, value, parameter_name, description=None, string_list_value=False):
        # Creates an SSM parameter
        
    def import_ssm_parameter(self, scope, id, parameter_name, version=None):
        # Imports an SSM parameter value
        
    def export_ssm_parameters_from_config(self, scope, config_dict, ssm_config, prefix=""):
        # Exports multiple SSM parameters based on a configuration dictionary
        
    def export_resource_to_ssm(self, scope, resource_values, config, resource_name):
        # Higher-level method that makes it clear we're exporting values
        # First tries to use the ssm_exports property, then falls back to ssm_parameters
        
    def import_resources_from_ssm(self, scope, config, resource_name):
        # Higher-level method that makes it clear we're importing values
        # First tries to use the ssm_imports property, then falls back to ssm_parameters
```

## Configuration Structure

The SSM parameter paths are defined in the configuration JSON under two distinct dictionaries:

1. `ssm_exports`: Parameters that this stack will publish to SSM
2. `ssm_imports`: Parameters that this stack will consume from SSM

Each key in these dictionaries should follow the pattern `{attribute_name}_path` and the value should be the SSM parameter path.

Example configuration for a VPC stack that exports values:

```json
{
  "vpc": {
    "name": "main-vpc",
    "cidr": "10.0.0.0/16",
    "ssm_exports": {
      "vpc_id_path": "/my-app/dev/vpc/id",
      "vpc_cidr_path": "/my-app/dev/vpc/cidr",
      "public_subnet_ids_path": "/my-app/dev/vpc/public-subnet-ids"
    }
  }
}
```

Example configuration for an API Gateway stack that imports values:

```json
{
  "api_gateway": {
    "name": "my-app-api",
    "vpc": {
      "ssm_imports": {
        "vpc_id_path": "/my-app/dev/vpc/id",
        "subnet_ids_path": "/my-app/dev/vpc/private-subnet-ids"
      }
    }
  }
}
```

For backward compatibility, the `ssm_parameters` dictionary is still supported and will be treated as both exports and imports.
```

## Usage Pattern

### 1. Configuration

In your stack configuration JSON, define SSM parameter paths using the `ssm_exports` and `ssm_imports` keys:

```json
{
  "vpc": {
    "name": "my-vpc",
    "cidr": "10.0.0.0/16",
    "ssm_exports": {
      "vpc_id_path": "/my-app/vpc/id",
      "vpc_cidr_path": "/my-app/vpc/cidr",
      "public_subnet_ids_path": "/my-app/vpc/public-subnet-ids"
    },
    "ssm_imports": {
      "subnet_ids_path": "/my-app/vpc/private-subnet-ids"
    }
  }
}
```

### 2. Resource Configuration Class

Ensure your resource configuration class inherits from `BaseConfig` to get access to the SSM exports and imports properties:

```python
from cdk_factory.configurations.base_config import BaseConfig

class VpcConfig(BaseConfig):
    # Resource-specific properties and methods
    # The ssm_exports and ssm_imports properties are inherited from BaseConfig
    pass
```

### 3. Stack Implementation

Make your stack class inherit from `SsmParameterMixin` and implement parameter export using the clearer methods:

```python
from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin

class VpcStack(IStack, SsmParameterMixin):
    # ...
    
    def _export_ssm_parameters(self, resource_name: str) -> None:
        # Create a dictionary of resources to export
        resources = {
            'resource_id': self.resource.id,
            'other_attribute': self.resource.other_attribute,
        }
        
        # Export all resources to SSM using the clearer method
        self.export_resource_to_ssm(
            scope=self,
            resource_values=resources,
            config=self.resource_config,
            resource_name=resource_name
        )
```

### 4. Consuming SSM Parameters

To consume SSM parameters from another stack:

```python
from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin

class ConsumerStack(IStack, SsmParameterMixin):
    # ...
    
    def _import_vpc_resources(self) -> Dict[str, str]:
        # Import all VPC resources defined in the configuration
        vpc_resources = self.import_resources_from_ssm(
            scope=self,
            config=self.consumer_config,
            resource_name="vpc"
        )
        
        # Now you can access the imported values
        vpc_id = vpc_resources.get('vpc_id')
        subnet_ids = vpc_resources.get('subnet_ids')
        
        # You can also import individual parameters if needed
        vpc_id_path = self.consumer_config.get_import_path("vpc_id")
        
        if vpc_id_path and not vpc_id:
            # Import the VPC ID from SSM if not already imported
            vpc_id = self.import_ssm_parameter(
                scope=self,
                id="ImportedVpcId",
                parameter_name=vpc_id_path
            )
            
        # Fall back to direct configuration if no SSM path is provided or import failed
        if not vpc_id:
            vpc_id = self.consumer_config.get("vpc_id")
            
        return vpc_resources
```

## Best Practices

1. **Clear Export/Import Distinction**: Use `ssm_exports` and `ssm_imports` dictionaries to clearly indicate which parameters are being published versus consumed:
   - `ssm_exports` for parameters the stack will write to SSM
   - `ssm_imports` for parameters the stack will read from SSM

2. **Consistent Parameter Naming**: Use a consistent naming pattern for SSM parameters:
   - `/[app-name]/[environment]/[resource-type]/[attribute]`
   - Example: `/my-app/dev/vpc/id`, `/my-app/prod/cognito/user-pool-arn`

3. **Path Keys in Configuration**: Always suffix SSM parameter path keys with `_path`:
   - `vpc_id_path` for the path to the VPC ID
   - `user_pool_arn_path` for the path to the Cognito User Pool ARN

4. **Use Helper Methods**: Use the provided helper methods for clarity:
   - `export_resource_to_ssm()` when exporting resources
   - `import_resources_from_ssm()` when importing resources
   - `get_export_path()` and `get_import_path()` when accessing specific paths

5. **Graceful Fallbacks**: When consuming parameters, provide fallbacks if the SSM parameter path is not configured or the parameter doesn't exist.

6. **Documentation**: Document which SSM parameters each stack exports and imports in the stack's README or documentation.

7. **Testing**: Include tests that verify both the export and import of SSM parameters.

## Example Implementation

See the following files for example implementations:

- `src/cdk_factory/configurations/base_config.py` - Base configuration with SSM support
- `src/cdk_factory/interfaces/ssm_parameter_mixin.py` - SSM parameter mixin
- `src/cdk_factory/configurations/resources/vpc.py` - VPC configuration with SSM support
- `src/cdk_factory/stack_library/vpc/vpc_stack.py` - VPC stack with SSM parameter export
