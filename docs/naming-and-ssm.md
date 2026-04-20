# Naming & SSM Conventions

## Stack Naming

Stack names are built from the `naming` block in the deployment config:

```json
{
  "naming": {
    "__warning__": "Changing prefix or stack_pattern on a live deployment will create NEW CloudFormation stacks.",
    "prefix": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}",
    "stack_pattern": "{prefix}-{stage}-{stack_name}"
  }
}
```

**Default pattern:** `{prefix}-{stage}-{stack_name}`

**Example:** With prefix `aplos-nca-saas-development`, stage `persistent-resources`, stack name `dynamodb-app-table`:
```
aplos-nca-saas-development-persistent-resources-dynamodb-app-table
```

### Naming Components

| Component | Source | Example |
|-----------|--------|---------|
| `{prefix}` | `naming.prefix` (or `{workload_name}-{environment}` default) | `aplos-nca-saas-development` |
| `{stage}` | Pipeline stage `name` | `persistent-resources` |
| `{stack_name}` | Stack config `name` | `dynamodb-app-table` |

### `stack_name` Override

Escape hatch for adopting existing CloudFormation stacks:

```json
{
  "name": "dynamodb-app-table",
  "module": "dynamodb_stack",
  "stack_name": "legacy-my-app-dynamodb"
}
```

This bypasses the `stack_pattern` and uses the literal value as the CloudFormation stack name.

### ⚠️ Guardrails

**Never rename on live deployments:**
- `naming.prefix` — changing creates entirely new stacks
- Stage `name` — changing creates new stacks for every stack in that stage
- Stack `name` — changing creates a new CloudFormation stack

CloudFormation identifies stacks by name. Renaming = new stack + orphaned old stack.

---

## DEPLOYMENT_NAMESPACE

Controls both stack naming prefix and SSM parameter paths.

```json
{
  "parameters": {
    "TENANT_NAME": "beta",
    "DEPLOYMENT_NAMESPACE": "{{TENANT_NAME}}"
  }
}
```

**Default behavior:** If `DEPLOYMENT_NAMESPACE` is not set, it falls back to `TENANT_NAME`.

This enables multi-tenant deployments where each tenant gets isolated:
- Stack names: `aplos-nca-saas-beta-persistent-resources-dynamodb-app-table`
- SSM paths: `/aplos-nca-saas/beta/dynamodb/dynamodb-app-table/table-arn`

---

## SSM Parameter Paths

### Namespace Pattern (Current)

```
/{namespace}/{resource-type}/{resource-name}/{attribute}
```

Where `namespace` expands to `{workload}/{environment}`:

```
/{workload}/{environment}/{resource-type}/{resource-name}/{attribute}
```

**Example:**
```
/aplos-nca-saas/beta/dynamodb/dynamodb-app-table/table-arn
/aplos-nca-saas/beta/s3/s3-workload-bucket/bucket-name
/aplos-nca-saas/beta/cognito/cognito-primary/user-pool-id
/aplos-nca-saas/beta/lambda/app-configurations/arn
/aplos-nca-saas/beta/route53/route53/hosted-zone-id
```

### Configuring SSM

**At the stack level** (top-level `ssm` key):
```json
{
  "name": "lambda-app-settings",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
  }
}
```

**At the resource level** (inside the resource config):
```json
{
  "dynamodb": {
    "name": "{{DYNAMODB_APP_TABLE_NAME}}",
    "ssm": {
      "enabled": true,
      "auto_export": true,
      "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
    }
  }
}
```

### SSM Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable SSM parameter management |
| `auto_export` | bool | `true` | Auto-export standard attributes (ARN, name, etc.) |
| `auto_import` | bool | `true` | Auto-import from namespace |
| `namespace` | string | — | `{workload}/{environment}` portion of the path |
| `pattern` | string | `/{workload}/{environment}/{stack_type}/{resource_name}/{attribute}` | Full path pattern |
| `exports` | object/array | — | Explicit export definitions |
| `imports` | object | — | Import config with `namespace` for cross-stack lookups |

### Namespace vs Legacy Pattern

**Namespace (current):**
```json
{
  "ssm": {
    "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
  }
}
```
Produces: `/aplos-nca-saas/beta/dynamodb/dynamodb-app-table/table-arn`

**Legacy (workload/environment):**
```json
{
  "ssm": {
    "workload": "aplos-nca-saas",
    "environment": "dev"
  }
}
```
Produces: `/aplos-nca-saas/dev/dynamodb/dynamodb-app-table/table-arn`

The `namespace` approach is preferred because it decouples the SSM path from the environment name, allowing tenant-based isolation.

### Cross-Stack SSM Imports

The API Gateway stack imports Lambda ARNs via SSM namespace:

```json
{
  "api_gateway": {
    "ssm": {
      "imports": {
        "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
      }
    },
    "routes": [
      {
        "path": "/app/configuration",
        "method": "GET",
        "lambda_name": "app-configurations"
      }
    ]
  }
}
```

The `lambda_name` is resolved to an SSM path:
```
/aplos-nca-saas/beta/lambda/app-configurations/arn
```

For direct SSM path references (bypassing namespace):
```json
{
  "lambda_arn_ssm_path": "/aplos-nca-saas/dev/lambda/callback-handler/arn"
}
```
