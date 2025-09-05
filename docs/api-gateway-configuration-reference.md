# API Gateway Configuration Reference

## Quick Start Guide

### Basic Lambda with API Gateway

```json
{
  "name": "my-service-stack",
  "lambda_functions": [
    {
      "name": "hello-world",
      "src": "src/handlers/hello",
      "handler": "index.handler",
      "api": {
        "method": "GET",
        "route": "/hello",
        "authorization_type": "NONE"
      }
    }
  ]
}
```

### Using Existing API Gateway

```json
{
  "name": "my-service-stack",
  "api_gateway": {
    "ssm_imports": {
      "api_id": "/my-cool-app/infrastructure/api-gateway/rest-api/id",
      "root_resource_id": "/my-cool-app/infrastructure/api-gateway/rest-api/root-resource-id"
    }
  },
  "lambda_functions": [
    {
      "name": "get-users",
      "src": "src/handlers/users",
      "handler": "get_users.handler",
      "api": {
        "method": "GET",
        "route": "/users",
        "authorization_type": "COGNITO"
      }
    }
  ]
}
```

## Configuration Hierarchy

The API Gateway integration follows this configuration hierarchy:

1. **Lambda Function Level** - Individual function API settings
2. **Stack Level** - Shared API Gateway configuration
3. **Environment Variables** - Runtime configuration
4. **SSM Parameters** - Cross-stack references

## Lambda Function API Configuration

### Basic API Configuration

```json
{
  "api": {
    "method": "POST",
    "route": "/users",
    "authorization_type": "COGNITO",
    "api_key_required": false,
    "cors": {
      "allow_origins": ["https://myapp.com"],
      "allow_methods": ["POST", "OPTIONS"],
      "allow_headers": ["Content-Type", "Authorization"]
    }
  }
}
```

### API Configuration Options

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `method` | string | `"GET"` | HTTP method (GET, POST, PUT, DELETE, etc.) |
| `route` | string | Required | API Gateway route path (e.g., "/users/{id}") |
| `authorization_type` | string | `"NONE"` | Authorization type (NONE, COGNITO, AWS_IAM) |
| `api_key_required` | boolean | `false` | Whether API key is required |
| `cors` | object | - | CORS configuration |
| `request_parameters` | object | `{}` | Request parameter validation |

### Authorization Types

#### No Authorization
```json
{
  "api": {
    "method": "GET",
    "route": "/public/health",
    "authorization_type": "NONE"
  }
}
```

#### Cognito User Pool Authorization
```json
{
  "api": {
    "method": "GET",
    "route": "/users/profile",
    "authorization_type": "COGNITO"
  }
}
```

#### AWS IAM Authorization
```json
{
  "api": {
    "method": "GET",
    "route": "/admin/users",
    "authorization_type": "AWS_IAM"
  }
}
```

## Stack-Level API Gateway Configuration

### Complete Configuration Example

```json
{
  "api_gateway": {
    "name": "my-api",
    "description": "My Service API",
    "deploy": true,
    "export_to_ssm": true,
    
    "deploy_options": {
      "stage_name": "prod",
      "data_trace_enabled": false,
      "metrics_enabled": true,
      "tracing_enabled": true,
      "throttling_rate_limit": 1000,
      "throttling_burst_limit": 2000
    },
    
    "endpoint_types": ["REGIONAL"],
    "binary_media_types": ["image/*", "application/pdf"],
    "min_compression_size": 1024,
    
    "default_cors_preflight_options": {
      "allow_origins": ["*"],
      "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      "allow_headers": ["Content-Type", "Authorization", "X-Api-Key"]
    },
    
    "ssm": {
      "enabled": true,
      "parameter_template": "/my-cool-app/dev/api-gateway/{resource_name}",
      "auto_export": true,
      "parameters": {
        "api_id": "rest-api/id",
        "api_arn": "rest-api/arn",
        "api_url": "rest-api/url",
        "root_resource_id": "rest-api/root-resource-id",
        "authorizer_id": "authorizer/id"
      }
    },
    
    "cognito_authorizer": {
      "ssm_imports": {
        "user_pool_arn": "/my-cool-app/dev/cognito/user-pool/arn"
      },
      "authorizer_name": "MyAuthorizer",
      "identity_source": "method.request.header.Authorization"
    }
  }
}
```

### Enhanced SSM Parameter Configuration

#### SSM Export Configuration (for API Gateway stacks)
```json
{
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "parameter_template": "/my-cool-app/{environment}/api-gateway/{resource_name}",
      "auto_export": true,
      "parameters": {
        "api_id": "rest-api/id",
        "api_arn": "rest-api/arn",
        "api_url": "rest-api/url",
        "root_resource_id": "rest-api/root-resource-id",
        "authorizer_id": "authorizer/id"
      }
    }
  }
}
```

