# Tree-Based Path Ownership: Solving API Gateway's Nested Stack Problem

When your REST API grows beyond a handful of endpoints, you'll hit CloudFormation's 200-resource limit per stack. The AWS CDK team knows this — they introduced `fromRestApiAttributes()` specifically to let you split resources across nested stacks. But their solution assumes something that real-world APIs rarely satisfy: that your route groups don't share path segments.

This doc explains what the official CDK pattern does, where it breaks down, and how cdk-factory's `PathOwnershipBuilder` solves the harder problem.

## Glossary

| Term | Definition |
|------|-----------|
| **Tree** | A general data structure where each node has zero or more children. Every trie is a tree, but not every tree is a trie. We use "tree-based" in the feature name because it's more approachable — most developers know what a tree is. |
| **Trie** | A specialized tree (also called a "prefix tree") where each node represents a single element of a sequence — in our case, one path segment. Nodes that share a common prefix share the same ancestors in the trie. The name comes from "re**trie**val." Pronounced "try" by most, "tree" by some (which is why we avoid the ambiguity in user-facing names). |
| **Shared Node** | A trie node where routes from 2+ route groups pass through. The parent stack owns the corresponding API Gateway Resource. |
| **Exclusive Node** | A trie node where routes from exactly 1 group pass through. The nested stack for that group owns it. |
| **Divergence Point** | A shared node that has at least one exclusive child — the point where the parent hands off resource ownership to a nested stack. |
| **Handoff Map** | A dictionary passed to each nested stack mapping path prefixes (e.g., `/v3/tenants/{tenant-id}`) to the API Gateway Resource IDs created by the parent stack at those divergence points. |

In this doc and in the codebase, we use both terms. The feature is called "tree-based path ownership" (readable, general). The implementation is a trie (technically precise). They refer to the same data structure in this context — a tree where each node is a single URL path segment.

## The Official CDK Pattern

