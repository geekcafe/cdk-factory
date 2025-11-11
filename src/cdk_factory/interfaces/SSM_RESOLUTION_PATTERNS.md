# SSM Parameter Resolution Patterns

The CDK-Factory `StandardizedSsmMixin` provides flexible SSM parameter resolution with support for all parameter types.

## Supported Patterns

### 1. Standard String Parameters (Default)

```json
{
  "value": "{{ssm:/path/to/parameter}}"
}
```

**Use for:**
- Plain text configuration values
- Non-sensitive data
- Database hosts, ports, endpoints

**Resolution:**
- Uses `StringParameter.from_string_parameter_name()`
- Returns a CDK token that resolves at deployment time
- Works for both String and SecureString types (SecureString is auto-decrypted)

**Example:**
```json
{
  "DB_HOST": "{{ssm:/blue-green/my-app/db/host}}",
  "API_URL": "{{ssm:/blue-green/my-app/api/endpoint}}"
}
```

### 2. Explicit SecureString Parameters

```json
{
  "value": "{{ssm-secure:/path/to/secret}}"
}
```

**Use for:**
- Passwords, API keys, tokens
- Sensitive configuration
- When you want to be explicit about encrypted parameters

**Resolution:**
- Uses `StringParameter.value_for_secure_string_parameter_name()`
- Returns a CDK token with version 1 (latest)
- Provides semantic clarity in configuration

**Example:**
```json
{
  "DB_PASSWORD": "{{ssm-secure:/blue-green/my-app/db/password}}",
  "API_KEY": "{{ssm-secure:/blue-green/my-app/api/key}}",
  "JWT_SECRET": "{{ssm-secure:/blue-green/my-app/jwt-secret}}"
}
```

**Note:** The `{{ssm:}}` pattern also works for SecureString parameters, but `{{ssm-secure:}}` makes it explicit.

### 3. StringList Parameters

```json
{
  "value": "{{ssm-list:/path/to/list}}"
}
```

**Use for:**
- Comma-separated lists
- Multiple values in a single parameter
- IP whitelists, feature flags, environment lists

**Resolution:**
- Uses `StringParameter.value_for_string_list_parameter()`
- Returns list items as a CDK token
- Values are comma-separated in SSM

**Example:**
```json
{
  "ALLOWED_IPS": "{{ssm-list:/blue-green/my-app/allowed-ips}}",
  "FEATURE_FLAGS": "{{ssm-list:/blue-green/my-app/features}}"
}
```

**SSM Storage:**
```
Parameter: /blue-green/my-app/allowed-ips
Type: StringList
Value: 10.0.0.1,10.0.0.2,10.0.0.3
```

## Pattern Comparison

| Pattern | Parameter Type | Use Case | Example |
|---------|---------------|----------|---------|
| `{{ssm:path}}` | String or SecureString | General purpose | `{{ssm:/app/config}}` |
| `{{ssm-secure:path}}` | SecureString | Explicit secrets | `{{ssm-secure:/app/password}}` |
| `{{ssm-list:path}}` | StringList | Multiple values | `{{ssm-list:/app/ips}}` |

## Usage Examples

### ECS Task Definition

```json
{
  "containers": [
    {
      "name": "app",
      "environment": {
        "DB_HOST": "{{ssm:/prod/app/db/host}}",
        "DB_PORT": "{{ssm:/prod/app/db/port}}",
        "DB_PASSWORD": "{{ssm-secure:/prod/app/db/password}}",
        "ALLOWED_ORIGINS": "{{ssm-list:/prod/app/cors/origins}}",
        "API_URL": "{{ssm:/prod/app/api/url}}"
      }
    }
  ]
}
```

### Lambda Environment Variables

```json
{
  "lambda": {
    "environment": {
      "TABLE_NAME": "{{ssm:/stage/app/dynamodb/table-name}}",
      "API_KEY": "{{ssm-secure:/stage/app/external-api/key}}",
      "REGIONS": "{{ssm-list:/stage/app/deployment/regions}}"
    }
  }
}
```

### Load Balancer Configuration

```json
{
  "load_balancer": {
    "certificate_arn": "{{ssm:/prod/app/cert/arn}}",
    "allowed_cidrs": "{{ssm-list:/prod/app/security/allowed-cidrs}}"
  }
}
```

## Best Practices

### 1. Use Appropriate Types

