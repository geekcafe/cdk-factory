# CDK-Factory Legacy Configuration

> This document covers legacy configuration patterns that are still supported but not recommended for new projects. See [Configuration Guide](./configuration-guide.md) for the preferred approach.

## `.env` File Based Configuration

The original cdk-factory pattern used `.env` files for environment-specific values:

```
# .env.deploy.dev
AWS_ACCOUNT=123456789012
AWS_REGION=us-east-1
WORKLOAD_NAME=my-app
ENVIRONMENT=dev
```

**Why this is legacy:** `.env` files are flat key-value pairs with no structure, no validation, and no support for nested config. The JSON deployment config approach is more expressive and self-documenting.

**Migration:** Move all values into `deployment.*.json` files in the `parameters` block.

## String-Based Permissions

The old permission system used magic strings that resolved resource names from environment variables:

```json
"permissions": ["dynamodb_read", "s3_read_workload", "dynamodb_write_transient"]
```

These required specific env vars to be set (`APP_TABLE_NAME`, `S3_WORKLOAD_BUCKET_NAME`, etc.) and the mapping was implicit — you couldn't tell which table `dynamodb_read` referred to.

**Why this is legacy:** The structured format is explicit about which resource each permission targets. A lambda that needs access to two different DynamoDB tables can express that clearly.

**Migration:** Replace string permissions with structured format:

| Old (string) | New (structured) |
|---|---|
| `"dynamodb_read"` | `{ "dynamodb": "read", "table": "{{DYNAMODB_APP_TABLE_NAME}}" }` |
| `"dynamodb_write"` | `{ "dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}" }` |
| `"s3_read_workload"` | `{ "s3": "read", "bucket": "{{S3_WORKLOAD_BUCKET_NAME}}" }` |
| `"dynamodb_read_transient"` | `{ "dynamodb": "read", "table": "{{DYNAMODB_TRANSIENT_TABLE_NAME}}" }` |
| `"audit_logging"` | `{ "dynamodb": "write", "table": "{{DYNAMODB_AUDIT_TABLE_NAME}}" }` |

Simple string permissions that don't have a resource target (`"cognito_admin"`, `"parameter_store_read"`) are still valid and preferred.

## Deployment Config — Values at Top Level

The older pattern put values directly at the top level of the deployment config:

```json
{
  "name": "dev",
  "aws_account": "123456789012",
  "workload_name": "my-app",
  "parameters": {
    "DYNAMODB_APP_TABLE_NAME": "my-table"
  }
}
```

**Why this is legacy:** Values are split between top-level fields and the `parameters` block, creating duplication. The `STANDARD_ENV_VARS` mapping in `deploy.py` bridges the gap but adds complexity.

**Migration:** Move all variable values into `parameters` and reference them via `{{PLACEHOLDER}}` in the structural fields below. See the [Configuration Guide](./configuration-guide.md) for the preferred pattern.

## `cdk.parameters` Placeholder Array

The `cdk.parameters` array in `config.json` maps `{{PLACEHOLDER}}` strings to environment variables:

```json
{
  "cdk": {
    "parameters": [
      {
        "placeholder": "{{ENVIRONMENT}}",
        "env_var_name": "ENVIRONMENT",
        "cdk_parameter_name": "Environment"
      }
    ]
  }
}
```

**Status:** Still required as the bridge between deployment configs and the structural config. Keep it minimal — only define placeholders actually used in config.json.

## `workload.resources` Section

The legacy Acme-SaaS-Application config defined resources at the workload level:

```json
{
  "workload": {
    "resources": {
      "ecr_repositories": [...],
      "lambda_functions": { "__inherits__": "./configs/resources/..." }
    }
  }
}
```

**Migration:** Resources are now defined in individual stack config files under `configs/stacks/`. Each stack is self-contained.

## One-File-Per-Lambda with `stack` Field

Individual JSON files per Lambda with a `stack` field for grouping:

```json
{ "name": "get-user", "stack": "users", "handler": "app.lambda_handler" }
```

**Status:** Supported via `lambda_config_dir` in cdk-factory. Both this format and the grouped `resources` array work simultaneously.

## `naming_prefix` Top-Level Field

```json
{ "naming_prefix": "my-app-dev" }
```

**Migration:** Use the `naming` block instead:

```json
{ "naming": { "prefix": "my-app-dev", "stack_pattern": "{prefix}-{stage}-{stack_name}" } }
```

The top-level `naming_prefix` is still supported as a fallback.
