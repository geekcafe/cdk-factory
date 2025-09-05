# API Gateway Migration Guide

## Overview

This guide helps you migrate existing API Gateway configurations to use the new SSM integration features while maintaining backward compatibility.

## Migration Scenarios

### Scenario 1: Direct Configuration to SSM

**Current Configuration (Direct Values):**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id": "abcd1234ef",
    "root_resource_id": "xyz789abc",
    "authorizer": {
      "id": "auth123def"
    }
  }
}
```

**Migrated Configuration (SSM Parameters):**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/infrastructure/api-gateway/root-resource-id",
    "authorizer": {
      "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/authorizer/id"
    }
  }
}
```

**Required SSM Parameters:**
```bash
aws ssm put-parameter --name "/my-cool-app/infrastructure/api-gateway/id" --value "abcd1234ef" --type "String"
aws ssm put-parameter --name "/my-cool-app/infrastructure/api-gateway/root-resource-id" --value "xyz789abc" --type "String"
aws ssm put-parameter --name "/my-cool-app/infrastructure/api-gateway/authorizer/id" --value "auth123def" --type "String"
```

### Scenario 2: Environment Variables to Configurable Environment Variables

**Current Configuration (Default Environment Variables):**
```bash
export API_GATEWAY_ID="abcd1234ef"
export API_GATEWAY_ROOT_RESOURCE_ID="xyz789abc"
export COGNITO_AUTHORIZER_ID="auth123def"
```

**Migrated Configuration (Custom Environment Variables):**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id_env_var": "USER_SERVICE_API_GATEWAY_ID",
    "root_resource_id_env_var": "USER_SERVICE_ROOT_RESOURCE_ID",
    "authorizer": {
      "id_env_var": "USER_SERVICE_AUTHORIZER_ID"
    }
  }
}
```

**Updated Environment Variables:**
```bash
export USER_SERVICE_API_GATEWAY_ID="abcd1234ef"
export USER_SERVICE_ROOT_RESOURCE_ID="xyz789abc"
export USER_SERVICE_AUTHORIZER_ID="auth123def"
```

### Scenario 3: Mixed Configuration to Fallback Chain

**Current Configuration (Mixed Sources):**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id": "abcd1234ef"
  }
}
```

```bash
export API_GATEWAY_ROOT_RESOURCE_ID="xyz789abc"
```

**Migrated Configuration (Full Fallback Chain):**
```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id": "abcd1234ef",
    "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/id",
    "id_env_var": "API_GATEWAY_ID",
    
    "root_resource_id_ssm_path": "/my-cool-app/infrastructure/api-gateway/root-resource-id",
    "root_resource_id_env_var": "API_GATEWAY_ROOT_RESOURCE_ID",
    
    "authorizer": {
      "id_ssm_path": "/my-cool-app/infrastructure/api-gateway/authorizer/id",
      "id_env_var": "COGNITO_AUTHORIZER_ID"
    }
  }
}
```

## Step-by-Step Migration Process

### Step 1: Identify Current Configuration

Run this script to identify your current API Gateway configuration:

```bash
#!/bin/bash
echo "=== Current API Gateway Configuration ==="
echo

# Check for direct configuration in JSON files
echo "Direct Configuration:"
find . -name "*.json" -exec grep -l "api_gateway" {} \; | while read file; do
    echo "File: $file"
    grep -A 10 -B 2 "api_gateway" "$file" | head -20
    echo
done

# Check for environment variables
echo "Environment Variables:"
env | grep -E "(API_GATEWAY|COGNITO_AUTHORIZER)" | sort

# Check for existing SSM parameters
echo "Existing SSM Parameters:"
aws ssm describe-parameters --filters "Key=Name,Values=/my-cool-app" --query 'Parameters[].Name' --output table 2>/dev/null || echo "No SSM parameters found or AWS CLI not configured"
```

### Step 2: Create Infrastructure Stack (Recommended)

Create a dedicated infrastructure stack that exports API Gateway configuration:

```json
{
  "name": "infrastructure-stack",
  "api_gateway": {
    "api_gateway_name": "main-api",
    "description": "Main API Gateway for all services",
    "export_to_ssm": true,
    "deploy_options": {
      "stage_name": "prod"
    },
    "cognito_authorizer": {
      "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC123DEF"
    }
  }
}
```

### Step 3: Deploy Infrastructure Stack

```bash
cdk deploy infrastructure-stack
```

