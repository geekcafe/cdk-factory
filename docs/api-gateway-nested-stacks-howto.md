# How-To: API Gateway with Lambda and Nested Stacks

This guide covers how cdk-factory deploys API Gateway REST APIs backed by Lambda functions, when and why you need nested stacks, and how the grouping configuration works.

## The Basics

cdk-factory discovers your API routes from Lambda configuration files. Each Lambda config can declare an `api` section with a route and method:

```json
{
  "name": "user-metrics",
  "description": "lists a specific users metrics",
  "docker": { "image": true },
  "ecr": {
    "name": "aplos-analytics/v3/aplos-nca-orchestration-services",
    "use_existing": true
  },
  "image_config": {
    "command": ["aplos_nca_orchestration.handlers.metrics.user_metrics.app.lambda_handler"]
  },
  "api": {
    "route": "/v3/tenants/{tenant-id}/users/{user-id}/metrics",
    "method": "get"
  }
}
```

The API Gateway stack collects all routes from all Lambda configs that it depends on, creates the REST API, path resources, methods, Lambda integrations, and permissions — all from configuration. You don't write CDK code for individual routes.

## Do I Need Nested Stacks?

**Short answer:** If you have more than ~25 routes, yes.

**Why:** Each API route creates roughly 8 CloudFormation resources (the path resource, the method, the Lambda permission, the CORS OPTIONS method, etc.). CloudFormation has a hard limit of 500 resources per stack. At ~25 routes you're already at 200 resources, and once you add the REST API itself, authorizer, deployment, stage, and other shared resources, you're pushing the limit.

### What happens if you don't enable nested stacks?

Everything goes into a single CloudFormation stack. This works fine for small APIs. Once you exceed the resource limit, your deployment fails with:

```
Resource limit exceeded: The template contains 523 resources, which exceeds the limit of 500.
```

At that point you have no choice but to split.

### What happens if you enable nested stacks without grouping?

If you set `"enabled": true` but don't provide a `"grouping"` config, cdk-factory will auto-group routes by their folder structure in the Lambda configs directory. Each subfolder under `resources/` becomes a group:

```
resources/
├── users/          → "users" group
├── metrics/        → "metrics" group
├── warm-up/        → "warm-up" group
└── workflow/api/   → "workflow/api" group
```

This automatic grouping works well when your folder structure mirrors your API domains. If it doesn't, use explicit grouping.

## Configuration Reference

The nested stacks configuration lives inside your API Gateway stack config:

```json
{
  "api_gateway": {
    "name": "my-api-gateway",
    "api_type": "REST",
    "nested_stacks": {
      "enabled": true,
      "max_resources_per_stack": 200,
      "grouping": {
        "users": ["users"],
        "workflow-api": ["workflow/api"],
        "metrics": ["metrics"],
        "warm-up": ["warm-up"]
      }
    }
  }
}
```

### Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `enabled` | Yes | `false` | Whether to split routes across nested stacks |
| `max_resources_per_stack` | No | `200` | Safety limit — warns if a group would exceed this |
| `grouping` | No | Auto-detected from folder structure | Explicit mapping of group names to Lambda config folder paths |

### Grouping Explained

The `grouping` object maps **group names** to **lists of folder paths**. Each Lambda config whose folder matches one of the paths gets assigned to that group.

```json
"grouping": {
  "users": ["users"],
  "workflow-api": ["workflow/api"],
  "metrics": ["metrics"]
}
```

This means:
- Lambda configs in `resources/users/` → assigned to the "users" nested stack
- Lambda configs in `resources/workflow/api/` → assigned to the "workflow-api" nested stack
- Lambda configs in `resources/metrics/` → assigned to the "metrics" nested stack

A group can include multiple folders:

```json
"grouping": {
  "admin": ["warm-up", "site-messages", "audit-logs"]
}
```

This puts all three folders' routes into a single "admin" nested stack.

## How It Works Under the Hood

When nested stacks are enabled:

1. **Route discovery** — cdk-factory scans all Lambda configs in dependent stacks, collects routes
2. **Grouping** — Routes are assigned to groups based on the `grouping` config (or auto-detected from folders)
3. **Path ownership analysis** — The `PathOwnershipBuilder` builds a trie of all routes, identifies which path segments are shared across groups
4. **Parent stack creates shared resources** — Path segments like `/v3`, `/tenants`, `/{tenant-id}` that multiple groups traverse are created as resources in the parent stack
5. **Nested stacks create exclusive resources** — Each nested stack only creates path segments unique to its group, receiving a handoff map of resource IDs from the parent
6. **Deployment** — The parent stack creates the Deployment and Stage with dependencies on all nested stack methods

### What the parent stack owns

- REST API
- Cognito Authorizer
- Shared path resources (segments traversed by 2+ groups)
- Deployment and Stage
- Custom domain mapping

### What each nested stack owns

- Exclusive path resources (segments only its routes use)
- HTTP Methods (GET, POST, etc.)
- Lambda permissions
- CORS OPTIONS methods

## Real-World Example

Here's the actual production config for a 12-group API:

