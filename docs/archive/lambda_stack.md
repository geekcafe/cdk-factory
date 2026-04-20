# Lambda Stack Documentation

## Overview

The Lambda Stack (`lambda_stack.py`) provides comprehensive AWS Lambda function deployment with automatic API Gateway integration, event triggers, and SQS queue management. It supports both ZIP-based and Docker container deployments with flexible configuration options.

## Features

- **Automatic API Gateway Integration**: Creates REST API endpoints when `api` configuration is present
- **Event-Driven Triggers**: Support for EventBridge, SQS, and scheduled events
- **Docker & ZIP Deployments**: Flexible deployment options with ECR integration
- **Existing Infrastructure Integration**: Reference existing API Gateways and authorizers
- **Cognito Authorization**: Automatic Cognito User Pool authorizer setup
- **CORS Configuration**: Built-in CORS support for web applications
- **Environment Variables**: Dynamic environment variable injection
- **Layer Support**: Lambda layer management and attachment

## Configuration Structure

### Stack Configuration

```json
{
  "name": "my-lambda-stack",
  "module": "lambda_stack",
  "enabled": true,
  "api_gateway": {
    "existing_api_id": "{{API_GATEWAY_ID}}",
    "existing_api_arn": "{{API_GATEWAY_ARN}}",
    "authorizer": {
      "id": "{{COGNITO_AUTHORIZER_ID}}",
      "type": "COGNITO"
    }
  },
  "resources": [
    // Lambda function configurations
  ]
}
```

### Lambda Function Configuration

```json
{
  "name": "my-function",
  "src": "src/handlers/my_function",
  "handler": "handler.lambda_handler",
  "description": "My Lambda Function",
  "runtime": "python3.11",
  "timeout": 30,
  "memory_size": 256,
  "environment_variables": [
    {"name": "ENV_VAR", "value": "value"}
  ],
  "api": {
    "routes": "/api/my-endpoint",
    "method": "POST",
    "authorization_type": "COGNITO",
    "api_key_required": false,
    "request_parameters": {
      "method.request.header.Authorization": true
    }
  },
  "triggers": [
    {
      "resource_type": "event-bridge",
      "event_pattern": {
        "source": ["my.application"]
      }
    }
  ],
  "sqs": {
    "queues": [
      {
        "name": "my-queue",
        "is_consumer": true,
        "batch_size": 10
      }
    ]
  },
  "schedule": {
    "type": "rate",
    "value": "15 minutes"
  }
}
```

## API Gateway Integration

### Automatic Integration

When an `api` configuration is present in a Lambda function, the stack automatically:

1. **Creates or references API Gateway**: Uses existing API if `existing_api_id` is configured
2. **Sets up Lambda integration**: Configures proxy integration with the Lambda function
3. **Creates resource paths**: Handles nested resource creation from route paths
4. **Configures authorization**: Sets up Cognito authorizers unless skipped
5. **Enables CORS**: Automatic CORS configuration for web applications

### API Configuration Options

| Property | Type | Description | Default |
|----------|------|-------------|---------|
| `routes` | string | API Gateway resource path (e.g., `/users/{id}`) | Required |
| `method` | string | HTTP method (GET, POST, PUT, DELETE, etc.) | Required |
| `authorization_type` | string | Authorization type: `"COGNITO"` (secure) or `"NONE"` (public) | `"COGNITO"` |
| `api_key_required` | boolean | Require API key for access | `false` |
| `request_parameters` | object | Request parameter validation rules | `{}` |
| `api_gateway_id` | string | Reference existing API Gateway by ID | `null` |
| `authorizer_id` | string | Reference existing Cognito authorizer by ID | `null` |

### Existing Infrastructure Integration

#### Option 1: Stack-Level Configuration
Configure existing API Gateway at the stack level:

```json
{
  "api_gateway": {
    "id": "abc123def456",
    "arn": "arn:aws:apigateway:region::/restapis/abc123def456",
    "root_resource_id": "abc123def456root",
    "authorizer": {
      "id": "auth789xyz",
      "type": "COGNITO"
    }
  }
}
```

**Important:** The `root_resource_id` is required for proper API Gateway import. You can find it using:
```bash
aws apigateway get-resources --rest-api-id abc123def456 --query 'items[?path==`/`].id' --output text
```