This will create SSM parameters:
- `/my-cool-app/infrastructure-stack/api-gateway/id`
- `/my-cool-app/infrastructure-stack/api-gateway/arn`
- `/my-cool-app/infrastructure-stack/api-gateway/root-resource-id`
- `/my-cool-app/infrastructure-stack/api-gateway/authorizer/id`

### Step 4: Update Service Stacks

Update your service stacks to reference the infrastructure stack:

```json
{
  "name": "user-service-stack",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/root-resource-id",
    "authorizer": {
      "id_ssm_path": "/my-cool-app/infrastructure-stack/api-gateway/authorizer/id"
    }
  },
  "lambda_functions": [
    // your lambda functions
  ]
}
```

### Step 5: Test Migration

Before deploying to production, test the migration:

```bash
# Deploy to a test environment
cdk deploy user-service-stack --profile test

# Verify the stack can resolve SSM parameters
aws logs filter-log-events --log-group-name "/aws/lambda/user-service-stack-*" --filter-pattern "SSM"
```

### Step 6: Deploy to Production

```bash
cdk deploy user-service-stack --profile production
```

## Migration Strategies

### Strategy 1: Big Bang Migration

Migrate all stacks at once. Best for smaller projects.

**Pros:**
- Clean, consistent configuration
- Single migration event
- Immediate benefits

**Cons:**
- Higher risk
- Requires coordination
- Potential downtime

**Steps:**
1. Create infrastructure stack
2. Update all service stacks
3. Deploy infrastructure stack
4. Deploy all service stacks

### Strategy 2: Gradual Migration

Migrate stacks one by one. Best for larger projects.

**Pros:**
- Lower risk
- Can be done incrementally
- Easy rollback

**Cons:**
- Mixed configuration during transition
- Longer migration period

**Steps:**
1. Create infrastructure stack with `export_to_ssm: true`
2. Deploy infrastructure stack
3. Migrate service stacks one by one
4. Test each migration
5. Clean up old configuration

### Strategy 3: Parallel Migration

Run old and new configurations in parallel.

**Pros:**
- Zero downtime
- Easy rollback
- Thorough testing

**Cons:**
- Resource duplication
- Complex configuration
- Higher costs during migration

**Steps:**
1. Create new infrastructure stack
2. Create new service stacks with SSM configuration
3. Test new stacks thoroughly
4. Switch traffic to new stacks
5. Remove old stacks

## Environment-Specific Migration

### Development Environment

```json
{
  "name": "user-service-dev",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/dev/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/dev/infrastructure/api-gateway/root-resource-id"
  }
}
```

### Staging Environment

```json
{
  "name": "user-service-staging",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/staging/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/staging/infrastructure/api-gateway/root-resource-id"
  }
}
```

### Production Environment

```json
{
  "name": "user-service-prod",
  "api_gateway": {
    "id_ssm_path": "/my-cool-app/prod/infrastructure/api-gateway/id",
    "root_resource_id_ssm_path": "/my-cool-app/prod/infrastructure/api-gateway/root-resource-id"
  }
}
```

## Rollback Procedures

### Rollback from SSM to Direct Configuration

If you need to rollback, you can revert to direct configuration:

```bash
# Get current SSM values
API_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/id" --query 'Parameter.Value' --output text)
ROOT_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/root-resource-id" --query 'Parameter.Value' --output text)
AUTH_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/authorizer/id" --query 'Parameter.Value' --output text)

# Update configuration
cat > rollback-config.json << EOF
{
  "name": "user-service-stack",
  "api_gateway": {
    "id": "$API_ID",
    "root_resource_id": "$ROOT_ID",
    "authorizer": {
      "id": "$AUTH_ID"
    }
  }
}
EOF
```

### Rollback from SSM to Environment Variables

```bash
# Export SSM values as environment variables
export API_GATEWAY_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/id" --query 'Parameter.Value' --output text)
export API_GATEWAY_ROOT_RESOURCE_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/root-resource-id" --query 'Parameter.Value' --output text)
export COGNITO_AUTHORIZER_ID=$(aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/authorizer/id" --query 'Parameter.Value' --output text)

# Remove SSM configuration from JSON
```

## Common Migration Issues

### Issue 1: SSM Parameter Not Found

**Error:**
```
Failed to retrieve API Gateway ID from SSM path /my-cool-app/infrastructure/api-gateway/id
```

