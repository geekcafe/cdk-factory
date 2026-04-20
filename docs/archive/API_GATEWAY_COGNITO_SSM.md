# API Gateway + Cognito SSM Integration Guide

## Overview

With the separated stack pattern (v0.8.0+), API Gateway needs to import the Cognito User Pool ARN from SSM Parameter Store instead of using environment variables or direct references.

## Deployment Flow

```
1. Cognito Stack       → Exports user_pool_arn to SSM
2. Lambda Stack        → Exports Lambda ARNs to SSM
3. API Gateway Stack   → Imports both from SSM
```

## Configuration Examples

### Method 1: SSM Auto-Import (Recommended)

#### Cognito Stack
```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-cognito",
  "module": "cognito_stack",
  "ssm": {
    "enabled": true,
    "auto_export": true,
    "workload": "{{WORKLOAD_NAME}}",
    "environment": "{{ENVIRONMENT}}"
  },
  "cognito": {
    "user_pool_name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}",
    "custom_attributes": [...]
  }
}
```

**Exports to SSM:**
- `/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/cognito/user-pool/user-pool-arn`
- `/{{WORKLOAD_NAME}}/{{ENVIRONMENT}}/cognito/user-pool/user-pool-id`

#### API Gateway Stack
```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-api-gateway",
  "module": "api_gateway_stack",
  "api_gateway": {
    "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-api",
    "api_type": "REST",
    "stage_name": "prod",
    "ssm": {
      "enabled": true,
      "auto_export": true,
      "workload": "{{WORKLOAD_NAME}}",
      "environment": "{{ENVIRONMENT}}",
      "imports": {
        "workload": "{{WORKLOAD_NAME}}",
        "environment": "{{ENVIRONMENT}}",
        "user_pool_arn": "auto"  // ✅ Auto-discovers from Cognito stack
      }
    },
    "cognito_authorizer": {
      "authorizer_name": "{{WORKLOAD_NAME}}-cognito-authorizer",
      "identity_source": "method.request.header.Authorization"
    },
    "routes": [
      {
        "path": "/api/resource",
        "method": "GET",
        "lambda_name": "my-handler",
        "authorization_type": "COGNITO_USER_POOLS"
      }
    ]
  }
}
```

### Method 2: Explicit SSM Path

```json
{
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "workload": "my-app",
      "environment": "prod",
      "imports": {
        "workload": "my-app",
        "environment": "prod",
        "user_pool_arn": "/my-app/prod/cognito/user-pool/user-pool-arn"  // Explicit
      }
    },
    "cognito_authorizer": {
      "authorizer_name": "my-app-authorizer"
    }
  }
}
```

### Method 3: Direct Config (Backward Compatible)

```json
{
  "api_gateway": {
    "cognito_authorizer": {
      "authorizer_name": "my-app-authorizer",
      "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC123"
    },
    "routes": [...]
  }
}
```

### Method 4: Environment Variable (Backward Compatible)

Set environment variable before deployment:
```bash
export COGNITO_USER_POOL_ID=us-east-1_ABC123
cdk deploy
```

## SSM Path Convention

Cognito stack exports follow this pattern:
```
/{workload}/{environment}/cognito/{resource-name}/{attribute}
```

**Default resource name:** `user-pool`

**Exported attributes:**
- `user-pool-arn` (or `user_pool_arn`)
- `user-pool-id` (or `user_pool_id`)
- `user-pool-name`
- `user-pool-client-id`
- `authorizer-id`

## Complete Example: Three-Stack Pattern

### deployment-config.json
```json
{
  "workload": {
    "name": "geek-cafe",
    "deployments": [
      {
        "name": "geek-cafe-prod",
        "environment": "prod",
        "pipeline": {
          "stages": [
            {
              "name": "infrastructure",
              "stacks": ["cognito-stack"]
            },
            {
              "name": "lambdas",
              "stacks": ["lambda-stack"]
            },
            {
              "name": "api-gateway",
              "stacks": ["api-gateway-stack"]
            }
          ]
        }
      }
    ]
  }
}
```

### Stage 1: cognito-stack.json
```json
{
  "name": "geek-cafe-prod-cognito",
  "module": "cognito_stack",
  "ssm": {
    "enabled": true,
    "auto_export": true,
    "workload": "geek-cafe",
    "environment": "prod"
  },
  "cognito": {
    "user_pool_name": "geek-cafe-prod",
    "exists": false
  }
}
```

### Stage 2: lambda-stack.json
```json
{
  "name": "geek-cafe-prod-lambdas",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "workload": "geek-cafe",
    "environment": "prod"
  },
  "resources": [
    {
      "name": "geek-cafe-prod-get-cafes",
      "src": "./src/handlers/cafes",
      "handler": "get_cafes.lambda_handler"
    }
  ]
}
```

