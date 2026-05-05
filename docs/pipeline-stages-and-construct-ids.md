# Pipeline Stages and Construct ID Stability

## Overview

CDK Pipelines uses `aws_cdk.Stage` as a scope for stacks deployed together. The stage construct ID becomes part of every CloudFormation logical ID for resources within those stacks. This has critical implications for infrastructure stability.

## How It Works

When you define a pipeline stage with stacks:

```json
{
  "name": "lambdas",
  "stacks": [
    { "__inherits__": "./configs/stacks/lambdas/lambda-workflow-app.json" },
    { "__inherits__": "./configs/stacks/lambdas/lambda-warm-up.json" }
  ]
}
```

CDK builds a construct tree like:

```
Pipeline → Stage(<stable_id>) → Stack(stack-name) → Resources
```

The `stable_id` of the stage is embedded in every resource's CloudFormation logical ID. If it changes, CloudFormation sees all resources as new and tries to recreate them — causing "AlreadyExists" errors on stateful resources like event source mappings, DynamoDB tables, and SQS queues.

## What Is Safe

| Action | Safe? | Notes |
|--------|-------|-------|
| Add a stack to a stage | ✅ Yes | Stage ID is based on stage name, not stack list |
| Remove a stack from a stage | ✅ Yes | Same reason |
| Rename a stage | ✅ Yes | As long as you keep `construct_id` set to the old value |
| Move a stack between stages | ❌ No | Changes the construct tree path for all resources |

## The `construct_id` Field

Every stage supports an optional `construct_id` field that pins the stage's internal identity:

```json
{
  "name": "compute-lambdas",
  "construct_id": "stage-a5158ab5",
  "stacks": [...]
}
```

**When `construct_id` is set**, it takes absolute priority. The stage name becomes a display label only — you can rename it freely without affecting deployed resources.

**When `construct_id` is not set**, the sanitized stage name is used as the construct ID. This is stable as long as you don't rename the stage.

## Renaming a Stage

To rename a stage without breaking deployed resources:

1. Add `construct_id` with the current stage name (or existing hash if migrating from an older version)
2. Change `name` to whatever you want

```json
// Before
{ "name": "lambdas", "stacks": [...] }

// After (safe rename)
{ "name": "compute-functions", "construct_id": "lambdas", "stacks": [...] }
```

## Why You Cannot Move Stacks Between Stages

Even though each stack has an explicit `stack_name` (making the CloudFormation stack itself portable), CDK generates **resource logical IDs** from the full construct tree path:

```
Pipeline / stage-a5158ab5 / aplos-nca-saas-dev-lambda-workflow-app / workflow-custom-report / Resource
```

If you move `lambda-workflow-app` from the `lambdas` stage to a new `workflow` stage, the path changes:

```
Pipeline / workflow / aplos-nca-saas-dev-lambda-workflow-app / workflow-custom-report / Resource
```

Every resource gets a new logical ID. CloudFormation interprets this as "delete old resource, create new one" — which fails for resources that already exist physically (event source mappings, etc.) or causes data loss for stateful resources.

This is a fundamental CDK Pipelines constraint, not a cdk-factory limitation.

## Migration from Hash-Based Stage IDs

Older versions of cdk-factory computed the stage ID as a SHA-256 hash of sorted stack names. This was fragile — adding or removing any stack from a stage changed the hash and broke all existing resources.

If you're migrating from the hash-based approach:

1. Determine the currently deployed stage hash (check your CloudFormation template's `aws:cdk:path` metadata)
2. Add `construct_id` with that hash value to your stage config
3. Update cdk-factory to the version with name-based stable IDs

Example migration:
```json
{
  "name": "lambdas",
  "construct_id": "stage-a5158ab5",
  "stacks": [...]
}
```

## Best Practices

1. **For new deployments**: No `construct_id` needed. The stage name is used directly and is stable.
2. **For existing deployments upgrading cdk-factory**: Add `construct_id` to pin the current hash before upgrading.
3. **Never move stacks between stages** on a live deployment. If you must reorganize, it requires a careful migration (export/import or stack recreation).
4. **Stages are deployment ordering groups** — use them to control what deploys in parallel vs sequentially. Don't overthink the grouping since stacks within a stage are independent CloudFormation stacks.
5. **Use `depends_on`** to control deployment order within a stage rather than creating new stages for ordering purposes.
