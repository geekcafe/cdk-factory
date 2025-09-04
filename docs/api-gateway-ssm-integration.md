# API Gateway SSM Integration Documentation

## Overview

The CDK Factory now provides centralized API Gateway integration with comprehensive SSM (Systems Manager) Parameter Store support. This enhancement enables seamless cross-stack API Gateway references while maintaining backward compatibility with existing configurations.

## Key Features

### 1. SSM Import/Export Support
- **Import**: Retrieve API Gateway IDs, authorizer IDs, and root resource IDs from SSM parameters
- **Export**: Automatically export API Gateway configuration to SSM parameters for cross-stack references
- **Fallback Chain**: Three-tier fallback mechanism for maximum flexibility

### 2. Fallback Mechanism (Priority Order)
1. **Direct config values** (highest priority) - Manual configuration in JSON files
2. **SSM parameter lookup** - Retrieved from AWS Systems Manager Parameter Store
3. **Environment variable fallback** (lowest priority) - Environment variables with configurable names

### 3. Cross-Stack References
- Standardized SSM parameter naming convention
- Automatic export when `export_to_ssm` is enabled
- Support for multiple stacks referencing the same API Gateway

## Configuration Options

### API Gateway Configuration

```json
{
  "api_gateway": {
    "id": "direct-api-gateway-id",
    "id_ssm_path": "/movatra/infrastructure/api-gateway/id",
    "id_env_var": "API_GATEWAY_ID",
    
    "root_resource_id": "direct-root-resource-id",
    "root_resource_id_ssm_path": "/movatra/infrastructure/api-gateway/root-resource-id",
    "root_resource_id_env_var": "API_GATEWAY_ROOT_RESOURCE_ID",
    
    "authorizer": {
      "id": "direct-authorizer-id",
      "id_ssm_path": "/movatra/infrastructure/api-gateway/authorizer/id",
      "id_env_var": "COGNITO_AUTHORIZER_ID"
    },
    
    "export_to_ssm": true
  }
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | string | - | Direct API Gateway ID |
| `id_ssm_path` | string | - | SSM path for API Gateway ID |
| `id_env_var` | string | `"API_GATEWAY_ID"` | Environment variable name for API Gateway ID |
| `root_resource_id` | string | - | Direct root resource ID |
| `root_resource_id_ssm_path` | string | - | SSM path for root resource ID |
| `root_resource_id_env_var` | string | `"API_GATEWAY_ROOT_RESOURCE_ID"` | Environment variable name for root resource ID |
| `authorizer.id` | string | - | Direct authorizer ID |
| `authorizer.id_ssm_path` | string | - | SSM path for authorizer ID |
| `authorizer.id_env_var` | string | `"COGNITO_AUTHORIZER_ID"` | Environment variable name for authorizer ID |
| `export_to_ssm` | boolean | `false` | Whether to export API Gateway config to SSM |

## Usage Examples

### Example 1: Infrastructure Stack (Exports API Gateway)

Create an infrastructure stack that exports API Gateway configuration:

```json
{
  "name": "infrastructure-stack",
  "api_gateway": {
    "api_gateway_name": "main-api",
    "description": "Main API Gateway for all services",
    "export_to_ssm": true,
    "cognito_authorizer": {
      "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC123DEF",
      "authorizer_name": "MainAuthorizer"
    }
  }
}
```

This will automatically export the following SSM parameters:
- `/movatra/infrastructure-stack/api-gateway/id`
- `/movatra/infrastructure-stack/api-gateway/arn`
- `/movatra/infrastructure-stack/api-gateway/root-resource-id`
- `/movatra/infrastructure-stack/api-gateway/authorizer/id`

### Example 2: Lambda Stack (Imports API Gateway)

Create a Lambda stack that imports the API Gateway from the infrastructure stack:

```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id_ssm_path": "/movatra/infrastructure-stack/api-gateway/id",
    "root_resource_id_ssm_path": "/movatra/infrastructure-stack/api-gateway/root-resource-id",
    "authorizer": {
      "id_ssm_path": "/movatra/infrastructure-stack/api-gateway/authorizer/id"
    }
  },
  "lambda_functions": [
    {
      "name": "get-user",
      "src": "src/handlers/users",
      "handler": "get_user.handler",
      "api": {
        "method": "GET",
        "route": "/users/{id}",
        "authorization_type": "COGNITO"
      }
    }
  ]
}
```

### Example 3: Environment Variable Fallback

For development or CI/CD environments, use environment variables:

```bash
export API_GATEWAY_ID="abcd1234ef"
export API_GATEWAY_ROOT_RESOURCE_ID="xyz789"
export COGNITO_AUTHORIZER_ID="auth123"
```

```json
{
  "name": "dev-lambda-stack",
  "api_gateway": {
    "id_env_var": "API_GATEWAY_ID",
    "root_resource_id_env_var": "API_GATEWAY_ROOT_RESOURCE_ID",
    "authorizer": {
      "id_env_var": "COGNITO_AUTHORIZER_ID"
    }
  }
}
```

### Example 4: Custom SSM Paths

Use custom SSM parameter paths for different environments:

```json
{
  "name": "production-lambda-stack",
  "api_gateway": {
    "id_ssm_path": "/myapp/prod/api-gateway/main-api-id",
    "root_resource_id_ssm_path": "/myapp/prod/api-gateway/main-api-root-resource",
    "authorizer": {
      "id_ssm_path": "/myapp/prod/cognito/main-authorizer-id"
    }
  }
}
```

## Deployment Patterns

### Pattern 1: Infrastructure-First Deployment

1. **Deploy Infrastructure Stack** (creates and exports API Gateway)
   ```bash
   cdk deploy infrastructure-stack
   ```

2. **Deploy Service Stacks** (import API Gateway via SSM)
   ```bash
   cdk deploy user-service-stack
   cdk deploy order-service-stack
   cdk deploy notification-service-stack
   ```

### Pattern 2: Environment-Based Deployment

1. **Set Environment Variables**
   ```bash
   export API_GATEWAY_ID=$(aws apigateway get-rest-apis --query 'items[?name==`main-api`].id' --output text)
   export API_GATEWAY_ROOT_RESOURCE_ID=$(aws apigateway get-resources --rest-api-id $API_GATEWAY_ID --query 'items[?path==`/`].id' --output text)
   ```

2. **Deploy Stacks**
   ```bash
   cdk deploy --all
   ```

## Migration Guide

### Migrating from Direct Configuration

**Before (Direct Configuration):**
```json
{
  "api_gateway": {
    "id": "abcd1234ef",
    "root_resource_id": "xyz789"
  }
}
```

**After (SSM Configuration):**
```json
{
  "api_gateway": {
    "id_ssm_path": "/movatra/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/movatra/infrastructure/api-gateway/root-resource-id"
  }
}
```

### Migrating from Environment Variables

**Before (Environment Variables Only):**
```bash
export API_GATEWAY_ID="abcd1234ef"
```

**After (Configurable Environment Variables):**
```json
{
  "api_gateway": {
    "id_env_var": "CUSTOM_API_GATEWAY_ID"
  }
}
```

```bash
export CUSTOM_API_GATEWAY_ID="abcd1234ef"
```

## Best Practices

### 1. SSM Parameter Naming Convention

Use a consistent naming convention for SSM parameters:
```
/organization/environment/service/resource-type/parameter-name
```

Examples:
- `/movatra/prod/api-gateway/id`
- `/movatra/staging/cognito/user-pool-arn`
- `/mycompany/dev/infrastructure/api-gateway/authorizer-id`

### 2. Environment Separation

Use different SSM paths for different environments:

```json
{
  "production": {
    "api_gateway": {
      "id_ssm_path": "/movatra/prod/api-gateway/id"
    }
  },
  "staging": {
    "api_gateway": {
      "id_ssm_path": "/movatra/staging/api-gateway/id"
    }
  }
}
```

### 3. Fallback Strategy

Configure multiple fallback options for maximum flexibility:

```json
{
  "api_gateway": {
    "id": "fallback-direct-id",
    "id_ssm_path": "/movatra/prod/api-gateway/id",
    "id_env_var": "API_GATEWAY_ID"
  }
}
```

### 4. Export Configuration

Only enable SSM export in infrastructure stacks:

```json
{
  "infrastructure-stack": {
    "api_gateway": {
      "export_to_ssm": true
    }
  },
  "service-stacks": {
    "api_gateway": {
      "export_to_ssm": false,
      "id_ssm_path": "/movatra/infrastructure/api-gateway/id"
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **SSM Parameter Not Found**
   ```
   Error: Failed to retrieve API Gateway ID from SSM path /path/to/param
   ```
   
   **Solution**: Ensure the SSM parameter exists and the stack has read permissions.

2. **Missing Root Resource ID**
   ```
   Error: API Gateway requires 'root_resource_id' in configuration
   ```
   
   **Solution**: Provide `root_resource_id` via direct config, SSM, or environment variable.

3. **Authorization Failures**
   ```
   Error: User pool ID is required for API Gateway authorizer
   ```
   
   **Solution**: Configure `user_pool_id` or `user_pool_arn` in the cognito_authorizer section.

### Debug Configuration

Enable debug logging to see which configuration source is being used:

```python
import logging
logging.getLogger('ApiGatewayIntegrationUtility').setLevel(logging.DEBUG)
```

This will show log messages like:
```
INFO: Using existing API Gateway ID from SSM: abcd1234ef
INFO: Found authorizer ID from environment variable COGNITO_AUTHORIZER_ID: auth123
```

## API Reference

### ApiGatewayIntegrationUtility Methods

#### `_get_existing_api_gateway_id_with_ssm_fallback(api_config, stack_config)`
Retrieves API Gateway ID using the fallback chain.

#### `_get_existing_authorizer_id_with_ssm_fallback(api_config, stack_config)`
Retrieves authorizer ID using the fallback chain.

#### `_get_root_resource_id_with_ssm_fallback(stack_config)`
Retrieves root resource ID using the fallback chain.

#### `export_api_gateway_to_ssm(api_gateway, authorizer, stack_config, export_prefix)`
Exports API Gateway configuration to SSM parameters.

**Parameters:**
- `api_gateway`: RestApi instance
- `authorizer`: Optional Authorizer instance
- `stack_config`: Stack configuration object
- `export_prefix`: Optional custom SSM path prefix

**Returns:**
Dictionary with exported parameter names:
```python
{
  "api_gateway_id": "/path/to/api-gateway/id",
  "api_gateway_arn": "/path/to/api-gateway/arn",
  "root_resource_id": "/path/to/api-gateway/root-resource-id",
  "authorizer_id": "/path/to/api-gateway/authorizer/id"
}
```

## Backward Compatibility

All existing configurations continue to work without modification. The new SSM features are opt-in and do not affect existing deployments.

### Existing Configuration Support

- Direct configuration values (`id`, `root_resource_id`, etc.)
- Environment variables (`API_GATEWAY_ID`, `COGNITO_AUTHORIZER_ID`, etc.)
- All existing API Gateway stack features and options

### New Features

- SSM parameter import/export
- Configurable environment variable names
- Cross-stack references
- Automatic fallback chain

## Security Considerations

### IAM Permissions

Ensure your CDK deployment role has the necessary SSM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter"
      ],
      "Resource": [
        "arn:aws:ssm:*:*:parameter/movatra/*",
        "arn:aws:ssm:*:*:parameter/your-org/*"
      ]
    }
  ]
}
```

### Parameter Store Security

- Use SecureString parameters for sensitive values
- Implement least-privilege access policies
- Use parameter hierarchies for organization
- Enable parameter store logging for audit trails

## Support

For questions or issues related to API Gateway SSM integration:

1. Check the troubleshooting section above
2. Review the configuration examples
3. Enable debug logging to see configuration resolution
4. Verify IAM permissions for SSM access
