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

### ⚠️ Export/import path agreement — the #1 cross-stack deployment footgun

A cross-stack SSM reference only works if the **exporting** stack writes the
parameter to the **exact path** the **importing** stack reads. These are two
independent config values in two different stacks, and nothing validates that
they agree until deploy time — so a mismatch is silent until it fails.

The canonical case: an **API Gateway route** backed by a Lambda in a **lambda
stack**.

- The lambda stack **exports** each function ARN at
  `/{lambda_stack.ssm.namespace}/{lambda_name}/arn`.
- The API Gateway stack, for a route that uses `lambda_name` (auto-discovery),
  **reads** `/{api_gateway.ssm.imports.namespace}/{lambda_name}/arn`.

**These two namespaces must be identical.** If the lambda stack adds a suffix its
siblings don't use — e.g. `.../lambda/event_bus` or `.../event_bus` instead of the
shared `.../lambda` (or flat `{workload}/{env}`) namespace — the API Gateway
auto-discovery builds a path that was never written, and the API Gateway stack's
**`prepare` phase fails at synth** (before any resource deploys) with:

```
Unable to fetch parameters [/acme-saas/prod/acme-saas-prod-<lambda>/arn]
from parameter store for this account.
(Service: AmazonCloudFormation; Status Code: 400; ... ValidationError)
```

The Lambda itself deployed fine and its ARN *is* in SSM — just under a different
path than the importer looked. The fix is to make the exporter and importer agree
(align the lambda stack's `ssm.namespace`), **not** to patch over it with a
per-route `lambda_arn_ssm_path` (that works, but it hides the inconsistency and
every new route to that stack has to remember the override).

#### Rules for clean cross-stack SSM (export → import)

1. **All lambda stacks that back routes on the same API Gateway share ONE
   `ssm.namespace`**, and the API Gateway's `ssm.imports.namespace` (or
   `imports.lambda_namespace`) equals it **exactly**. No per-stack suffixes
   (`.../lambda/foo`, `.../bar`) for a stack whose functions are API routes — the
   importer resolves a single namespace and cannot search across several. (See
   also `ssm-parameter-naming-convention.md` → "API Gateway Constraint".)
2. **The escape hatch is explicit, not a default.** A route may set
   `lambda_arn_ssm_path` to read a non-conforming path verbatim. Reserve it for a
   genuinely foreign producer you don't control — not to work around your own
   lambda stack using the wrong namespace. Prefer fixing the exporter.
3. **Renaming an export path replaces the parameter.** Because the exported
   `AWS::SSM::Parameter` is CloudFormation-managed, changing a stack's
   `ssm.namespace` makes CF create the new path and delete the old one on the next
   deploy (the old params are cleaned up, not orphaned). Deploy the **exporting**
   stack before (or in the same run as) the importer so the new path exists when
   the importer's `prepare` resolves it.
4. **Keep unrelated namespaces unrelated.** A stack can own several *distinct*
   SSM namespaces for different resource kinds (e.g. a lambda stack whose SQS
   triggers read `/{workload}/{env}/sqs/...` while its functions export to the
   shared lambda namespace). Only the **lambda-export** namespace must match the
   API Gateway importer; the queue/topic namespaces are independent and should not
   be changed to "match" anything.
5. **When in doubt, verify the live path.** `aws ssm get-parameters-by-path
   --path /{workload}/{env} --recursive` shows exactly where a producer wrote its
   params; compare against the path the importer builds
   (`/{imports.namespace}/{lambda_name}/arn`).


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