```json
"nested_stacks": {
  "enabled": true,
  "max_resources_per_stack": 200,
  "grouping": {
    "users": ["users"],
    "workflow-api": ["workflow/api"],
    "file-system": ["file-system"],
    "legacy": ["legacy"],
    "subscriptions": ["subscriptions"],
    "metrics": ["metrics"],
    "audit-logs": ["audit-logs"],
    "report-templates": ["report-templates"],
    "tenants": ["tenants"],
    "site-messages": ["site-messages"],
    "validations": ["validations"],
    "warm-up": ["warm-up"]
  }
}
```

With this config, the path ownership builder automatically determines:
- `/v3`, `/tenants`, `/{tenant-id}` are shared across most groups → parent stack creates them
- `/admin` is exclusive to warm-up → warm-up nested stack creates it
- `/users` is exclusive to the users group → users nested stack creates it
- etc.

You don't need to think about which segments are shared. The trie figures it out.

## Adding a New Route

When you add a new Lambda with an API route:

1. Create the Lambda config JSON in the appropriate `resources/` subfolder
2. Include the `api` section with `route` and `method`
3. Make sure the subfolder is listed in the `grouping` config (or rely on auto-detection)
4. Deploy

That's it. The path ownership builder re-analyzes all routes on every synthesis. If your new route introduces a new shared segment, the builder automatically moves ownership of that segment to the parent stack. No manual intervention needed.

### Example: Adding a new endpoint

Say you want to add `GET /v3/tenants/{tenant-id}/users/{user-id}/preferences`. Create:

```
resources/users/user-preferences.json
```

```json
{
  "name": "user-preferences",
  "description": "Get user preferences",
  "docker": { "image": true },
  "ecr": {
    "name": "aplos-analytics/v3/aplos-nca-services",
    "use_existing": true
  },
  "image_config": {
    "command": ["aplos_nca_services.handlers.users.preferences.app.lambda_handler"]
  },
  "api": {
    "route": "/v3/tenants/{tenant-id}/users/{user-id}/preferences",
    "method": "get"
  }
}
```

Since it's in the `resources/users/` folder and `"users": ["users"]` is in the grouping, it automatically joins the "users" nested stack. The shared segments (`/v3/tenants/{tenant-id}`) are already owned by the parent. The users nested stack creates `/users/{user-id}/preferences` below the handoff point.

## Can I Make Grouping Fully Automatic?

**Yes.** If you omit the `grouping` field, cdk-factory auto-groups routes by their Lambda resource folder structure:

```json
"nested_stacks": {
  "enabled": true,
  "max_resources_per_stack": 200
}
```

With this config, cdk-factory resolves each route's Lambda to its folder under `resources/` and uses that folder path as the group name. If your folder structure is:

```
resources/
├── users/          → "users" group
├── metrics/        → "metrics" group
├── warm-up/        → "warm-up" group
└── workflow/api/   → "workflow/api" group
```

Then you get the same result as explicitly writing:

```json
"grouping": {
  "users": ["users"],
  "metrics": ["metrics"],
  "warm-up": ["warm-up"],
  "workflow/api": ["workflow/api"]
}
```

Any Lambda that can't be resolved to a folder goes into a `"default"` group.

**When to use explicit grouping instead:**
- You want to combine multiple folders into one group (to keep nested stack count low)
- Your folder structure doesn't match your desired API domain boundaries
- You want control over group names (they appear in CloudFormation resource names)

## Disabling Nested Stacks

If your API is small enough to fit in a single stack (under ~25 routes):

```json
"nested_stacks": {
  "enabled": false
}
```

Or simply omit the `nested_stacks` section entirely. All routes go into the parent stack using the traditional single-stack path creation. No trie, no handoff maps, no nested stacks.

## Troubleshooting

### "Resource limit exceeded"

You've outgrown single-stack mode. Enable nested stacks.

### "Cross-stack conflict: segment 'X' under 'Y' claimed by groups: [A, B]"

This shouldn't happen with the trie-based builder (it handles shared segments automatically). If you see this, it likely means a bug in the grouping config where the same Lambda config is assigned to multiple groups. Check your `grouping` paths for overlaps.

### "PathOwnershipBuilder requires at least one route group"

No routes were discovered. Check that:
- Your API Gateway stack has `depends_on` pointing to the Lambda stacks
- The Lambda configs have `api` sections with `route` and `method`
- The Lambda stacks are enabled

### Nested stack count exceeds 20

CloudFormation allows a maximum of ~200 nested stacks per parent, but cdk-factory caps at 20 for practical reasons. If you have more than 20 groups, combine related folders:

```json
"grouping": {
  "admin": ["warm-up", "site-messages", "audit-logs"],
  "core": ["users", "tenants", "subscriptions"]
}
```

## Related Docs

- [Tree-Based Path Ownership](./tree-based-path-ownership.md) — Deep dive into how the trie-based ownership model works and how it compares to the official CDK pattern
- [Configuration Reference](./configuration-reference.md) — Full reference for all stack config options
- [Stack Modules](./stack-modules.md) — Overview of available stack module types