```json
// ✅ Good - Explicit about sensitive data
{
  "DB_PASSWORD": "{{ssm-secure:/app/db/password}}"
}

// ⚠️ Works but less clear
{
  "DB_PASSWORD": "{{ssm:/app/db/password}}"
}
```

### 2. Hierarchical Naming

```json
// ✅ Good - Organized hierarchy
{
  "DB_HOST": "{{ssm:/prod/app/database/host}}",
  "DB_PORT": "{{ssm:/prod/app/database/port}}",
  "DB_NAME": "{{ssm:/prod/app/database/name}}"
}
```

### 3. StringList for Multiple Values

```json
// ✅ Good - Single parameter for list
{
  "ALLOWED_IPS": "{{ssm-list:/app/security/allowed-ips}}"
}

// ❌ Bad - Multiple parameters
{
  "ALLOWED_IP_1": "{{ssm:/app/security/allowed-ip-1}}",
  "ALLOWED_IP_2": "{{ssm:/app/security/allowed-ip-2}}"
}
```

### 4. SecureString for Secrets

```json
// ✅ Good - Encrypted at rest
{
  "API_KEY": "{{ssm-secure:/app/secrets/api-key}}",
  "JWT_SECRET": "{{ssm-secure:/app/secrets/jwt}}",
  "ENCRYPTION_KEY": "{{ssm-secure:/app/secrets/encryption}}"
}

// ❌ Bad - Plain text secrets
{
  "API_KEY": "{{ssm:/app/config/api-key}}"  // String type
}
```

## Token Resolution

All patterns return **CDK tokens** that are resolved at deployment time by CloudFormation:

```python
# Configuration
"DB_HOST": "{{ssm:/prod/app/db/host}}"

# CDK generates CloudFormation
"DB_HOST": {
  "Fn::Sub": [
    "{{resolve:ssm:/prod/app/db/host}}"
  ]
}

# At deployment time, CloudFormation resolves to actual value
"DB_HOST": "mysql.example.com"
```

## Error Handling

### Invalid Pattern

```json
// ❌ Typo in pattern
{
  "value": "{{ssm-secur:/path}}"  // Missing 'e'
}
// Result: Treated as literal string, not resolved
```

### Non-existent Parameter

```json
// ❌ Parameter doesn't exist
{
  "value": "{{ssm:/non/existent/path}}"
}
// Result: CloudFormation deployment fails with parameter not found
```

### Wrong Type

```json
// ❌ Using ssm-list for String parameter
{
  "value": "{{ssm-list:/path/to/string}}"  // Parameter is String type
}
// Result: CloudFormation error or unexpected behavior
```

## Parameter Store Integration

### Creating Parameters

Use the `ParameterStoreStack` to create parameters:

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "db/host",
        "value": "mysql.example.com",
        "type": "String"
      },
      {
        "name": "db/password",
        "value": "secure-password",
        "type": "SecureString"
      },
      {
        "name": "allowed-ips",
        "value": "10.0.0.1,10.0.0.2,10.0.0.3",
        "type": "StringList"
      }
    ]
  }
}
```

### Consuming Parameters

Reference them in dependent stacks:

```json
{
  "dependencies": ["parameter-store-stack"],
  "ecs_service": {
    "environment": {
      "DB_HOST": "{{ssm:/prod/app/db/host}}",
      "DB_PASSWORD": "{{ssm-secure:/prod/app/db/password}}",
      "ALLOWED_IPS": "{{ssm-list:/prod/app/allowed-ips}}"
    }
  }
}
```

## Migration Guide

### From Plain Values

```json
// Before
{
  "DB_HOST": "mysql.example.com",
  "DB_PASSWORD": "hardcoded-password"
}

// After
{
  "DB_HOST": "{{ssm:/prod/app/db/host}}",
  "DB_PASSWORD": "{{ssm-secure:/prod/app/db/password}}"
}
```

### From Secrets Manager

```json
// Before
{
  "DB_PASSWORD": "{{secrets:prod/app/db-credentials}}"
}

// After - Use SSM SecureString
{
  "DB_PASSWORD": "{{ssm-secure:/prod/app/db/password}}"
}
```

## See Also

- [ParameterStoreStack Documentation](../stack_library/ssm/parameter_store/README.md)
- [StandardizedSsmMixin Source](./standardized_ssm_mixin.py)
- [AWS SSM Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
