# Lambda Permissions Reference

Structured permission definitions for Lambda resource configs. Permissions are defined in the `permissions` array of each Lambda resource JSON file.

---

## Structured Permission Format

All permissions use a consistent structured format:

```json
{ "<service>": "<action>", "<resource_key>": "<resource_value>" }
```

---

## DynamoDB

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dynamodb` | string | Yes | Action: `read`, `write`, or `delete` |
| `table` | string | Yes | DynamoDB table name (supports `{{PLACEHOLDER}}`) |

```json
{ "dynamodb": "read", "table": "{{DYNAMODB_TABLE_NAME}}" }
{ "dynamodb": "write", "table": "{{DYNAMODB_TABLE_NAME}}" }
{ "dynamodb": "delete", "table": "my-table" }
```

Actions granted:
- `read` — GetItem, Scan, Query, BatchGetItem (table + all indexes)
- `write` — BatchWriteItem, PutItem, UpdateItem
- `delete` — DeleteItem

---

## S3

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `s3` | string | Yes | Action: `read`, `write`, or `delete` |
| `bucket` | string | Yes | S3 bucket name (supports `{{PLACEHOLDER}}`) |

```json
{ "s3": "read", "bucket": "{{MEDIA_BUCKET_NAME}}" }
{ "s3": "write", "bucket": "{{EXPORTS_BUCKET_NAME}}" }
{ "s3": "delete", "bucket": "my-bucket" }
```

---

## Cognito IDP

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cognito-idp` | string | Yes | Action: `admin`, `full`, or `read` |
| `user_pool_arn` | string | No | Explicit User Pool ARN |
| `ssm_path` | string | No | SSM parameter path containing the User Pool ARN (resolved at synth time) |
| `user_pool` | string | No | User Pool ID (ARN is constructed from account/region) |

When no resource field is provided, the permission uses a wildcard (`*`) resource.

### Resource Resolution Priority

1. `user_pool_arn` — use the literal ARN
2. `ssm_path` — resolve ARN from SSM Parameter Store at synth time
3. `user_pool` — construct ARN from pool ID + account + region
4. (none) — wildcard `*`

### Examples

```json
// Wildcard — simplest, use when pool is created in same pipeline
{ "cognito-idp": "admin" }

// Scoped via SSM — resolves at synth time from a previously deployed stack
{ "cognito-idp": "admin", "ssm_path": "/my-workload/dev/cognito/user-pool/arn" }

// Scoped via explicit ARN
{ "cognito-idp": "full", "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789:userpool/us-east-1_abc123" }

// Scoped via pool ID (ARN built from account/region)
{ "cognito-idp": "read", "user_pool": "us-east-1_abc123" }
```

### Actions Granted

| Action | IAM Actions |
|--------|-------------|
| `admin` | `cognito-idp:*` |
| `full` | `cognito-idp:*` |
| `read` | ListUsers, AdminGetUser, ListGroups, ListUserPools, ListUserPoolClients, DescribeUserPool |

### When to Use Each Approach

- **Wildcard** (`{ "cognito-idp": "admin" }`): When the Cognito User Pool is created in an earlier stage of the same pipeline and you don't yet have the pool ID/ARN as a config value. This is the simplest approach and works for single-tenant setups.

- **SSM path** (`{ "cognito-idp": "admin", "ssm_path": "..." }`): When the Cognito stack has `ssm.auto_export: true` and has been deployed at least once. The SSM parameter is resolved at CDK synth time. Best for tightening permissions after initial deployment.

- **Explicit ARN or pool ID**: When you have a pre-existing User Pool (e.g., imported from another account or created outside this pipeline).

---

## Lambda

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lambda` | string | Yes | Action: `invoke` |
| `function` | string | No | Function name or `*` (default: `*`) |

```json
{ "lambda": "invoke", "function": "*" }
{ "lambda": "invoke", "function": "my-other-function" }
```

---

## EventBridge

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `events` | string | Yes | Action: `read` or `manage` |

```json
{ "events": "read" }
{ "events": "manage" }
```

Actions granted:
- `read` — DescribeRule, ListRules, ListTargetsByRule
- `manage` — DescribeRule, EnableRule, DisableRule, ListRules, ListTargetsByRule

---

## Parameter Store

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parameter_store` | string | Yes | Action: `read` |
| `path` | string | Yes | SSM parameter path (supports wildcards, e.g., `/my-app/dev/*`) |

```json
{ "parameter_store": "read", "path": "/my-workload/dev/cognito/*" }
```

---

## String Permissions (Legacy)

Simple string values are still supported for backward compatibility:

```json
"permissions": [
  "cognito_admin",
  "parameter_store_read"
]
```

| String | Equivalent Structured |
|--------|----------------------|
| `cognito_admin` | `{ "cognito-idp": "admin" }` |
| `parameter_store_read` | `{ "parameter_store": "read", "path": "*" }` (wildcard) |
| `cognito_user_pool_read` | `{ "cognito-idp": "read" }` (wildcard) |

The structured format is preferred — it's more explicit and supports resource scoping.

---

## Complete Example

```json
{
  "name": "my-admin-handler",
  "permissions": [
    { "dynamodb": "read", "table": "{{DYNAMODB_TABLE_NAME}}" },
    { "dynamodb": "write", "table": "{{DYNAMODB_TABLE_NAME}}" },
    { "cognito-idp": "admin" },
    { "s3": "read", "bucket": "{{MEDIA_BUCKET_NAME}}" },
    { "parameter_store": "read", "path": "/my-workload/dev/cognito/*" }
  ]
}
```
