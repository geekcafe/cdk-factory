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

With `WORKLOAD_NAME=acme-saas` and `DEPLOYMENT_NAMESPACE=development`, the CloudFormation stack name is:

```
acme-saas-development-dynamodb-app-table
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
- Stack names: `acme-saas-beta-dynamodb-app-table`
- SSM paths: `/acme-saas/beta/dynamodb/dynamodb-app-table/table_name`

---

## SSM Parameter Paths

### Path Pattern

```
/{namespace}/{resource_type}/{stack_name}/{attribute}
```

Where `namespace` is configured via `ssm.namespace` (e.g., `acme-saas/{{DEPLOYMENT_NAMESPACE}}`):

```
/acme-saas/beta/dynamodb/dynamodb-app-table/table_name
/acme-saas/beta/s3/s3-workload-bucket/bucket_name
/acme-saas/beta/cognito/cognito-primary/user-pool-id
/acme-saas/beta/lambda/app-configurations/arn
/acme-saas/beta/route53/route53/hosted-zone-id
```

### Configuring SSM

SSM is always a **top-level** block — peer of `name`, `module`, `enabled`. Never nested inside a resource block.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "module": "dynamodb_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "acme-saas/{{DEPLOYMENT_NAMESPACE}}"
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
      "namespace": "acme-saas/{{DEPLOYMENT_NAMESPACE}}"
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
/acme-saas/beta/lambda/app-configurations/arn
```

For direct SSM path references (bypassing namespace):
```json
{
  "lambda_arn_ssm_path": "/acme-saas/dev/lambda/callback-handler/arn"
}
```


## SSM Import Logical IDs (Determinism)

When a stack imports an SSM parameter (e.g. via `imports`, `{{ssm:/path}}`
references, or a `lambda_arn_ssm_path`), cdk-factory creates a lookup construct
whose CloudFormation **logical ID** is derived from the parameter path.

As of **1.11.0**, that logical ID is **deterministic** — it is derived from a
stable content hash of the path (`sha1`), so the same SSM path always produces the
same logical ID across `cdk synth` runs, processes, and machines.

Before 1.11.0 these logical IDs used Python's builtin `hash()`, which is seeded
per process (`PYTHONHASHSEED`). That produced a different logical ID on every
synth, so resources referencing an imported SSM value appeared "changed" on every
deploy — a source of spurious CloudFormation diffs and, for
replacement-sensitive references (notably ECS `CapacityProviderStrategy` and
Application Auto Scaling policies), deploy failures.

Practical implications:

- **New stacks:** nothing to do — logical IDs are stable from the start.
- **Existing stacks upgrading to 1.11.0:** expect a **one-time** diff as the
  imported-SSM logical IDs move from their old random value to the new stable
  value. Run `cdk diff` first. Most changes are cosmetic; see `MIGRATION.md`
  ("Deterministic SSM Logical IDs") for the replacement-risk checklist and the
  Application Auto Scaling reconcile procedure.

Do not reintroduce Python's builtin `hash()` for construct IDs anywhere — always
use a content hash (`hashlib`) so logical IDs stay reproducible.