**Solution:**
```bash
# Check if parameter exists
aws ssm get-parameter --name "/my-cool-app/infrastructure/api-gateway/id"

# Create parameter if missing
aws ssm put-parameter --name "/my-cool-app/infrastructure/api-gateway/id" --value "your-api-gateway-id" --type "String"
```

### Issue 2: IAM Permissions

**Error:**
```
AccessDenied: User is not authorized to perform: ssm:GetParameter
```

**Solution:**
Add SSM permissions to your deployment role:
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
      "Resource": "arn:aws:ssm:*:*:parameter/my-cool-app/*"
    }
  ]
}
```

### Issue 3: Cross-Region SSM Parameters

**Error:**
```
Parameter /my-cool-app/infrastructure/api-gateway/id not found
```

**Solution:**
Ensure SSM parameters are created in the correct region:
```bash
aws ssm put-parameter --name "/my-cool-app/infrastructure/api-gateway/id" --value "your-api-id" --type "String" --region us-east-1
```

### Issue 4: Parameter Store Limits

**Error:**
```
ParameterLimitExceeded: Too many parameters
```

**Solution:**
Clean up unused parameters:
```bash
# List all parameters
aws ssm describe-parameters --query 'Parameters[].Name'

# Delete unused parameters
aws ssm delete-parameter --name "/old/unused/parameter"
```

## Validation Scripts

### Pre-Migration Validation

```bash
#!/bin/bash
echo "=== Pre-Migration Validation ==="

# Check AWS CLI configuration
aws sts get-caller-identity > /dev/null || { echo "AWS CLI not configured"; exit 1; }

# Check required permissions
aws ssm describe-parameters --max-items 1 > /dev/null || { echo "Missing SSM permissions"; exit 1; }

# Check existing API Gateway
if [ -n "$API_GATEWAY_ID" ]; then
    aws apigateway get-rest-api --rest-api-id "$API_GATEWAY_ID" > /dev/null || { echo "API Gateway $API_GATEWAY_ID not found"; exit 1; }
fi

echo "Pre-migration validation passed"
```

### Post-Migration Validation

```bash
#!/bin/bash
echo "=== Post-Migration Validation ==="

# Check SSM parameters exist
PARAMS=(
    "/my-cool-app/infrastructure/api-gateway/id"
    "/my-cool-app/infrastructure/api-gateway/root-resource-id"
    "/my-cool-app/infrastructure/api-gateway/authorizer/id"
)

for param in "${PARAMS[@]}"; do
    aws ssm get-parameter --name "$param" > /dev/null || { echo "Parameter $param not found"; exit 1; }
    echo "✓ Parameter $param exists"
done

# Test stack deployment
cdk synth > /dev/null || { echo "CDK synthesis failed"; exit 1; }
echo "✓ CDK synthesis successful"

echo "Post-migration validation passed"
```

## Migration Checklist

### Pre-Migration
- [ ] Backup current configuration files
- [ ] Document current API Gateway IDs and resources
- [ ] Test migration in development environment
- [ ] Verify IAM permissions for SSM access
- [ ] Plan rollback procedure

### During Migration
- [ ] Create infrastructure stack with `export_to_ssm: true`
- [ ] Deploy infrastructure stack
- [ ] Verify SSM parameters are created
- [ ] Update service stack configurations
- [ ] Test service stack deployments
- [ ] Verify API Gateway functionality

### Post-Migration
- [ ] Remove old configuration files
- [ ] Clean up unused environment variables
- [ ] Update deployment documentation
- [ ] Train team on new configuration patterns
- [ ] Monitor for any issues

## Best Practices for Migration

1. **Start with Development**: Always test migration in development first
2. **Use Gradual Migration**: Migrate one stack at a time for large projects
3. **Maintain Fallbacks**: Keep fallback configuration during transition
4. **Document Changes**: Update all documentation and runbooks
5. **Monitor Closely**: Watch for errors during and after migration
6. **Test Thoroughly**: Verify all API endpoints work after migration
7. **Plan Rollback**: Have a tested rollback procedure ready
8. **Communicate**: Inform team members about configuration changes

## Support and Troubleshooting

If you encounter issues during migration:

1. Check the main documentation: `api-gateway-ssm-integration.md`
2. Enable debug logging to see configuration resolution
3. Verify SSM parameter values and permissions
4. Test configuration in isolation
5. Use the validation scripts provided above

For additional support, refer to the troubleshooting section in the main documentation.
