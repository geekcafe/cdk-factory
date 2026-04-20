# Naming & SSM Conventions

## Stack Naming

Stack names are declarative. The `name` field in each stack config is the literal CloudFormation stack name — no implicit transformation, no pattern assembly.

Placeholders (`{{PLACEHOLDER}}`) are resolved before the name is used:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "module": "dynamodb_stack"
}
```

With `WORKLOAD_NAME=aplos-nca-saas` and `DEPLOYMENT_NAMESPACE=development`, the CloudFormation stack name is:

```
aplos-nca-saas-development-dynamodb-app-table
```

There is no `naming` block, no `prefix`, no `stack_pattern`, and no `build_stack_name()`. The `name` field is what you see in CloudFormation.

### ⚠️ Guardrails

**Never rename on live deployments.** CloudFormation identifies stacks by name. Changing `name` = new stack + orphaned old stack.

After resolution, any remaining `{{...}}` tokens raise a validation error:

```
Unresolved placeholder '{{VARIABLE}}' in config. Add this parameter to your deployment JSON or config.json.
```

---

## DEPLOYMENT_NAMESPACE

Controls both stack naming and SSM parameter paths. Defined in the deployment JSON:

```json
{
  "parameters": {
    "TENANT_NAME": "beta",
    "DEPLOYMENT_NAMESPACE": "{{TENANT_NAME}}"
  }
}
```

This enables multi-tenant deployments where each tenant gets isolated:
- Stack names: `aplos-nca-saas-beta-dynamodb-app-table`
- SSM paths: `/aplos-nca-saas/beta/dynamodb/dynamodb-app-table/table_name`

---

## SSM Parameter Paths

### Path Pattern

```
/{namespace}/{resource_type}/{stack_name}/{attribute}
```

Where `namespace` is configured via `ssm.namespace` (e.g., `aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}`):

```
/aplos-nca-saas/beta/dynamodb/dynamodb-app-table/table_name
/aplos-nca-saas/beta/s3/s3-workload-bucket/bucket_name
/aplos-nca-saas/beta/cognito/cognito-primary/user-pool-id
/aplos-nca-saas/beta/lambda/app-configurations/arn
/aplos-nca-saas/beta/route53/route53/hosted-zone-id
```

### Configuring SSM

SSM is always a **top-level** block — peer of `name`, `module`, `enabled`. Never nested inside a resource block.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "module": "dynamodb_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
  },
  "dynamodb": {
    "name": "{{DYNAMODB_APP_TABLE_NAME}}",
    "use_existing": "{{DYNAMODB_APP_USE_EXISTING}}"
  }
}
```

### SSM Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_export` | bool | `false` | Enable automatic SSM parameter export. The only trigger key — `enabled` is rejected. |
| `namespace` | string? | `{workload_name}/{environment}` | SSM path namespace |
| `imports.namespace` | string? | — | Namespace for importing SSM parameters from other stacks |

### Cross-Stack SSM Imports

Stacks that consume SSM parameters from other stacks (API Gateway, Monitoring) use `ssm.imports.namespace`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-api-gateway-primary",
  "module": "api_gateway_stack",
  "ssm": {
    "imports": {
      "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "api_gateway": {
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