In June 2020, the CDK team merged [commit 21a1de3](https://github.com/aws/aws-cdk/commit/21a1de308101a5f7e07558ff8c786f27e5235289) (PR #8270), which introduced `RestApi.fromRestApiAttributes()`. The [API Gateway construct library docs](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_apigateway/README.html) describe the pattern under "Breaking up Methods and Resources across Stacks."

The idea is straightforward:

1. A **root stack** creates the `RestApi` with `deploy=False`
2. **Nested stacks** import the API using `fromRestApiAttributes(restApiId, rootResourceId)`
3. Each nested stack calls `api.root.addResource('pets')` or `api.root.addResource('books')` to create its own top-level resource
4. A **deploy stack** creates the `Deployment` and `Stage` with dependencies on all methods

```python
# PetsStack (nested)
api = RestApi.from_rest_api_attributes(self, "RestApi",
    rest_api_id=props.rest_api_id,
    root_resource_id=props.root_resource_id,
)
api.root.add_resource("pets").add_method("GET", ...)

# BooksStack (nested)
api = RestApi.from_rest_api_attributes(self, "RestApi",
    rest_api_id=props.rest_api_id,
    root_resource_id=props.root_resource_id,
)
api.root.add_resource("books").add_method("GET", ...)
```

This works perfectly when `/pets` and `/books` are completely disjoint. Each nested stack creates its own resource directly under the API root. No overlap, no conflict.

## Where It Breaks Down

Real APIs aren't that clean. Consider a typical multi-tenant SaaS API:

```
/v3/tenants/{tenant-id}/users          → users group
/v3/tenants/{tenant-id}/users/{user-id} → users group
/v3/tenants/{tenant-id}/metrics         → metrics group
/v3/tenants/{tenant-id}/workflow        → workflow group
/v3/admin/warm-up                       → warm-up group
```

Multiple groups share the path segments `/v3`, `/tenants`, and `/{tenant-id}`. If two nested stacks both try to create the `v3` resource under the API root, CloudFormation throws a **409 AlreadyExists** error. The resource already exists — created by the other stack.

The CDK's `fromRestApiAttributes()` only passes the **root resource ID**. It has no mechanism for saying "here's the resource ID for `/v3/tenants/{tenant-id}` — start building below that." You'd have to manually figure out which segments are shared, create them in the parent, and pass the right resource IDs to each nested stack.

With 12 route groups and dozens of routes, doing that by hand is error-prone and brittle. Add a new route and you might accidentally introduce a new shared segment that breaks a different stack.

## The Trie-Based Solution

cdk-factory's `PathOwnershipBuilder` automates what you'd otherwise have to do manually. It builds a trie (prefix tree) of all routes across all groups, identifies every shared segment, and computes exactly which resource IDs each nested stack needs.

### How It Works

```python
from cdk_factory.stack_library.api_gateway.path_ownership_builder import (
    PathOwnershipBuilder,
)

route_groups = {
    "users": [
        {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
        {"path": "/v3/tenants/{tenant-id}/users/{user-id}", "method": "GET"},
    ],
    "metrics": [
        {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
    ],
    "warm-up": [
        {"path": "/v3/admin/warm-up", "method": "POST"},
    ],
}

builder = PathOwnershipBuilder(route_groups)
builder.build()
builder.validate()
```

After building, the trie looks like this:

```
(root)
  └── v3  [users, metrics, warm-up]  ← SHARED
        ├── tenants  [users, metrics]  ← SHARED
        │     └── {tenant-id}  [users, metrics]  ← SHARED (divergence point)
        │           ├── users  [users]  ← EXCLUSIVE
        │           │     └── {user-id}  [users]
        │           └── metrics  [metrics]  ← EXCLUSIVE
        └── admin  [warm-up]  ← EXCLUSIVE
              └── warm-up  [warm-up]
```

The builder classifies each node:
- **Shared nodes** (2+ groups pass through): `v3`, `tenants`, `{tenant-id}`
- **Exclusive nodes** (exactly 1 group): `users`, `metrics`, `admin`, `warm-up`
- **Divergence points** (shared node with an exclusive child): `v3`, `{tenant-id}`

### Parent Stack Creates Shared Resources

The parent stack creates `CfnResource` entries for every shared node:

```python
shared_nodes = builder.get_shared_nodes()
resource_id_map = {"/": api.rest_api_root_resource_id}

for node in shared_nodes:
    path_key = "/" + "/".join(node.full_path)
    parent_path_key = (
        "/" + "/".join(node.parent.full_path)
        if node.parent and node.parent.segment
        else "/"
    )
    construct_id = PathOwnershipBuilder.compute_construct_id(node.full_path)

    cfn_resource = apigateway.CfnResource(
        self,
        construct_id,
        rest_api_id=api.rest_api_id,
        parent_id=resource_id_map[parent_path_key],
        path_part=node.segment,
    )
    resource_id_map[path_key] = cfn_resource.ref
```

### Nested Stacks Get a Handoff Map

Each nested stack receives a `resource_id_handoff_map` telling it exactly where to attach:

```python
# For the "users" group:
handoff_map = builder.get_handoff_map("users")
# → {"/v3/tenants/{tenant-id}": "/v3/tenants/{tenant-id}"}

# For the "warm-up" group:
handoff_map = builder.get_handoff_map("warm-up")
# → {"/v3": "/v3"}
```

The nested stack imports the handoff resource and creates only its exclusive segments below it:

```python
# Users nested stack receives:
resource_id_handoff_map = {"/v3/tenants/{tenant-id}": "cfn-ref-to-tenant-id-resource"}

# It imports that resource and creates only "users" and "{user-id}" below it.
# It never touches "v3", "tenants", or "{tenant-id}" — those belong to the parent.
```

## Comparison

| Aspect | CDK Official Pattern | PathOwnershipBuilder |
|--------|---------------------|---------------------|
| Handles shared path segments | No — assumes disjoint resources | Yes — trie identifies all shared segments |
| Parent creates shared resources | Only passes root resource ID | Creates `CfnResource` for every shared node |
| Handoff granularity | Single point (API root) | Multiple divergence points per group |
| Conflict detection | None — fails at CloudFormation deploy time | Synthesis-time `validate()` with actionable errors |
| Scales to 12+ groups with overlapping paths | Breaks with 409 errors | Designed for this |
| Handles route additions over time | Manual re-partitioning required | Automatic — trie recomputes ownership |
| Construct ID stability | N/A | Deterministic IDs from path content, not group membership |

## What We Share With the Official Approach

We're not fighting the CDK — we're building on the same primitives:

- **Parent stack owns RestApi, Authorizer, Deployment, Stage** — same architecture
- **Nested stacks import resources via `Resource.from_resource_attributes()`** — the same API introduced in commit 21a1de3
- **Deployment depends on all nested stack methods** — same dependency pattern
- **Each nested stack only creates resources it owns** — same principle of ownership

The difference is that the official pattern requires you to manually ensure no two stacks share a path segment. `PathOwnershipBuilder` does that analysis for you, automatically, at synthesis time.

## Design Principles

### Pure Logic, No CDK Dependencies

The `PathOwnershipBuilder` module has zero CDK imports. It operates on plain Python dicts, sets, and dataclasses. This makes it trivial to unit test and property test without synthesizing stacks.

### Deterministic Construct IDs

Construct IDs are derived from path content:
```
/v3/tenants/{tenant-id} → SharedPath-v3-tenants-tenant-id
```

This means adding or removing routes doesn't rename existing CloudFormation resources. Stability matters — renaming a resource means CloudFormation deletes and recreates it, which can cause downtime.

### Fail Fast

If the builder detects a configuration that would cause a cross-stack conflict, it raises a `ValueError` during CDK synthesis — before you ever hit CloudFormation. The error message tells you exactly which segment is conflicting and which groups claim it.

### Single-Group Passthrough

When all routes belong to a single group (or nested stacks are disabled), the builder does nothing. It passes the API root resource ID directly to the nested stack. No shared resources are created in the parent. Zero overhead for the simple case.

## When to Use What

**Use the CDK's built-in pattern when:**
- Your route groups have completely disjoint top-level paths (e.g., `/pets` and `/books`)
- You're manually managing a small number of nested stacks
- You don't need automatic conflict detection

**Use PathOwnershipBuilder when:**
- Multiple route groups share path segments (the common case in tenant-scoped APIs)
- You have many groups (5+) and want automatic ownership computation
- You want synthesis-time conflict detection instead of deploy-time 409 errors
- Routes are added incrementally over time and you don't want to manually re-partition

## Further Reading

- [CDK commit 21a1de3](https://github.com/aws/aws-cdk/commit/21a1de308101a5f7e07558ff8c786f27e5235289) — The PR that introduced `fromRestApiAttributes()`
- [AWS CDK API Gateway Construct Library](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_apigateway/README.html) — Official docs including the nested stack example
- [CloudFormation resource limits](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-limits.html) — The 500-resource limit that motivates nested stacks
- `src/cdk_factory/stack_library/api_gateway/path_ownership_builder.py` — The implementation
- `tests/properties/test_path_ownership_builder.py` — Property-based tests proving correctness invariants