#### Option 2: Function-Level Configuration
Configure existing infrastructure per Lambda function:

```json
{
  "name": "my-function",
  "src": "src/handlers/my_function",
  "handler": "handler.lambda_handler",
  "api": {
    "route": "/api/endpoint",
    "method": "POST",
    "api_gateway_id": "abc123def456",
    "authorizer_id": "auth789xyz",
    "authorization_type": "COGNITO"
  }
}
```

#### Existing Authorizer Support

The Lambda Stack supports referencing existing Cognito User Pool authorizers using L1 CDK constructs:

- **New Authorizers**: When `authorizer_id` is not provided, creates new `CognitoUserPoolsAuthorizer` using L2 constructs
- **Existing Authorizers**: When `authorizer_id` is provided, uses L1 `CfnMethod` construct with `authorizer_id` parameter

**Technical Implementation:**
- L2 constructs (`resource.add_method()`) are used for new authorizers with full CDK integration
- L1 constructs (`apigateway.CfnMethod`) are used for existing authorizers to bypass L2 limitations
- L1 approach creates CloudFormation resources directly with `AuthorizerId` property
- Lambda permissions are automatically configured for both approaches

**Environment Variables Required:**
- `COGNITO_USER_POOL_ID`: Cognito User Pool ID for new authorizers (not required for existing authorizers)

## Event Triggers

### EventBridge Integration

```json
{
  "triggers": [
    {
      "resource_type": "event-bridge",
      "event_pattern": {
        "source": ["my.application"],
        "detail-type": ["User Action"],
        "detail": {
          "action": ["create", "update"]
        }
      }
    }
  ]
}
```

### Scheduled Events

```json
{
  "schedule": {
    "type": "rate",
    "value": "15 minutes"
  }
}
```

**Schedule Types:**
- `rate`: Rate expressions (e.g., "15 minutes", "1 hour")
- `cron`: Cron expressions (e.g., "0 18 * * ? *")

## SQS Integration

### Queue Configuration

```json
{
  "sqs": {
    "queues": [
      {
        "name": "processing-queue",
        "is_consumer": true,
        "is_producer": false,
        "batch_size": 10,
        "maximum_batching_window_in_seconds": 5,
        "visibility_timeout": 300
      }
    ]
  }
}
```

**Queue Properties:**
- `is_consumer`: Lambda consumes messages from queue
- `is_producer`: Lambda can send messages to queue
- `batch_size`: Number of messages to process in batch
- `maximum_batching_window_in_seconds`: Max time to wait for batch
- `visibility_timeout`: Message visibility timeout

## Docker Deployment

### ECR Configuration

```json
{
  "ecr": {
    "arn": "arn:aws:ecr:region:account:repository/my-repo",
    "repository_name": "my-repo",
    "tag": "latest"
  },
  "deployment_type": "docker"
}
```

### Docker Image Function

The stack automatically handles Docker image deployment when `ecr` configuration is present:

1. **Image URI Construction**: Builds image URI from ECR configuration
2. **Lambda Function Creation**: Creates `DockerImageFunction` with specified configuration
3. **Layer Attachment**: Attaches any configured Lambda layers
4. **Environment Setup**: Injects environment variables and configuration

## Environment Variables

### Dynamic Environment Variables

The stack automatically injects several environment variables:

- `ENVIRONMENT`: Current deployment environment
- `WORKLOAD`: Current workload identifier
- `STACK_NAME`: Current stack name
- Custom variables from `environment_variables` configuration

### Environment Variable Patterns

```json
{
  "environment_variables": {
    "DATABASE_URL": "{{DATABASE_URL}}",
    "API_KEY": "{{API_KEY}}",
    "STATIC_VALUE": "production"
  }
}
```

## Lambda Layers

### Layer Configuration

```json
{
  "layers": [
    {
      "name": "shared-utilities",
      "arn": "arn:aws:lambda:region:account:layer:utilities:1"
    }
  ]
}
```

## Error Handling

### Common Configuration Errors

1. **Missing Source Directory**: Ensure `source_directory` points to valid handler code
2. **Invalid ECR ARN**: Verify ECR repository exists and ARN is correct
3. **Missing Environment Variables**: Required variables for existing infrastructure integration
4. **Invalid Schedule Expression**: Check rate/cron expression syntax

