# Configuration Reference

Complete schema reference for `config.json`.

## Top-Level Structure

```json
{
  "cdk": { "parameters": [...] },
  "workload": {
    "name": "...",
    "devops": { ... },
    "deployments": [ ... ]
  }
}
```

---

## `cdk.parameters`

Defines `{{PLACEHOLDER}}` template variables that get resolved at synth time.

```json
{
  "cdk": {
    "parameters": [
      {
        "placeholder": "{{WORKLOAD_NAME}}",
        "env_var_name": "WORKLOAD_NAME",
        "cdk_parameter_name": "WorkloadName"
      },
      {
        "placeholder": "{{CDK_SYNTH_COMMAND_FILE}}",
        "value": "./commands/cdk_synth.sh",
        "cdk_parameter_name": "CdkSynthCommandFile"
      },
      {
        "placeholder": "{{DEVOPS_ACCOUNT}}",
        "env_var_name": "DEVOPS_ACCOUNT",
        "cdk_parameter_name": "DevOpsAccountNumber",
        "value": "974817967438"
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `placeholder` | string | The `{{TOKEN}}` to find/replace throughout the config |
| `env_var_name` | string? | Environment variable to read the value from |
| `value` | string? | Static value (acts as default when env var is not set) |
| `default_value` | string? | Last-resort fallback if nothing else resolves |
| `cdk_parameter_name` | string | CDK context key name (passed via `-c Key=Value`) |
| `required` | bool | Default `true`. If `false`, missing values won't error |

**Resolution order:**
1. CDK context (`-c WorkloadName=foo`)
2. Environment variable (`WORKLOAD_NAME`)
3. Static `value` in config
4. `default_value` (last resort)

---

## `workload`

```json
{
  "workload": {
    "name": "{{WORKLOAD_NAME}}",
    "description": "My SaaS Infrastructure",
    "primary_domain": "example.com",
    "tags": { "Project": "my-project", "Team": "platform" }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Workload identifier, used in naming |
| `description` | string? | Human-readable description |
| `primary_domain` | string? | Root domain for the workload |
| `tags` | object? | Key-value tags applied to all resources |

---

## `workload.devops`

DevOps account where pipelines run.

```json
{
  "devops": {
    "account": "{{DEVOPS_ACCOUNT}}",
    "region": "{{DEVOPS_REGION}}",
    "code_repository": {
      "name": "MyOrg/MyRepo",
      "type": "connector_arn",
      "connector_arn": "arn:aws:codestar-connections:us-east-1:111111111111:connection/abc-123"
    },
    "commands": [
      {
        "name": "cdk_synth",
        "file": "{{CDK_SYNTH_COMMAND_FILE}}"
      }
    ]
  }
}
```

---

## `workload.deployments[]`

Each deployment targets an account/region with a specific mode.

```json
{
  "name": "v3-my-app-dev-pipeline",
  "environment": "{{ENVIRONMENT}}",
  "account": "{{AWS_ACCOUNT}}",
  "region": "{{AWS_REGION}}",
  "mode": "pipeline",
  "enabled": true,
  "order": 1,
  "pipeline": { ... }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Deployment identifier |
| `environment` | string | Environment name (dev, staging, prod) |
| `account` | string | Target AWS account ID |
| `region` | string | Target AWS region |
| `mode` | string | `"pipeline"` or `"stack"` |
| `enabled` | bool | Toggle deployment on/off |
| `order` | int | Sort order for pipeline deployments |
| `description` | string? | Human-readable description |
| `subdomain` | string? | Subdomain for this deployment |
| `tenant` | string? | Tenant identifier |

> **Removed:** The `naming` block (`prefix`, `stack_pattern`) has been removed. Stack names are now fully-qualified in each stack config's `name` field using `{{PLACEHOLDER}}` tokens. See [MIGRATION.md](../MIGRATION.md).

---

## `pipeline`

Nested inside a deployment when `mode: "pipeline"`.

```json
{
  "pipeline": {
    "name": "v3-my-app-dev-pipeline",
    "branch": "{{GIT_BRANCH}}",
    "enabled": true,
    "trigger_on_branch_change": true,
    "code_artifact_logins": [
      {
        "domain": "my-domain",
        "repository": "python",
        "region": "us-east-1",
        "tool": "pip"
      }
    ],
    "cross_account_role_arns": [
      "arn:aws:iam::222222222222:role/DevOpsCrossAccountAccessRole",
      "arn:aws:iam::333333333333:role/DevOpsCrossAccountAccessRole"
    ],
    "stages": [ ... ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Pipeline name in CodePipeline |
| `branch` | string | Source branch |
| `enabled` | bool | Toggle pipeline |
| `trigger_on_branch_change` | bool | Auto-trigger on push (default: `true`) |
| `code_artifact_logins` | array? | CodeArtifact auth for install steps |
| `cross_account_role_arns` | array? | IAM roles the pipeline can assume |
| `stages` | array | Ordered list of pipeline stages |

---

## `stages[]`

```json
{
  "name": "persistent-resources",
  "enabled": true,
  "wave_name": "wave-1",
  "depends_on": ["other-stage"],
  "stacks": [
    { "__inherits__": "./configs/stacks/dynamodb-app.json" },
    { "__inherits__": "./configs/stacks/s3-workload.json" }
  ],
  "builds": [
    {
      "enabled": true,
      "post_steps": [
        {
          "id": "dns-delegation",
          "name": "Cross-Account DNS Delegation",
          "commands": [
            "pip install cdk-factory boto3",
            "python -m cdk_factory.utilities.route53_delegation"
          ]
        }
      ]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Stage identifier (used in stack naming) |
| `enabled` | bool | Toggle stage |
| `wave_name` | string? | Group stages into a deployment wave |
| `depends_on` | array? | Stage dependencies |
| `stacks` | array | Stack definitions (inline or via `__inherits__`) |
| `builds` | array? | Build steps with `pre_steps` and/or `post_steps` |

### `__inherits__` (JSON Composition)

Pull stack config from an external file:

```json
{ "__inherits__": "./configs/stacks/dynamodb-app.json" }
```

Also supports `__imports__` (preferred alias) with multiple sources:

```json
{ "__imports__": ["./base.json", "./overrides.json"] }
```

When merging: dicts merge recursively, arrays extend, scalars override.

---

## Stack Config

Each stack (inline or inherited) follows this shape:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "description": "DynamoDB table for core application data",
  "module": "dynamodb_stack",
  "enabled": true,
  "phase": "persistent",
  "depends_on": ["other-stack"],
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}",
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "dynamodb": { ... }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** The literal, fully-resolved CloudFormation stack name. Use `{{PLACEHOLDER}}` tokens for workload/namespace prefixing (e.g., `{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table`). |
| `description` | string? | Human-readable label describing what the stack is for |
| `module` | string | **Required.** Registered module name (e.g., `dynamodb_stack`) |
| `enabled` | bool | Toggle stack |
| `phase` | string? | Logical grouping (`persistent`, `application`) |
| `depends_on` | array? | Stack dependencies (by name). The only accepted dependency key — `dependencies` is rejected. |
| `ssm` | object? | Top-level SSM config (see below). Must NOT be nested inside a resource block. |

> **Removed keys:** `stack_name` is no longer accepted — use `name` for the actual stack name and `description` for labels. `dependencies` is no longer accepted — use `depends_on`. The `naming` block is removed — `name` is the literal CF stack name. See [MIGRATION.md](../MIGRATION.md).

The module-specific config key (e.g., `dynamodb`, `bucket`, `api_gateway`) varies per module. See [stack-modules.md](stack-modules.md).

---

## SSM Configuration

The `ssm` block is always a top-level peer of `name`, `module`, and `enabled`. Nesting SSM inside a resource block (e.g., `dynamodb.ssm`, `bucket.ssm`) is a validation error.

```json
{
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}",
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_export` | bool | `false` | Enable automatic SSM parameter export of resource attributes |
| `namespace` | string? | `{workload_name}/{environment}` | SSM path namespace. Falls back to deployment-level defaults when absent. |
| `imports.namespace` | string? | — | Namespace for importing SSM parameters from other stacks (used by API Gateway, Monitoring) |

> **Removed key:** `ssm.enabled` is no longer accepted — use `ssm.auto_export` instead.

### SSM Namespace Precedence

1. `ssm.namespace` (from the stack config) — highest priority
2. `{workload_name}/{environment}` from the deployment config — fallback

### SSM Export Path Pattern

When `auto_export` is enabled, parameters are exported at:

```
/{namespace}/{resource_type}/{stack_name}/{attribute}
```

### SSM Examples by Stack Module

**DynamoDB** — exports `table_name`, `table_arn`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "module": "dynamodb_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "dynamodb": { "name": "my-table" }
}
```

Exports: `/my-workload/development/dynamodb/dynamodb-app-table/table_name`

**S3** — exports `bucket_name`, `bucket_arn`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-s3-workload-bucket",
  "module": "bucket_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "bucket": { "name": "my-bucket" }
}
```

**Lambda** — exports `arn`, `function-name` per function:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-lambda-app-settings",
  "module": "lambda_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "resources": [{ "name": "app-configurations", "..." : "..." }]
}
```

**SQS** — exports `arn`, `url`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-sqs-consumer-queues",
  "module": "sqs_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "sqs": { "queues": [] }
}
```

**Cognito** — exports `user-pool-id`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-cognito-primary",
  "module": "cognito_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "cognito": { "use_existing": true, "user_pool_id": "us-east-1_abc123" }
}
```

**Route53** — exports `hosted-zone-id`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-route53",
  "module": "route53_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "route53": { "hosted_zone_name": "dev.example.com", "use_existing": true }
}
```

**API Gateway** — imports Lambda ARNs via `ssm.imports.namespace`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-api-gateway-primary",
  "module": "api_gateway_stack",
  "ssm": {
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "api_gateway": { "name": "agw-primary", "..." : "..." }
}
```

**Monitoring** — imports Lambda ARNs via `ssm.imports.namespace`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-cloudwatch-dashboard",
  "module": "monitoring_stack",
  "ssm": {
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "monitoring": { "dashboard_name": "my-dashboard" }
}
```

---

## Placeholder Resolution

All config files use `{{VARIABLE}}` syntax for template variables. Placeholders are resolved before stack configs are processed.

### Syntax

```
{{VARIABLE_NAME}}
```

Variable names must match `[A-Za-z_][A-Za-z0-9_]*`.

### Resolution Sources (in order)

There are three resolution paths, executed in sequence:

1. **`deployment.*.json` parameters** — resolved first by `deploy.py`. Supports chained references (up to 5 passes).
2. **`config.json` parameters** — resolved by `CdkConfig` via `JsonLoadingUtility.recursive_replace()`. Single-pass recursive replace.
3. **Stack config values** — resolved by `CdkConfig` after loading via `JsonLoadingUtility`.

Since `deploy.py` runs first and resolves all chained references, the single-pass behavior in `CdkConfig` is sufficient.

### Chained Resolution Example

In `deployment.dev.json`:

```json
{
  "parameters": {
    "TENANT_NAME": "development",
    "DEPLOYMENT_NAMESPACE": "{{TENANT_NAME}}",
    "HOSTED_ZONE_NAME": "{{TENANT_NAME}}.aplos-nca.com",
    "API_DNS_RECORD": "api.{{HOSTED_ZONE_NAME}}"
  }
}
```

Resolution (multi-pass):
1. `DEPLOYMENT_NAMESPACE` → `development`
2. `HOSTED_ZONE_NAME` → `development.aplos-nca.com`
3. `API_DNS_RECORD` → `api.development.aplos-nca.com`

### Unresolved Placeholder Errors

After resolution, any remaining `{{...}}` tokens raise a descriptive error:

```
Unresolved placeholder '{{VARIABLE}}' in config. Add this parameter to your deployment JSON or config.json.
```
