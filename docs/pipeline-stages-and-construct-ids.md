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

## How `stable_id` Is Determined

The stage construct ID follows a two-tier priority:

1. **Explicit `construct_id`** in the stage config — highest priority, used for migrations
2. **Sanitized stage name** — the default; uses the `name` field directly

The stage name is stable across all deployments (dev, alpha, demo, etc.) because it doesn't include environment-specific values. This means you can share a single `config.json` across multiple environments without conflicts.

## What Is Safe

| Action | Safe? | Notes |
|--------|-------|-------|
| Add a stack to a stage | ✅ Yes | Stage ID is the stage name, not derived from stack list |
| Remove a stack from a stage | ✅ Yes | Same reason |
| Rename a stage | ⚠️ Requires migration | See "Renaming a Stage" below |
| Move a stack between stages | ❌ No | Changes the construct tree path for all resources |

## The `construct_id` Field

Every stage supports an optional `construct_id` field that pins the stage's internal identity:

```json
{
  "name": "compute-lambdas",
  "construct_id": "lambdas",
  "stacks": [...]
}
```

**When `construct_id` is set**, it takes absolute priority. The stage name becomes a display label only — you can rename it freely without affecting deployed resources.

**When `construct_id` is not set**, the sanitized stage name is used as the construct ID.

## Renaming a Stage

To rename a stage without breaking deployed resources:

1. Add `construct_id` with the current stage name
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
Pipeline / lambdas / acme-saas-dev-lambda-workflow-app / workflow-custom-report / Resource
```

If you move `lambda-workflow-app` from the `lambdas` stage to a new `workflow` stage, the path changes:

```
Pipeline / workflow / acme-saas-dev-lambda-workflow-app / workflow-custom-report / Resource
```

Every resource gets a new logical ID. CloudFormation interprets this as "delete old resource, create new one" — which fails for resources that already exist physically (event source mappings, etc.) or causes data loss for stateful resources.

This is a fundamental CDK Pipelines constraint, not a cdk-factory limitation. Stages are deployment ordering groups — use them to control what deploys in parallel vs sequentially, but don't move stacks between them on live deployments.

## Breaking Change: Migration from Hash-Based Stage IDs

**Version history**: Older versions of cdk-factory computed the stage ID as a SHA-256 hash of sorted stack names within the stage. This was fragile — adding or removing any stack changed the hash and broke all existing resources. It also produced different hashes per environment (since stack names include the deployment namespace), making `construct_id` pinning impossible in shared configs.

The current version uses the stage name directly, which is environment-independent and stable across stack additions/removals.

### Migration Steps

Upgrading from the hash-based version is a **breaking change** for existing deployments. The recommended migration path:

1. **Delete the affected CloudFormation stacks** (e.g., lambda stacks) in each environment
2. **Update cdk-factory** to the version with name-based stable IDs
3. **Redeploy** — stacks are recreated with the new stable logical IDs

This requires brief downtime for the affected stacks. Schedule accordingly for production environments.

**Why not pin with `construct_id`?** The old hashes were environment-specific (they included the deployment namespace in stack names). A single `construct_id` in a shared config can't satisfy multiple environments simultaneously. Deleting and redeploying is the clean path.

### What to delete

Only delete stacks whose stage ID would change. Typically:
- Lambda stacks (stateless, safe to recreate)
- API Gateway stacks (stateless)

**Do NOT delete** without careful planning:
- DynamoDB stacks (stateful — enable deletion protection or use `use_existing` patterns)
- S3 stacks (stateful — data loss risk)
- Cognito stacks (stateful — user pool deletion loses all users)

For stateful stacks, if their stage ID also changed, use `construct_id` to pin them individually, or use CloudFormation import to adopt the existing resources under new logical IDs.

## Best Practices

1. **Choose stage names carefully** — they become part of the infrastructure identity. Treat them like database table names: pick once, keep forever.
2. **Stages are ordering groups** — use them to control deployment parallelism and sequencing. Don't overthink the grouping.
3. **Use `depends_on`** to control deployment order within a stage rather than creating new stages for ordering purposes.
4. **Never move stacks between stages** on a live deployment without a migration plan.
5. **New deployments just work** — no `construct_id` needed. The stage name is used directly and is stable across all environments.