### Stage 3: api-gateway-stack.json
```json
{
  "name": "geek-cafe-prod-api-gateway",
  "module": "api_gateway_stack",
  "api_gateway": {
    "name": "geek-cafe-prod-api",
    "api_type": "REST",
    "stage_name": "prod",
    "ssm": {
      "enabled": true,
      "auto_export": true,
      "workload": "geek-cafe",
      "environment": "prod",
      "imports": {
        "workload": "geek-cafe",
        "environment": "prod",
        "user_pool_arn": "auto"  // ✅ Imports from Cognito stack
      }
    },
    "cognito_authorizer": {
      "authorizer_name": "geek-cafe-cognito-authorizer"
    },
    "routes": [
      {
        "path": "/cafes",
        "method": "GET",
        "lambda_name": "geek-cafe-prod-get-cafes",  // ✅ Imports from Lambda stack
        "authorization_type": "COGNITO_USER_POOLS"
      }
    ]
  }
}
```

## SSM Parameters Created

After all stacks deploy:

**From Cognito Stack:**
```
/geek-cafe/prod/cognito/user-pool/user-pool-arn
/geek-cafe/prod/cognito/user-pool/user-pool-id
/geek-cafe/prod/cognito/user-pool/user-pool-client-id
```

**From Lambda Stack:**
```
/geek-cafe/prod/lambda/geek-cafe-prod-get-cafes/arn
/geek-cafe/prod/lambda/geek-cafe-prod-get-cafes/function-name
```

**From API Gateway Stack:**
```
/geek-cafe/prod/api-gateway/geek-cafe-prod-api/api-id
/geek-cafe/prod/api-gateway/geek-cafe-prod-api/api-url
/geek-cafe/prod/api-gateway/geek-cafe-prod-api/root-resource-id
/geek-cafe/prod/api-gateway/geek-cafe-prod-api/authorizer-id
```

## Troubleshooting

### Error: "User pool ID is required for API Gateway authorizer"

**Cause:** API Gateway can't find the Cognito User Pool ARN.

**Solutions:**

1. **Check SSM imports are configured:**
   ```json
   "ssm": {
     "imports": {
       "user_pool_arn": "auto"  // Must be present
     }
   }
   ```

2. **Verify Cognito stack deployed first:**
   ```bash
   aws ssm get-parameter --name "/geek-cafe/prod/cognito/user-pool/user-pool-arn"
   ```

3. **Check workload/environment match:**
   ```json
   // Both must match
   Cognito: "workload": "geek-cafe", "environment": "prod"
   API GW:  "workload": "geek-cafe", "environment": "prod"
   ```

4. **Use explicit path if auto-discovery fails:**
   ```json
   "imports": {
     "user_pool_arn": "/geek-cafe/prod/cognito/user-pool/user-pool-arn"
   }
   ```

5. **Temporary workaround - use direct config:**
   ```json
   "cognito_authorizer": {
     "user_pool_arn": "arn:aws:cognito-idp:region:account:userpool/pool_id"
   }
   ```

### Error: SSM Parameter Not Found

**Check if Cognito stack exported correctly:**
```bash
aws ssm get-parameters-by-path \
  --path "/geek-cafe/prod/cognito" \
  --recursive
```

**Verify auto_export is enabled in Cognito stack:**
```json
{
  "ssm": {
    "enabled": true,
    "auto_export": true  // ✅ Must be true
  }
}
```

## Migration from Old Pattern

### Before (Combined Lambda + API Gateway)
```json
{
  "module": "lambda_stack",
  "api_gateway": {
    "enabled": true,
    "cognito_authorizer": {
      "user_pool_id": "${COGNITO_USER_POOL_ID}"  // ❌ Env var
    }
  },
  "resources": [...]
}
```

### After (Separated Stacks)

**Lambda Stack:**
```json
{
  "module": "lambda_stack",
  "ssm": {"enabled": true, "workload": "app", "environment": "prod"},
  "resources": [...]
}
```

**API Gateway Stack:**
```json
{
  "module": "api_gateway_stack",
  "api_gateway": {
    "ssm": {
      "enabled": true,
      "workload": "app",
      "environment": "prod",
      "imports": {
        "workload": "app",
        "environment": "prod",
        "user_pool_arn": "auto"  // ✅ SSM import
      }
    }
  }
}
```

## Benefits of SSM-Based Approach

1. **No environment variables needed** - All config in JSON
2. **Type-safe** - ARNs validated by AWS
3. **Automatic discovery** - Follows naming conventions
4. **Loose coupling** - Stacks can deploy independently
5. **Audit trail** - SSM tracks all parameter access
6. **Centralized** - One place to manage cross-stack references
