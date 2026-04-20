# Deployment Guide

## Deployment Files

Each tenant/environment gets a `deployment.*.json` file in the `deployments/` directory:

```
cdk/
├── config.json                          # Main workload config
├── deploy.py                            # Deployment CLI
├── deployments/
│   ├── deployment.dev.json              # Development tenant
│   ├── deployment.beta.json             # Beta tenant
│   └── deployment.production.json       # Production tenant
└── configs/
    └── stacks/                          # Stack configs (referenced via __inherits__)
```

### Deployment JSON Structure

```json
{
  "parameters": {
    "AWS_ACCOUNT": "959096737760",
    "AWS_REGION": "us-east-1",
    "AWS_PROFILE": "my-profile",
    "WORKLOAD_NAME": "my-app",
    "TENANT_NAME": "beta",
    "ENVIRONMENT": "dev",
    "DEPLOYMENT_NAMESPACE": "{{TENANT_NAME}}",
    "GIT_BRANCH": "develop",

    "DYNAMODB_APP_TABLE_NAME": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-v3-app-database",
    "DYNAMODB_APP_USE_EXISTING": "true",

    "S3_WORKLOAD_BUCKET_NAME": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-v3-user-files",
    "S3_WORKLOAD_USE_EXISTING": "true",

    "HOSTED_ZONE_NAME": "{{TENANT_NAME}}.example.com",
    "API_DNS_RECORD": "api.{{HOSTED_ZONE_NAME}}"
  },

  "name": "{{TENANT_NAME}}",
  "description": "Beta environment",
  "aws_account": "{{AWS_ACCOUNT}}",
  "aws_region": "{{AWS_REGION}}",
  "aws_profile": "{{AWS_PROFILE}}",
  "git_branch": "{{GIT_BRANCH}}",
  "workload_name": "{{WORKLOAD_NAME}}",
  "tenant_name": "{{TENANT_NAME}}",

  "naming": {
    "prefix": "{{WORKLOAD_NAME}}-{{TENANT_NAME}}-{{ENVIRONMENT}}",
    "stack_pattern": "{prefix}-{stage}-{stack_name}"
  },

  "code_repository": {
    "name": "{{CODE_REPOSITORY_NAME}}",
    "connector_arn": "{{CODE_REPOSITORY_ARN}}"
  }
}
```

The `parameters` block is the source of truth. Values reference each other with `{{PLACEHOLDER}}` syntax and are resolved in multiple passes to handle chained references.

---

## Deploy Flow

```
deploy.sh → deploy.py → CdkDeploymentCommand
                │
                ├── Auto-discovers deployment.*.json files
                ├── Resolves {{PLACEHOLDER}} references in parameters
                ├── Sets environment variables from parameters
                ├── Validates required variables
                └── Runs: npx cdk synth | diff | deploy
```

### Running

```bash
# Interactive — prompts for environment and operation
python deploy.py

# Non-interactive
python deploy.py -e dev -o synth     # synth only
python deploy.py -e dev -o deploy    # deploy
python deploy.py -e dev -o diff      # diff

# Validate config without deploying
python deploy.py --dry-run
```

### Interactive Mode

1. Select deployment environment (from discovered `deployment.*.json` files)
2. Select operation (synth, deploy, diff)
3. Validates all required variables
4. Displays configuration summary
5. Executes CDK command

---

## Parameter Resolution Order

When resolving `{{PLACEHOLDER}}` values:

1. **CDK context** (`-c Key=Value` on command line) — highest priority
2. **Environment variable** (`env_var_name` from config) — from deployment JSON or shell
3. **Static `value`** in config.json — acts as default
4. **`default_value`** — last resort fallback

```json
{
  "placeholder": "{{DEVOPS_ACCOUNT}}",
  "env_var_name": "DEVOPS_ACCOUNT",
  "cdk_parameter_name": "DevOpsAccountNumber",
  "value": "974817967438"
}
```

Here, `value: "974817967438"` is used if neither CDK context nor `DEVOPS_ACCOUNT` env var is set.

---

## Adding a New Tenant

1. Copy an existing deployment file:
   ```bash
   cp deployments/deployment.dev.json deployments/deployment.newtenant.json
   ```

2. Update the `parameters` block:
   ```json
   {
     "parameters": {
       "TENANT_NAME": "newtenant",
       "AWS_ACCOUNT": "444444444444",
       "HOSTED_ZONE_NAME": "newtenant.example.com",
       "DYNAMODB_APP_USE_EXISTING": "false",
       "S3_WORKLOAD_USE_EXISTING": "false"
     }
   }
   ```

3. Deploy:
   ```bash
   python deploy.py -e newtenant -o deploy
   ```

That's it. The config.json template + deployment JSON parameters handle everything else.

---

## `use_existing` Toggle

Controls whether a resource is created or imported:

| Value | Behavior |
|-------|----------|
| `"false"` | Create new resource (first deployment) |
| `"true"` | Import existing resource (subsequent deployments or migration) |

Typically set in the deployment JSON parameters:

```json
{
  "parameters": {
    "DYNAMODB_APP_USE_EXISTING": "false",
    "S3_WORKLOAD_USE_EXISTING": "true"
  }
}
```

**Common pattern:** Set to `"false"` for initial deployment, then flip to `"true"` once resources exist. This prevents accidental recreation.

---

## Required Environment Variables

The deployment CLI validates these are set before running CDK:

| Variable | Description |
|----------|-------------|
| `AWS_ACCOUNT` | Target AWS account ID |
| `AWS_REGION` | Target AWS region |
| `WORKLOAD_NAME` | Workload identifier |
| `ENVIRONMENT` | Environment name |
| `TENANT_NAME` | Tenant identifier (used for namespacing) |
| `GIT_BRANCH` | Source branch for pipeline |
| `CODE_REPOSITORY_NAME` | Source repo name |
| `CODE_REPOSITORY_ARN` | CodeStar connection ARN |