#### SSM Import Configuration (for service stacks)
```json
{
  "api_gateway": {
    "ssm_imports": {
      "api_id": "/my-cool-app/infrastructure/api-gateway/rest-api/id",
      "root_resource_id": "/my-cool-app/infrastructure/api-gateway/rest-api/root-resource-id",
      "authorizer_id": "/my-cool-app/infrastructure/api-gateway/authorizer/id"
    }
  }
}
```

#### Legacy SSM Configuration (backward compatibility)
```json
{
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/infrastructure/api-gateway/root-resource-id",
    "authorizer": {
      "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/authorizer/id"
    }
  }
}
```

## Environment Variables

### Default Environment Variables

The following environment variables are automatically recognized:

| Variable | Purpose | Default SSM Path |
|----------|---------|------------------|
| `API_GATEWAY_ID` | API Gateway ID | `/my-cool-app/{stack}/api-gateway/id` |
| `API_GATEWAY_ROOT_RESOURCE_ID` | Root resource ID | `/my-cool-app/{stack}/api-gateway/root-resource-id` |
| `COGNITO_AUTHORIZER_ID` | Authorizer ID | `/my-cool-app/{stack}/api-gateway/authorizer/id` |
| `COGNITO_USER_POOL_ID` | User pool ID | - |

### Custom Environment Variables

Configure custom environment variable names:

```json
{
  "api_gateway": {
    "id_env_var": "MY_API_GATEWAY_ID",
    "root_resource_id_env_var": "MY_ROOT_RESOURCE_ID",
    "authorizer": {
      "id_env_var": "MY_AUTHORIZER_ID"
    }
  }
}
```

## Advanced Configuration Patterns

### Multi-Environment Setup

#### Infrastructure Stack (shared across environments)
```json
{
  "name": "infrastructure-${ENVIRONMENT}",
  "api_gateway": {
    "name": "main-api-${ENVIRONMENT}",
    "export_to_ssm": true,
    "cognito_authorizer": {
      "ssm_imports": {
        "user_pool_arn": "/my-cool-app/${ENVIRONMENT}/cognito/user-pool/arn"
      }
    }
  }
}
```

#### Service Stack (environment-specific)
```json
{
  "name": "user-service-${ENVIRONMENT}",
  "api_gateway": {
    "ssm_imports": {
      "api_id": "/my-cool-app/infrastructure-${ENVIRONMENT}/api-gateway/rest-api/id",
      "root_resource_id": "/my-cool-app/infrastructure-${ENVIRONMENT}/api-gateway/rest-api/root-resource-id",
      "authorizer_id": "/my-cool-app/infrastructure-${ENVIRONMENT}/api-gateway/authorizer/id"
    }
  }
}
```

### Microservices Architecture

#### API Gateway Stack
```json
{
  "name": "api-gateway-stack",
  "api_gateway": {
    "name": "microservices-api",
    "description": "Central API Gateway for all microservices",
    "ssm": {
      "enabled": true,
      "parameter_template": "/my-cool-app/api-gateway-stack/{resource_name}",
      "auto_export": true,
      "parameters": {
        "api_id": "rest-api/id",
        "api_arn": "rest-api/arn",
        "api_url": "rest-api/url",
        "root_resource_id": "rest-api/root-resource-id"
      }
    },
    "endpoint_types": ["REGIONAL"],
    "default_cors_preflight_options": {
      "allow_origins": ["https://app.example.com"],
      "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    }
  }
}
```

