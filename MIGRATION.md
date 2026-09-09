# Migration Guide — Config Consistency Release

This release standardizes JSON configuration patterns across all stack modules. cdk-factory is in beta — deprecated patterns are removed outright with prescriptive validation errors.

---

## Breaking Changes Summary

| # | Change | Old Pattern | New Pattern |
|---|--------|-------------|-------------|
| 1 | [Nested SSM removal](#1-nested-ssm-blocks-removed) | `dynamodb.ssm`, `bucket.ssm`, etc. | Top-level `ssm` block |
| 2 | [`ssm.enabled` removal](#2-ssmenabled-removed) | `ssm.enabled: true` | `ssm.auto_export: true` |
| 3 | [`bucket.exists` removal](#3-bucketexists-removed) | `bucket.exists: true` | `bucket.use_existing: true` |
| 4 | [`dependencies` → `depends_on`](#4-dependencies-key-removed) | `dependencies` key | `depends_on` key only |
| 5 | [`stack_name` removal](#5-stack_name-key-removed) | `stack_name` key | `name` + `description` |
| 6 | [`naming` block removed](#6-naming-block-removed) | `naming.prefix` + `naming.stack_pattern` | Fully-qualified `name` with `{{PLACEHOLDER}}` tokens |

---

## 1. Nested SSM Blocks Removed

SSM configuration must be a top-level peer of `name`, `module`, and `enabled`. Resource-nested SSM blocks are rejected.

**Before (rejected):**

```json
{
  "name": "dynamodb-app-table",
  "module": "dynamodb_stack",
  "dynamodb": {
    "name": "my-table",
    "ssm": {
      "auto_export": true,
      "namespace": "acme-saas/development"
    }
  }
}
```

**After (canonical):**

```json
{
  "name": "dynamodb-app-table",
  "module": "dynamodb_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "acme-saas/development"
  },
  "dynamodb": {
    "name": "my-table"
  }
}
```

**Validation error:**
```
SSM config must be at the stack top level. Move 'dynamodb.ssm' to a top-level 'ssm' block. See MIGRATION.md.
```

**Affected resource keys:** `dynamodb`, `bucket`, `cognito`, `route53`, `sqs`, `api_gateway`, `state_machine`, `monitoring`, `resources`

---

## 2. `ssm.enabled` Removed

The `ssm.enabled` key (used by Lambda and SQS stacks) is replaced by `ssm.auto_export`. All modules now use the same trigger key.

**Before (rejected):**

```json
{
  "name": "lambda-app-settings",
  "module": "lambda_stack",
  "ssm": {
    "enabled": true,
    "namespace": "acme-saas/development"
  }
}
```

**After (canonical):**

```json
{
  "name": "lambda-app-settings",
  "module": "lambda_stack",
  "ssm": {
    "auto_export": true,
    "namespace": "acme-saas/development"
  }
}
```

**Validation error:**
```
'ssm.enabled' is removed. Use 'ssm.auto_export: true' instead. See MIGRATION.md.
```

---

## 3. `bucket.exists` Removed

The legacy `exists` key on S3 bucket configs is removed. Use `use_existing` instead.

**Before (rejected):**

```json
{
  "name": "s3-workload-bucket",
  "module": "bucket_stack",
  "bucket": {
    "name": "my-bucket",
    "exists": true
  }
}
```

**After (canonical):**

```json
{
  "name": "s3-workload-bucket",
  "module": "bucket_stack",
  "bucket": {
    "name": "my-bucket",
    "use_existing": true
  }
}
```

**Validation error:**
```
'bucket.exists' is removed. Use 'bucket.use_existing' instead. See MIGRATION.md.
```

**Additional rule:** When `use_existing` is `true`, the resource `name` field is required. Missing it produces:
```
'bucket' has 'use_existing: true' but no 'name' field. Provide the resource name. See MIGRATION.md.
```

---

## 4. `dependencies` Key Removed

Stack configs must use `depends_on` for dependency declarations. The `dependencies` JSON key is no longer accepted. The `StackConfig.dependencies` Python property now reads from `depends_on`.

**Before (rejected — both keys present):**

```json
{
  "name": "api-gateway-primary",
  "depends_on": ["lambda-app-settings"],
  "dependencies": ["lambda-app-settings"]
}
```

**After (canonical):**

```json
{
  "name": "api-gateway-primary",
  "depends_on": ["lambda-app-settings"]
}
```

**Validation error:**
```
Stack config contains both 'depends_on' and 'dependencies'. Use 'depends_on' only. See MIGRATION.md.
```

---

## 5. `stack_name` Key Removed

The `stack_name` escape hatch is removed. The top-level `name` field IS the literal CloudFormation stack name (used for the CDK construct ID). Use `description` for human-readable labels.

**Before (rejected):**

```json
{
  "name": "my-stack",
  "stack_name": "custom-cf-stack-name",
  "module": "dynamodb_stack"
}
```

**After (canonical):**

```json
{
  "name": "dynamodb-app-table",
  "description": "DynamoDB table for core application data",
  "module": "dynamodb_stack"
}
```

**Validation error:**
```
'stack_name' is not a valid key. Use 'name' for the actual stack name (construct ID / CloudFormation stack name) and 'description' for a human-readable label. See MIGRATION.md.
```

---

## 6. `naming` Block Removed

The `naming` block in deployment configs (`naming.prefix`, `naming.stack_pattern`) and the `build_stack_name()` method are removed. Stack names are now declarative — the `name` field in each stack config is the literal, fully-resolved CloudFormation stack name.

Use `{{PLACEHOLDER}}` tokens in the `name` field to include workload name, namespace, etc.

**Before (rejected — deployment config with naming block):**

```json
{
  "naming": {
    "prefix": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}",
    "stack_pattern": "{prefix}-{stage}-{stack_name}"
  }
}
```

With stack config:

```json
{
  "name": "dynamodb-app-table",
  "module": "dynamodb_stack"
}
```

**After (canonical — fully-qualified name in stack config):**

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "module": "dynamodb_stack"
}
```

No `naming` block in the deployment config. The stack `name` resolves to the literal CloudFormation stack name (e.g., `acme-saas-development-dynamodb-app-table`).

**Validation error (if `naming` block is present in deployment config):**
```
The 'naming' block has been removed from cdk-factory. Stack configs must use fully-qualified names in the 'name' field. See MIGRATION.md.
```

---

## Upgrade Checklist

Follow these steps to migrate your consumer configs:

1. **Move nested SSM blocks to top level**
   - For each stack config, check if `dynamodb.ssm`, `bucket.ssm`, `cognito.ssm`, `route53.ssm`, `api_gateway.ssm`, or `monitoring.ssm` exists
   - Move the entire `ssm` object to the stack top level (peer of `name`, `module`)
   - Remove the `ssm` key from inside the resource block

2. **Rename `ssm.enabled` → `ssm.auto_export`**
   - Search all configs for `"enabled"` inside an `ssm` block
   - Replace with `"auto_export"`

3. **Replace `bucket.exists` with `bucket.use_existing`**
   - Search S3 configs for `"exists"` inside a `bucket` block
   - Replace with `"use_existing"`

4. **Use `depends_on` only**
   - Remove any `"dependencies"` keys from stack configs
   - Ensure `"depends_on"` is present where needed

5. **Remove `stack_name` keys**
   - Remove any `"stack_name"` keys from stack configs
   - Ensure `"name"` is the intended CloudFormation stack name
   - Add `"description"` for human-readable labels

6. **Remove `naming` block and use fully-qualified stack names**
   - Remove the `"naming"` block from all deployment JSON files
   - Update every stack config `"name"` to include the full prefix: `{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-<stack-name>`
   - Ensure `DEPLOYMENT_NAMESPACE` is defined in your deployment JSON parameters
   - The resolved `name` must match the existing CloudFormation stack name exactly, or CloudFormation will create a new stack

7. **Add `description` fields**
   - Add a `"description"` field to each stack config for readability

8. **Verify `use_existing` resources have `name`**
   - For any resource with `"use_existing": true`, ensure the `"name"` field is present

9. **Run validation**
   - Run `cdk synth` — the `ConfigValidator` will catch any remaining deprecated patterns with prescriptive error messages
   - Any unresolved `{{...}}` placeholders will also raise errors

---

## Affected Config Parser Classes

| Class | File | Changes |
|-------|------|---------|
| `ConfigValidator` | `configurations/config_validator.py` | **New.** Validates all canonical patterns, rejects deprecated ones. Called before `module.build()`. |
| `StackConfig` | `configurations/stack.py` | `dependencies` property reads from `depends_on`. Added `ssm_config`, `ssm_namespace`, `ssm_auto_export`, `description` properties. Clarified `name` as actual stack name. |
| `S3BucketConfig` | `configurations/resources/s3.py` | Removed `exists` property and fallback. `use_existing` reads only from `use_existing` key. Added S3 name validation (3–63 chars, lowercase, no consecutive dots). |
| `DynamoDBConfig` | `configurations/resources/dynamodb.py` | Added name validation (3–255 chars, alphanumeric + underscores + hyphens + dots). |
| `LambdaFunctionConfig` | `configurations/resources/lambda_function.py` | Added name validation (1–64 chars, alphanumeric + hyphens + underscores). |

## Affected Stack Modules

| Module | File | Changes |
|--------|------|---------|
| `DynamoDBStack` | `stack_library/dynamodb/dynamodb_stack.py` | Reads SSM from `stack_config.ssm_config` instead of `dynamodb.ssm`. |
| `S3BucketStack` | `stack_library/buckets/bucket_stack.py` | Reads SSM from `stack_config.ssm_config` instead of `bucket.ssm`. |
| `LambdaStack` | `stack_library/aws_lambdas/lambda_stack.py` | Changed `ssm_config.get("enabled")` → `ssm_config.get("auto_export")`. |
| `SQSStack` | `stack_library/simple_queue_service/sqs_stack.py` | Changed `enabled` → `auto_export`. |
| `ApiGatewayStack` | `stack_library/api_gateway/api_gateway_stack.py` | Reads SSM imports from `stack_config.ssm_config` instead of `api_gateway.ssm`. |
| `CognitoStack` | `stack_library/cognito/` | Reads SSM from `stack_config.ssm_config` instead of `cognito.ssm`. |
| `Route53Stack` | `stack_library/route53/` | Reads SSM from `stack_config.ssm_config` instead of `route53.ssm`. |
| `MonitoringStack` | `stack_library/monitoring/` | Reads SSM from `stack_config.ssm_config` instead of `monitoring.ssm`. |


---

# Migration Guide — Deterministic SSM Logical IDs (1.11.0)

This release changes how CloudFormation **logical IDs** are generated for
imported SSM parameters. It does not change any real resource configuration, but
because logical IDs change, **upgrading produces a one-time CloudFormation diff**
on any stack that imports SSM parameters. Read this before upgrading a stack that
is already deployed.

## What changed and why

Construct IDs for imported SSM parameters were built with Python's builtin
`hash(path)`. Builtin `hash()` is seeded per process (`PYTHONHASHSEED`), so the
same SSM path produced a **different** logical ID on every `cdk synth`. Any
resource that referenced such a parameter therefore looked "changed" on every
deploy. In most cases that is a harmless cosmetic diff, but where the reference
sits in a **replacement-sensitive** property it can cascade into a resource
replacement.

Real-world example that motivated the fix: an ECS service references its capacity
provider and target group through imported SSM parameters. The churning parameter
logical IDs made the `AWS::ECS::Service` look changed, which cascaded into
re-creating its Application Auto Scaling target-tracking policies and failed the
deploy with:

```
Only one TargetTrackingScaling policy for a given metric specification is allowed.
```

1.11.0 replaces `hash(path)` with a stable content hash
(`int(hashlib.sha1(path.encode()).hexdigest(), 16) % 10000`), so the logical IDs
are identical across synths, processes, and machines going forward.

## Impact when you upgrade an already-deployed stack

- **First deploy after upgrading:** the imported-SSM CfnParameter logical IDs
  change once (from the old random value to the new stable value), then never
  again.
- **Most stacks:** cosmetic — only the parameter's logical ID is renamed; the
  resolved value and every real resource are unchanged.
- **Replacement risk (rare):** only when an SSM-imported value is referenced by
  an **immutable / replacement-forcing** property AND the consuming resource has
  a **fixed physical name** or a service-side singleton constraint. Known
  categories to check:
  - `AWS::ECS::Service` `CapacityProviderStrategy` / `LoadBalancers`
  - `AWS::ECS::CapacityProvider` (fixed `Name`) referencing an ASG
  - `AWS::ApplicationAutoScaling::ScalingPolicy` (one target-tracking policy per
    metric per scalable target)
  - Any resource with a fixed physical name (e.g. an S3 `BucketName`) whose
    changed reference forces replacement
  Auto-named resources (no fixed physical name) are safe — CloudFormation
  create-then-deletes with a new name and repoints references.

## Required pre-flight: `cdk diff` before deploying

For any already-deployed stack, run `cdk diff` before deploying the upgrade and
inspect it:

1. If the only differences are `AWS::SSM::Parameter` / CfnParameter logical-ID
   renames and no real resource is listed as **replace** → safe to deploy.
2. If a fixed-name resource or an Application Auto Scaling policy shows
   **replacement**, reconcile it first. For the ECS Application Auto Scaling case,
   delete the pre-existing target-tracking policies before the deploy so
   CloudFormation can recreate them cleanly:
   ```
   aws application-autoscaling delete-scaling-policy \
     --service-namespace ecs \
     --resource-id service/<cluster>/<service> \
     --scalable-dimension ecs:service:DesiredCount \
     --policy-name <existing CPU policy name>
   # repeat for the Memory policy
   ```
   The task count holds during the brief window (the capacity provider still
   manages EC2 instances), and the deploy recreates the policies. After this
   one-time reconcile, the stable logical IDs prevent recurrence.

---

# Migration Guide — RDS Credentials Secret Pinning (1.11.0)

`RdsConfig` adds `secret_logical_id_override`. This is **opt-in** and only needed
when an already-deployed RDS stack's generated credentials secret would otherwise
be replaced by a construct-path change (e.g. this naming refactor, or moving the
stack in/out of a pipeline Stage).

## Symptom without the override

`cdk diff` shows the generated `AWS::SecretsManager::Secret` being **destroyed and
recreated** (its logical ID changed) even though the DB instance itself is stable.
Deploying would rotate the master password and can fail because the new secret
reuses the same name while the old one is pending deletion.

## Fix

1. Find the deployed secret's logical ID in the live template:
   ```
   aws cloudformation get-template --stack-name <rds-stack> \
     --query TemplateBody --output json \
     | grep -o '"[A-Za-z0-9]*Secret[A-Za-z0-9]*"'
   ```
2. Set it in the RDS config so CloudFormation sees no change:
   ```json
   {
     "rds": {
       "secret_name": "/my-namespace/rds/credentials",
       "secret_logical_id_override": "<deployed secret logical id>"
     }
   }
   ```
3. Re-run `cdk diff` and confirm the secret shows **no change** (identical logical
   ID) before deploying.

Leave `secret_logical_id_override` unset for brand-new stacks.
