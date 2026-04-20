# CDK-Factory Configuration Guide

This is the preferred way to configure a cdk-factory project. For legacy patterns (`.env` files, string-based permissions, `workload.resources`), see [Legacy Configuration](./configuration-legacy.md).

## Overview

A cdk-factory project has two types of configuration:

1. **Deployment configs** — one JSON file per environment/tenant, containing all environment-specific values
2. **Workload config** (`config.json`) — the structural definition of your infrastructure: stages, stacks, and their relationships

The deployment config is the single source of truth for environment-specific values. The workload config is purely structural.

## Project Structure

```
my-project/
├── cdk/
│   ├── app.py                      # CDK entry point
│   ├── deploy.py                   # Deployment CLI (subclasses CdkDeploymentCommand)
│   ├── deploy.sh                   # Shell wrapper
│   ├── config.json                 # Workload config (structural)
│   ├── configs/
│   │   └── stacks/                 # One JSON file per CloudFormation stack
│   │       ├── dynamodb-app.json
│   │       ├── s3-workload.json
│   │       ├── lambda-users.json
│   │       └── api-gateway.json
│   └── deployments/                # One JSON file per environment
│       ├── deployment.dev.json
│       ├── deployment.uat.json
│       └── deployment.prod.json
└── readme.md
```

## Deployment Config (`deployment.*.json`)

Each deployment config defines everything needed to deploy to a specific environment. The `parameters` block at the top is the single source of truth — everything below references it via `{{PLACEHOLDER}}` syntax.

```json
{
  "parameters": {
    "AWS_ACCOUNT": "123456789012",
    "AWS_REGION": "us-east-1",
    "WORKLOAD_NAME": "my-saas-app",
    "TENANT_NAME": "development",
    "ENVIRONMENT": "dev",
    "GIT_BRANCH": "develop",
    "DESCRIPTION": "Development environment",

    "DYNAMODB_APP_TABLE_NAME": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-app-database",
    "S3_WORKLOAD_BUCKET_NAME": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-files",
    "COGNITO_PRIMARY_USER_POOL_ID": "us-east-1_abc123",
    "HOSTED_ZONE_NAME": "{{TENANT_NAME}}.example.com",
    "API_DNS_RECORD": "api.{{HOSTED_ZONE_NAME}}"
  },

  "name": "dev",
  "description": "{{DESCRIPTION}}",
  "aws_account": "{{AWS_ACCOUNT}}",
  "aws_region": "{{AWS_REGION}}",
  "aws_profile": "my-dev-profile",
  "git_branch": "{{GIT_BRANCH}}",
  "workload_name": "{{WORKLOAD_NAME}}",
  "tenant_name": "{{TENANT_NAME}}",

  "naming": {
    "prefix": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-{{ENVIRONMENT}}",
    "stack_pattern": "{prefix}-{stage}-{stack_name}"
  },

  "code_repository": {
    "name": "MyOrg/my-repo",
    "connector_arn": "arn:aws:codeconnections:us-east-1:123456789012:connection/abc-123"
  }
}
```

### How It Works

1. `parameters` at the top defines all variable values
2. Everything below references them via `{{PLACEHOLDER}}` syntax
3. The deployment CLI resolves all `{{}}` references at load time — before CDK runs
4. Chained references work: `{{HOSTED_ZONE_NAME}}` resolves first, then `{{API_DNS_RECORD}}` uses the resolved value

### Parameters

The `parameters` block is what you edit per environment. Use `<TODO>` as a placeholder for values you haven't filled in yet — the deployment CLI will catch these and give you a clear error before CDK runs.

### Naming

The `naming` block controls how CloudFormation stacks and resources are named:

- `prefix` — base prefix for all resource and stack names
- `stack_pattern` — how CF stack names are composed. Variables: `{prefix}`, `{stage}`, `{stack_name}`

For a complete override on a specific stack, add `"stack_name": "exact-cf-stack-name"` to that stack's config file.

## Stack Configs

Each stack config file defines a single CloudFormation stack:

