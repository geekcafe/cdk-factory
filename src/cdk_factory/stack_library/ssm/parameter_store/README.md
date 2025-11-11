# Parameter Store Stack

General-purpose CDK stack for managing AWS Systems Manager Parameter Store parameters.

## Features

- ✅ Create multiple SSM parameters from JSON configuration
- ✅ Support all parameter types (String, StringList, SecureString)
- ✅ Automatic parameter name prefixing (optional)
- ✅ Template variable substitution
- ✅ Stable construct IDs (no pipeline name bleed)
- ✅ Global and per-parameter tags
- ✅ Standard and Advanced parameter tiers
- ✅ Parameter validation with allowed patterns
- ✅ CDK v2 compliant (no deprecated APIs)

## Implementation Notes

### CDK v2 Compliance
This stack uses modern CDK v2 patterns without deprecated APIs:
- **String parameters**: Use `StringParameter` (L2 construct)
- **StringList parameters**: Use `StringListParameter` (L2 construct)

### ⚠️ SecureString NOT Supported

**CRITICAL:** This stack does **NOT** support SecureString parameters. CloudFormation's `AWS::SSM::Parameter` resource only supports `String` and `StringList` types.

If you include `"type": "SecureString"` in your configuration, **the synthesis will fail** with a clear error message.

**For Sensitive Data (passwords, API keys, tokens):**

✅ **Use AWS Secrets Manager** (recommended) - Full CloudFormation support, automatic rotation, versioning
  - Create secrets via Secrets Manager stack or manually
  - Reference in your application code
  - See project `SECRETS_MANAGEMENT.md` for detailed implementation guide

✅ **Pre-create SecureString manually** (if you must use SSM)
  ```bash
  aws ssm put-parameter --name "/path/to/secret" --value "SECRET" --type SecureString
  ```
  - Create before deployment
  - Reference in app using `{{ssm-secure:/path/to/secret}}`
  - Not managed by CDK (manual lifecycle)

**Why?** CloudFormation's `AWS::SSM::Parameter` [does not include SecureString](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ssm-parameter.html) as a valid Type value. Additionally, you cannot change a parameter's type after creation without deleting it first.

**Use This Stack For:** Non-sensitive configuration values, application settings, feature flags, connection info, ARN references.

## Configuration

### Basic Structure

```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-parameter-store",
  "module": "parameter_store_stack",
  "enabled": true,
  "parameter_store": {
    "prefix": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}",
    "auto_format_names": true,
    "global_tags": {
      "ManagedBy": "CDK-Factory"
    },
    "parameters": [
      {
        "name": "config/setting",
        "value": "value",
        "type": "String",
        "description": "Description"
      }
    ]
  }
}
```

### Configuration Options

#### Top-Level Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prefix` | string | No | `/{environment}/{workload}` | Prefix prepended to parameter names |
| `auto_format_names` | boolean | No | `true` | Automatically prefix parameter names |
| `global_tags` | object | No | `{}` | Tags applied to all parameters |
| `parameters` | array | **Yes** | - | Array of parameter definitions |

#### Parameter Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **Yes** | - | Parameter name or path |
| `value` | string | **Yes** | - | Parameter value |
| `type` | string | No | `String` | `String`, `StringList`, or `SecureString` |
| `description` | string | No | `Managed by CDK-Factory` | Parameter description |
| `tier` | string | No | `Standard` | `Standard`, `Advanced`, or `Intelligent-Tiering` |
| `allowed_pattern` | string | No | - | Regex pattern for value validation |
| `data_type` | string | No | `text` | `text` or `aws:ec2:image` |
| `tags` | object | No | `{}` | Parameter-specific tags |

## Usage Examples

### Example 1: Basic Parameters

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "app/version",
        "value": "1.0.0",
        "description": "Application version"
      },
      {
        "name": "app/environment",
        "value": "production",
        "description": "Environment name"
      }
    ]
  }
}
```

Creates:
- `/blue-green/my-app/app/version` = `1.0.0`
- `/blue-green/my-app/app/environment` = `production`

### Example 2: Absolute Paths

```json
{
  "parameter_store": {
    "auto_format_names": false,
    "parameters": [
      {
        "name": "/custom/path/setting",
        "value": "custom-value"
      }
    ]
  }
}
```

Creates:
- `/custom/path/setting` = `custom-value` (no prefix added)

### Example 3: Template Variables

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "config/region",
        "value": "{{AWS_REGION}}"
      },
      {
        "name": "config/account",
        "value": "{{AWS_ACCOUNT}}"
      },
      {
        "name": "config/workload",
        "value": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}"
      }
    ]
  }
}
```

Supported variables:
- `{{ENVIRONMENT}}` - Deployment environment
- `{{WORKLOAD_NAME}}` - Workload name
- `{{AWS_ACCOUNT}}` - AWS account ID
- `{{AWS_REGION}}` - AWS region

### Example 4: Secure Parameters

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "secrets/api-key",
        "value": "sk-1234567890abcdef",
        "type": "SecureString",
        "description": "Third-party API key",
        "tags": {
          "Sensitive": "true"
        }
      }
    ]
  }
}
```

Creates an encrypted parameter using AWS KMS.

### Example 5: String Lists

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "config/allowed-ips",
        "value": "10.0.0.1,10.0.0.2,10.0.0.3",
        "type": "StringList",
        "description": "Allowed IP addresses"
      }
    ]
  }
}
```