#### User Service Stack
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "ssm_imports": {
      "api_id": "/my-cool-app/api-gateway-stack/rest-api/id",
      "root_resource_id": "/my-cool-app/api-gateway-stack/rest-api/root-resource-id"
    }
  },
  "lambda_functions": [
    {
      "name": "create-user",
      "api": {"method": "POST", "route": "/users"}
    },
    {
      "name": "get-user",
      "api": {"method": "GET", "route": "/users/{id}"}
    },
    {
      "name": "update-user",
      "api": {"method": "PUT", "route": "/users/{id}"}
    }
  ]
}
```

#### Order Service Stack
```json
{
  "name": "order-service-stack",
  "api_gateway": {
    "ssm_imports": {
      "api_id": "/my-cool-app/api-gateway-stack/rest-api/id",
      "root_resource_id": "/my-cool-app/api-gateway-stack/rest-api/root-resource-id"
    }
  },
  "lambda_functions": [
    {
      "name": "create-order",
      "api": {"method": "POST", "route": "/orders"}
    },
    {
      "name": "get-orders",
      "api": {"method": "GET", "route": "/orders"}
    }
  ]
}
```

## CORS Configuration

### Function-Level CORS
```json
{
  "api": {
    "method": "POST",
    "route": "/users",
    "cors": {
      "allow_origins": ["https://app.example.com", "https://admin.example.com"],
      "allow_methods": ["POST", "OPTIONS"],
      "allow_headers": ["Content-Type", "Authorization"],
      "expose_headers": ["X-Request-ID"],
      "max_age": 86400,
      "allow_credentials": true
    }
  }
}
```

### Stack-Level Default CORS
```json
{
  "api_gateway": {
    "default_cors_preflight_options": {
      "allow_origins": ["*"],
      "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      "allow_headers": ["Content-Type", "Authorization", "X-Api-Key"],
      "max_age": 86400
    }
  }
}
```

## Request Validation

### Parameter Validation
```json
{
  "api": {
    "method": "GET",
    "route": "/users/{id}",
    "request_parameters": {
      "method.request.path.id": true,
      "method.request.querystring.limit": false,
      "method.request.header.Authorization": true
    }
  }
}
```

## Deployment Configuration

### Stage Options
```json
{
  "api_gateway": {
    "deploy_options": {
      "stage_name": "prod",
      "description": "Production deployment",
      "data_trace_enabled": false,
      "metrics_enabled": true,
      "tracing_enabled": true,
      "throttling_rate_limit": 10000,
      "throttling_burst_limit": 20000,
      "cache_cluster_enabled": true,
      "cache_cluster_size": "0.5",
      "caching_enabled": true,
      "cache_ttl_in_seconds": 300,
      "cache_key_parameters": ["method.request.path.id"]
    }
  }
}
```

### Custom Domain Configuration
```json
{
  "api_gateway": {
    "hosted_zone": {
      "zone_name": "example.com",
      "zone_id": "Z123456789"
    },
    "ssl_cert_arn": "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012",
    "domain_name": "api.example.com"
  }
}
```

## Security Configuration

### API Keys and Usage Plans
```json
{
  "api_gateway": {
    "api_keys": [
      {
        "name": "mobile-app-key",
        "description": "API key for mobile application",
        "enabled": true
      },
      {
        "name": "partner-api-key",
        "description": "API key for partner integrations",
        "enabled": true
      }
    ],
    "usage_plans": [
      {
        "name": "basic-plan",
        "description": "Basic usage plan",
        "throttle": {
          "rate_limit": 1000,
          "burst_limit": 2000
        },
        "quota": {
          "limit": 10000,
          "period": "DAY"
        },
        "api_keys": ["mobile-app-key"]
      },
      {
        "name": "premium-plan",
        "description": "Premium usage plan",
        "throttle": {
          "rate_limit": 5000,
          "burst_limit": 10000
        },
        "quota": {
          "limit": 100000,
          "period": "DAY"
        },
        "api_keys": ["partner-api-key"]
      }
    ]
  }
}
```

### Resource Policy
```json
{
  "api_gateway": {
    "policy": {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": "*",
          "Action": "execute-api:Invoke",
          "Resource": "*",
          "Condition": {
            "IpAddress": {
              "aws:SourceIp": ["203.0.113.0/24", "198.51.100.0/24"]
            }
          }
        }
      ]
    }
  }
}
```

## Troubleshooting Configuration

### Debug Configuration Resolution

Enable debug logging to see which configuration values are being used:

```python
import logging
logging.getLogger('ApiGatewayIntegrationUtility').setLevel(logging.DEBUG)
```

### Common Configuration Issues

1. **Missing Route Configuration**
   ```json
   // ❌ Incorrect - missing route
   {
     "api": {
       "method": "GET"
     }
   }
   
   // ✅ Correct
   {
     "api": {
       "method": "GET",
       "route": "/users"
     }
   }
   ```

2. **Invalid Authorization Type**
   ```json
   // ❌ Incorrect - invalid authorization type
   {
     "api": {
       "authorization_type": "INVALID"
     }
   }
   
   // ✅ Correct
   {
     "api": {
       "authorization_type": "COGNITO"
     }
   }
   ```

3. **Missing SSM Parameters**
   ```json
   // ❌ Will fail if SSM parameter doesn't exist
   {
     "api_gateway": {
       "ssm_imports": {
         "api_id": "/nonexistent/parameter"
       }
     }
   }
   
   // ✅ Use correct SSM parameter paths
   {
     "api_gateway": {
       "ssm_imports": {
         "api_id": "/my-cool-app/infrastructure/api-gateway/rest-api/id",
         "root_resource_id": "/my-cool-app/infrastructure/api-gateway/rest-api/root-resource-id"
       }
     }
   }
   ```

## Configuration Validation

The CDK Factory automatically validates configuration and provides helpful error messages:

- Missing required fields
- Invalid authorization types
- Conflicting configuration options
- SSM parameter accessibility
- IAM permission issues

## Best Practices Summary

1. **Use SSM parameters for cross-stack references**
2. **Provide fallback configuration options**
3. **Follow consistent naming conventions**
4. **Separate infrastructure and service stacks**
5. **Use environment-specific configurations**
6. **Enable export_to_ssm only in infrastructure stacks**
7. **Configure appropriate CORS policies**
8. **Use API keys and usage plans for rate limiting**
9. **Implement proper request validation**
10. **Test configuration in development environments first**