### Validation

The stack performs validation on:
- Source directory existence
- ECR repository accessibility
- Environment variable presence
- Schedule expression syntax
- API Gateway route format

## Best Practices

### Function Organization

1. **Group Related Functions**: Use separate stacks for different functional domains
2. **Consistent Naming**: Use descriptive, consistent naming conventions
3. **Environment Separation**: Separate configurations for different environments

### API Gateway Design

1. **Resource Hierarchy**: Design logical resource hierarchies
2. **HTTP Methods**: Use appropriate HTTP methods for operations
3. **Authorization**: Implement consistent authorization patterns
4. **Error Responses**: Configure proper error response formats

### Performance Optimization

1. **Memory Sizing**: Right-size memory allocation for workload
2. **Timeout Configuration**: Set appropriate timeout values
3. **Cold Start Optimization**: Use provisioned concurrency for critical functions
4. **Layer Usage**: Leverage layers for shared dependencies

## Examples

### Basic Lambda with API Gateway

```json
{
  "name": "user-service",
  "src": "src/handlers/users",
  "handler": "users.lambda_handler",
  "description": "User management service",
  "api": {
    "route": "/users",
    "method": "GET"
  }
}
```

### EventBridge Triggered Function

```json
{
  "name": "event-processor",
  "src": "src/handlers/events",
  "handler": "processor.lambda_handler",
  "description": "Process application events",
  "triggers": [
    {
      "resource_type": "event-bridge",
      "event_pattern": {
        "source": ["myapp.users"],
        "detail-type": ["User Created"]
      }
    }
  ]
}
```

### Scheduled Function with SQS

```json
{
  "name": "batch-processor",
  "src": "src/handlers/batch",
  "handler": "batch.lambda_handler",
  "description": "Batch processing job",
  "schedule": {
    "type": "cron",
    "value": "0 2 * * ? *"
  },
  "sqs": {
    "queues": [
      {
        "name": "batch-queue",
        "is_producer": true
      }
    ]
  }
}
```

### Lambda with Existing Authorizer

```json
{
  "name": "secure-api",
  "src": "src/handlers/secure",
  "handler": "secure.lambda_handler",
  "description": "Secure API using existing authorizer",
  "api": {
    "route": "/secure/data",
    "method": "GET",
    "authorizer_id": "auth123xyz789",
    "authorization_type": "COGNITO"
  }
}
```

## Troubleshooting

### Deployment Issues

1. **Permission Errors**: Verify IAM roles have necessary permissions
2. **Resource Conflicts**: Check for naming conflicts with existing resources
3. **Timeout Errors**: Increase timeout values for long-running operations

### API Gateway Issues

1. **CORS Errors**: Configure CORS settings in API Gateway configuration
2. **Authorization Failures**: Verify Cognito User Pool and authorizer configuration
3. **Route Conflicts**: Check for overlapping API routes
4. **Existing Authorizer Issues**: 
   - Ensure `authorizer_id` is valid and accessible
   - Verify authorizer belongs to the same API Gateway
   - Check that authorization type is `COGNITO_USER_POOLS`

### Testing and Validation

The Lambda Stack now uses real CDK synthesis testing instead of mocks:

- Tests validate actual CloudFormation template generation
- Synthesis tests catch authorization type mismatches and resource conflicts
- Environment variables are properly validated during testing
- Both L1 and L2 construct approaches are tested for authorizer integration

### Runtime Issues

1. **Import Errors**: Verify all dependencies are included in deployment package
2. **Environment Variables**: Check environment variable configuration and values

## Migration Guide

### From Manual API Gateway Setup

1. **Extract Configuration**: Convert manual API Gateway setup to configuration
2. **Reference Existing**: Use `existing_api_id` to reference current API Gateway
3. **Gradual Migration**: Migrate functions one at a time
4. **Test Thoroughly**: Verify all integrations work correctly

### From Other CDK Patterns

1. **Configuration Mapping**: Map existing CDK code to configuration format
2. **Environment Variables**: Extract hardcoded values to environment variables
3. **Resource References**: Convert resource references to configuration patterns