### Example 6: Parameter Validation

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "config/port",
        "value": "8080",
        "type": "String",
        "allowed_pattern": "^[0-9]{1,5}$",
        "description": "Application port (must be 1-5 digits)"
      }
    ]
  }
}
```

### Example 7: Advanced Tier

```json
{
  "parameter_store": {
    "parameters": [
      {
        "name": "config/large-json",
        "value": "{\"key1\":\"value1\",\"key2\":\"value2\",...}",
        "type": "String",
        "tier": "Advanced",
        "description": "Large configuration JSON (>4KB)"
      }
    ]
  }
}
```

Use Advanced tier for:
- Parameters larger than 4KB (up to 8KB)
- Parameters requiring higher throughput
- More than 10,000 parameters in an account/region

## Parameter Naming

### Auto-Formatting (Default)

With `auto_format_names: true` (default):

| Input Name | Result |
|------------|--------|
| `config/setting` | `/blue-green/workload/config/setting` |
| `/absolute/path` | `/absolute/path` (unchanged) |

### Manual Formatting

With `auto_format_names: false`:

| Input Name | Result |
|------------|--------|
| `config/setting` | `config/setting` (exactly as specified) |
| `/absolute/path` | `/absolute/path` (exactly as specified) |

## Tags

Tags are applied in this order (later tags override earlier ones):

1. **Global tags** - Applied to all parameters
2. **Parameter tags** - Applied to specific parameter
3. **Auto tags** - Always added:
   - `ManagedBy: CDK-Factory`
   - `Environment: {environment}`
   - `Workload: {workload}`

## Stable Construct IDs

All parameters use stable IDs based on their index and sanitized name:

```
{workload}-{environment}-param-{index}-{sanitized-name}
```

Example: `my-app-blue-green-param-0-config-setting`

This ensures CloudFormation logical IDs remain stable across pipeline changes.

## Integration Example

Add to your pipeline configuration:

```json
{
  "stages": [
    {
      "name": "Stage-1-Parameters",
      "stacks": [
        {
          "__imports__": "./config-parameters.json"
        }
      ]
    }
  ]
}
```

## Best Practices

1. **Use SecureString for secrets** - Encrypts values at rest
2. **Group related parameters** - Use hierarchical naming (`app/db/host`, `app/db/port`)
3. **Leverage template variables** - Avoid hardcoding environment-specific values
4. **Add descriptions** - Makes parameters self-documenting
5. **Use allowed_pattern** - Validate parameter values at deployment time
6. **Tag appropriately** - Mark sensitive parameters with tags
7. **Choose correct tier** - Use Standard tier unless you need Advanced features

## Common Use Cases

### Database Configuration

```json
{
  "parameters": [
    {"name": "db/host", "value": "mysql.example.com"},
    {"name": "db/port", "value": "3306"},
    {"name": "db/name", "value": "{{WORKLOAD_NAME}}_db"},
    {"name": "db/username", "value": "app_user"},
    {"name": "db/password", "value": "...", "type": "SecureString"}
  ]
}
```

### Feature Flags

```json
{
  "parameters": [
    {"name": "features/enabled", "value": "feature1,feature2", "type": "StringList"},
    {"name": "features/rollout-percentage", "value": "25"}
  ]
}
```

### API Configuration

```json
{
  "parameters": [
    {"name": "api/base-url", "value": "https://api.example.com"},
    {"name": "api/timeout", "value": "30", "allowed_pattern": "^[0-9]+$"},
    {"name": "api/key", "value": "...", "type": "SecureString"}
  ]
}
```

## Troubleshooting

### Parameter Already Exists

If a parameter already exists, CDK will update it. To change a parameter name, remove the old one first or use a different name.

### Value Too Large

Standard tier parameters have a 4KB limit. Use Advanced tier for larger values:

```json
{"tier": "Advanced"}
```

### Invalid Character in Name

Parameter names must:
- Start with `/`
- Contain only: `a-zA-Z0-9_.-/`
- Be 1-2048 characters

## Consuming Parameters in Other Stacks

Once created, parameters can be referenced in other stacks using SSM resolution patterns:

### Resolution Patterns

| Pattern | Parameter Type | Example |
|---------|---------------|---------|
| `{{ssm:path}}` | String or SecureString | `{{ssm:/prod/app/db/host}}` |
| `{{ssm-secure:path}}` | SecureString (explicit) | `{{ssm-secure:/prod/app/db/password}}` |
| `{{ssm-list:path}}` | StringList | `{{ssm-list:/prod/app/allowed-ips}}` |

### Example: ECS Container Environment

```json
{
  "dependencies": ["parameter-store-stack"],
  "ecs_service": {
    "containers": [{
      "environment": {
        "APP_VERSION": "{{ssm:/prod/app/version}}",
        "DB_HOST": "{{ssm:/prod/app/db/host}}",
        "DB_PASSWORD": "{{ssm-secure:/prod/app/db/password}}",
        "ALLOWED_ORIGINS": "{{ssm-list:/prod/app/cors/origins}}"
      }
    }]
  }
}
```

### Example: Lambda Function

```json
{
  "dependencies": ["parameter-store-stack"],
  "lambda": {
    "environment": {
      "TABLE_NAME": "{{ssm:/stage/app/table}}",
      "API_KEY": "{{ssm-secure:/stage/app/api-key}}",
      "REGIONS": "{{ssm-list:/stage/app/regions}}"
    }
  }
}
```

**Note:** All patterns return CDK tokens that resolve at deployment time. See [SSM Resolution Patterns](../../../interfaces/SSM_RESOLUTION_PATTERNS.md) for detailed documentation.

## See Also

- [SSM Resolution Patterns Documentation](../../../interfaces/SSM_RESOLUTION_PATTERNS.md)
- [AWS Parameter Store Documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [CDK SSM Module](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm-readme.html)