```json
{
  "name": "lambda-users",
  "module": "lambda_stack",
  "enabled": true,
  "depends_on": [],
  "sqs_decoupled_mode": true,
  "ssm": {
    "enabled": true,
    "workload": "my-saas-app",
    "environment": "{{ENVIRONMENT}}"
  },
  "resources": [
    {
      "name": "get-user",
      "docker": { "image": true },
      "ecr": {
        "name": "my-org/user-service",
        "use_existing": true,
        "region": "us-east-1",
        "account": "123456789012"
      },
      "image_config": {
        "command": ["my_app.handlers.users.get.handler"]
      },
      "api": {
        "route": "/users/{user-id}",
        "method": "get"
      },
      "permissions": [
        { "dynamodb": "read", "table": "{{DYNAMODB_APP_TABLE_NAME}}" },
        { "dynamodb": "write", "table": "{{DYNAMODB_APP_TABLE_NAME}}" }
      ],
      "environment_variables": [
        { "name": "ENVIRONMENT" },
        { "name": "DYNAMODB_TABLE_NAME" }
      ]
    }
  ]
}
```

## Permissions

Permissions use a structured format that explicitly declares the service, action, and target resource:

```json
"permissions": [
  { "dynamodb": "read",  "table":  "{{DYNAMODB_APP_TABLE_NAME}}" },
  { "dynamodb": "write", "table":  "{{DYNAMODB_APP_TABLE_NAME}}" },
  { "dynamodb": "read",  "table":  "{{DYNAMODB_TRANSIENT_TABLE_NAME}}" },
  { "s3": "read",  "bucket": "{{S3_WORKLOAD_BUCKET_NAME}}" },
  { "s3": "write", "bucket": "{{S3_WORKLOAD_BUCKET_NAME}}" },
  "cognito_admin",
  "parameter_store_read"
]
```

### Supported Formats

| Format | Example | Use Case |
|--------|---------|----------|
| Structured DynamoDB | `{ "dynamodb": "read", "table": "my-table" }` | DynamoDB read/write/delete |
| Structured S3 | `{ "s3": "read", "bucket": "my-bucket" }` | S3 read/write/delete |
| Simple string | `"cognito_admin"` | Permissions without a resource target |
| Inline IAM | `{ "actions": [...], "resources": [...] }` | Custom one-off policies |

### DynamoDB Actions
`read` (GetItem, Scan, Query, BatchGetItem), `write` (BatchWriteItem, PutItem, UpdateItem), `delete` (DeleteItem)

### S3 Actions
`read` (GetObject), `write` (PutObject, multipart upload), `delete` (DeleteObject)

### Simple String Permissions
`cognito_admin`, `cognito_user_pool_read`, `cognito_user_pool_client_read`, `cognito_user_pool_group_read`, `parameter_store_read`

## Workload Config (`config.json`)

The workload config defines the structure of your infrastructure. The `cdk.parameters` array bridges deployment-specific values into the structural config via `{{PLACEHOLDER}}` resolution.

Keep the `cdk.parameters` array minimal — only define placeholders that are actually used in config.json.

### Stages and Stacks

Stacks are organized into pipeline stages. The `__inherits__` pattern loads stack configs from separate JSON files.

**Deployment order matters:** SQS stacks should come before Lambda stacks (so queues exist before event source mappings are created).

## Deployment CLI

```bash
# Interactive (arrow-key menu)
./deploy.sh

# Non-interactive
python deploy.py -e dev -o synth
python deploy.py -e dev -o deploy
python deploy.py -e dev -o diff
python deploy.py -e dev --dry-run
```

## Adding a New Environment

1. Create `deployments/deployment.{name}.json` — copy an existing one and update the `parameters` block
2. Run `./deploy.sh` — the new environment appears in the menu automatically

## Adding a New Stack

1. Create a stack config JSON in `configs/stacks/`
2. Add `{ "__inherits__": "./configs/stacks/my-stack.json" }` to the appropriate stage in `config.json`
3. If it's a Lambda stack with SQS consumers, add `"sqs_decoupled_mode": true`

## SSM Parameter Paths

All resources register in SSM Parameter Store for cross-stack discovery:

| Resource | Path Pattern |
|----------|-------------|
| Lambda | `/{workload}/{environment}/lambda/{name}/arn` |
| Lambda | `/{workload}/{environment}/lambda/{name}/function-name` |
| Docker Lambda | `/{workload}/{environment}/docker-lambdas/{name}/arn` |
| SQS Queue | `/{workload}/{environment}/sqs/{name}/arn` |
| SQS Queue | `/{workload}/{environment}/sqs/{name}/url` |
| S3 Bucket | `/{workload}/{environment}/s3/{stack-name}/bucket_name` |
| S3 Bucket | `/{workload}/{environment}/s3/{stack-name}/bucket_arn` |
