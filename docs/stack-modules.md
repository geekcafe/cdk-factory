# Stack Modules Reference

Each module is registered via `@register_stack("module_name")` and loaded dynamically from `stack_library/`.

## Common Patterns

These patterns apply to all stack modules.

### SSM Configuration

SSM is always a **top-level** block — never nested inside a resource block. See [configuration-reference.md](configuration-reference.md#ssm-configuration) for full details.

```json
{
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  }
}
```

- `auto_export` triggers automatic SSM parameter export (replaces the removed `enabled` key)
- `namespace` sets the SSM path prefix (falls back to `{workload_name}/{environment}` from deployment config)

### `use_existing`

All resource types use `use_existing` inside their resource block to import an existing AWS resource instead of creating one. When `use_existing` is `true`, the resource `name` is required.

```json
{ "dynamodb": { "name": "my-table", "use_existing": true } }
```

> The legacy `bucket.exists` key is removed. Use `bucket.use_existing`.

### `depends_on`

Stack dependencies are declared with `depends_on` (array of stack names). The `dependencies` key is no longer accepted.

```json
{ "depends_on": ["lambda-app-settings", "dynamodb-app-table"] }
```

---

## `dynamodb_stack`

DynamoDB table — create new or import existing.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-dynamodb-app-table",
  "description": "DynamoDB table for core application data",
  "module": "dynamodb_stack",
  "enabled": true,
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "dynamodb": {
    "name": "{{DYNAMODB_APP_TABLE_NAME}}",
    "use_existing": "{{DYNAMODB_APP_USE_EXISTING}}",
    "gsi_count": 20,
    "ttl_attribute": "expires_at",
    "point_in_time_recovery": true,
    "enable_delete_protection": true,
    "replica_regions": ["us-west-2"]
  }
}
```

Auto-exports (when `auto_export: true`): `table_name`, `table_arn`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | — | **Required.** Table name (3–255 chars, alphanumeric + `_-\.`) |
| `use_existing` | bool | `false` | Import existing table instead of creating |
| `gsi_count` | int | `0` | Auto-generate N GSIs with standard naming (`gsi-N-pk`/`gsi-N-sk`) |
| `global_secondary_indexes` | array | `[]` | Named GSI definitions (cannot combine with `gsi_count`) |
| `ttl_attribute` | string? | — | Attribute name for TTL auto-deletion |
| `point_in_time_recovery` | bool | `true` | Enable PITR |
| `enable_delete_protection` | bool | `true` | Prevent accidental table deletion |
| `replica_regions` | array | `[]` | Regions for global table replicas |

### Named GSIs

```json
{
  "global_secondary_indexes": [
    {
      "index_name": "by-status",
      "partition_key": { "name": "status", "type": "S" },
      "sort_key": { "name": "created_at", "type": "N" },
      "projection": "ALL"
    },
    {
      "index_name": "by-tenant",
      "partition_key": { "name": "tenant_id", "type": "S" },
      "projection": "KEYS_ONLY"
    }
  ]
}
```

| GSI Field | Type | Description |
|-----------|------|-------------|
| `index_name` | string | **Required.** GSI name |
| `partition_key` | object | `{ "name": "...", "type": "S\|N\|B" }` |
| `sort_key` | object? | Optional sort key |
| `projection` | string | `ALL`, `KEYS_ONLY`, or `INCLUDE` |
| `non_key_attributes` | array? | For `INCLUDE` projection |

---

## `bucket_stack`

S3 bucket — create new or import existing.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-s3-workload-bucket",
  "description": "Primary workload S3 bucket",
  "module": "bucket_stack",
  "enabled": true,
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "bucket": {
    "name": "{{S3_WORKLOAD_BUCKET_NAME}}",
    "use_existing": "{{S3_WORKLOAD_USE_EXISTING}}",
    "versioned": true,
    "encryption": "s3_managed",
    "enforce_ssl": true,
    "auto_delete_objects": false,
    "removal_policy": "retain",
    "enable_event_bridge": false,
    "lifecycle_rules": [
      {
        "expiration_days": 90,
        "prefix": "tmp/"
      }
    ]
  }
}
```

Auto-exports (when `auto_export: true`): `bucket_name`, `bucket_arn`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | — | **Required.** Bucket name (3–63 chars, lowercase, no consecutive dots) |
| `use_existing` | bool | `false` | Import existing bucket. The legacy `exists` key is removed. |
| `versioned` | bool | `true` | Enable versioning |
| `encryption` | string | `s3_managed` | `s3_managed`, `kms_managed`, or `kms` |
| `enforce_ssl` | bool | `true` | Require HTTPS |
| `auto_delete_objects` | bool | `false` | Auto-delete on stack removal |
| `removal_policy` | string | `retain` | `retain`, `destroy`, or `snapshot` |
| `enable_event_bridge` | bool | `false` | Send events to EventBridge |
| `lifecycle_rules` | array | `[]` | S3 lifecycle rules |
| `public_read_access` | bool | `false` | Public read access |
| `block_public_access` | string | `block_all` | `block_all`, `block_acls`, `disabled` |

---

## `lambda_stack`

Lambda functions with Docker image, Dockerfile, or code asset packaging.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-lambda-app-settings",
  "description": "Lambda functions for application settings API",
  "module": "lambda_stack",
  "enabled": true,
  "auto_name": true,
  "depends_on": [],
  "additional_permissions": [
    { "dynamodb": "read", "table": "{{DYNAMODB_AUDIT_TABLE_NAME}}" },
    { "dynamodb": "write", "table": "{{DYNAMODB_AUDIT_TABLE_NAME}}" }
  ],
  "additional_environment_variables": [
    { "name": "DYNAMODB_AUDIT_TABLE_NAME", "value": "{{DYNAMODB_AUDIT_TABLE_NAME}}" }
  ],
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "resources": [
    {
      "name": "app-configurations",
      "description": "application settings api",
      "docker": { "image": true },
      "ecr": {
        "name": "my-org/my-service",
        "use_existing": true,
        "region": "us-east-1",
        "account": "111111111111"
      },
      "image_config": {
        "command": ["my_module.handler.lambda_handler"]
      },
      "environment_variables": [
        { "name": "ENVIRONMENT" },
        { "name": "API_VERSION", "value": "1.0" }
      ],
      "permissions": [
        { "dynamodb": "read", "table": "{{DYNAMODB_APP_TABLE_NAME}}" },
        "parameter_store_read"
      ]
    }
  ]
}
```

Auto-exports (when `auto_export: true`): `arn`, `function-name` per function

Lambda function names are validated: 1–64 chars, alphanumeric + hyphens + underscores.

### Stack-Level Properties

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_name` | bool | `true` | When `true`, CDK generates function names from the construct path. Set to `false` to use the explicit `name` from each resource. |
| `additional_permissions` | array | `[]` | Permissions merged into every resource in this stack. Resource-level permissions take precedence (duplicates are skipped). |
| `additional_environment_variables` | array | `[]` | Environment variables merged into every resource. Resource-level vars with the same `name` take precedence. |

### `skip_stack_defaults`

Any resource can opt out of stack-level merging by setting `skip_stack_defaults: true`:

```json
{
  "name": "special-function",
  "skip_stack_defaults": true,
  "permissions": [ "parameter_store_read" ],
  "environment_variables": [ { "name": "ENVIRONMENT" } ]
}
```

This resource will not receive `additional_permissions` or `additional_environment_variables` from the stack.

### Directory-Based Resource Inheritance

When a stack has many resources, split each into its own `.json` file in a directory and use `__inherits__` to load them all:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-lambda-file-system",
  "module": "lambda_stack",
  "additional_permissions": [
    { "dynamodb": "read", "table": "{{DYNAMODB_AUDIT_TABLE_NAME}}" },
    { "dynamodb": "write", "table": "{{DYNAMODB_AUDIT_TABLE_NAME}}" }
  ],
  "additional_environment_variables": [
    { "name": "DYNAMODB_AUDIT_TABLE_NAME", "value": "{{DYNAMODB_AUDIT_TABLE_NAME}}" }
  ],
  "resources": {
    "__inherits__": "./configs/stacks/lambdas/resources/file-system"
  }
}
```

When `__inherits__` points to a directory, every `.json` file in that directory is loaded and collected into an array. The directory structure looks like:

```
configs/stacks/lambdas/resources/file-system/
├── file-system-archive.json
├── file-system-download-url.json
├── file-system-get-file.json
├── file-system-upload-url.json
└── ...
```

Each file defines a single resource object (no wrapping array needed):

```json
{
  "name": "file-system-archive",
  "docker": { "image": true },
  "ecr": { "name": "my-org/my-service", "use_existing": true, "region": "us-east-1", "account": "111111111111" },
  "image_config": { "command": ["my_module.handlers.archive.lambda_handler"] },
  "memory_size": 256,
  "timeout": 30,
  "permissions": [
    { "dynamodb": "read", "table": "{{DYNAMODB_APP_TABLE_NAME}}" }
  ],
  "environment_variables": [
    { "name": "ENVIRONMENT", "value": "{{ENVIRONMENT}}" }
  ]
}
```

Stack-level `additional_permissions` and `additional_environment_variables` are merged into each loaded resource (unless `skip_stack_defaults` is set).

### Lambda Packaging Modes

**Docker image** (from ECR):
```json
{
  "docker": { "image": true },
  "ecr": { "name": "my-repo", "use_existing": true, "region": "us-east-1", "account": "111111111111" },
  "image_config": { "command": ["module.handler"] }
}
```

**Dockerfile** (build from source):
```json
{
  "docker": { "file": true, "path": "./docker", "file_name": "Dockerfile" }
}
```

**Code asset** (zip):
```json
{
  "code_asset": { "path": "./lambda_code", "handler": "index.handler", "runtime": "python3.12" }
}
```

### SQS Integration

```json
{
  "name": "my-worker",
  "sqs": {
    "consumer": {
      "queue_name": "work-queue",
      "batch_size": 10
    },
    "producer": {
      "queue_name": "output-queue"
    },
    "dlq_consumer": {
      "queue_name": "work-queue-dlq"
    }
  }
}
```

### EventBridge Triggers

```json
{
  "event_bridge": {
    "rules": [
      {
        "name": "daily-trigger",
        "schedule": "rate(1 day)"
      },
      {
        "name": "pattern-trigger",
        "event_pattern": {
          "source": ["my.source"],
          "detail-type": ["MyEvent"]
        }
      }
    ]
  }
}
```

### S3 Triggers

```json
{
  "s3_trigger": {
    "bucket_name": "{{S3_UPLOAD_BUCKET_NAME}}",
    "events": ["s3:ObjectCreated:*"],
    "prefix": "uploads/"
  }
}
```

### Resource Policies

```json
{
  "resource_policies": [
    {
      "principal": "apigateway.amazonaws.com",
      "actions": ["lambda:InvokeFunction"]
    }
  ]
}
```

---

## `api_gateway_stack`

REST or HTTP API Gateway with Lambda integration.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-api-gateway-primary",
  "description": "Primary REST API Gateway",
  "module": "api_gateway_stack",
  "enabled": true,
  "depends_on": ["lambda-app-settings"],
  "ssm": {
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "api_gateway": {
    "name": "agw-primary",
    "api_type": "REST",
    "description": "Primary API Gateway",
    "deploy_options": {
      "stage_name": "api",
      "logging_level": "INFO",
      "data_trace_enabled": false,
      "tracing_enabled": true,
      "metrics_enabled": true
    },
    "custom_domain": {
      "domain_name": "{{API_DNS_RECORD}}",
      "hosted_zone_id": "{{HOSTED_ZONE_ID}}",
      "hosted_zone_name": "{{HOSTED_ZONE_NAME}}",
      "certificate_arn": "{{SSL_CERT_ARN}}"
    },
    "cognito": {
      "user_pool_ssm_path": "/my-workload/dev/cognito/primary/user-pool-id"
    },
    "routes": [
      {
        "path": "/app/configuration",
        "method": "GET",
        "lambda_name": "app-configurations",
        "skip_authorizer": true
      },
      {
        "path": "/v3/validations/trigger",
        "method": "POST",
        "lambda_name": "validation-trigger"
      },
      {
        "path": "/external/callback",
        "method": "POST",
        "lambda_arn_ssm_path": "/my-workload/dev/lambda/callback-handler/arn"
      }
    ],
    "cors": {
      "allow_origins": ["*"],
      "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      "allow_headers": ["Content-Type", "Authorization"]
    }
  }
}
```

> SSM imports are now at the top-level `ssm` block, not inside `api_gateway.ssm`.

| Field | Type | Description |
|-------|------|-------------|
| `api_type` | string | `REST` or `HTTP` |
| `cognito.user_pool_ssm_path` | string | SSM path to Cognito user pool ID for authorizer |
| `routes[].lambda_name` | string | Lambda name (resolved via `ssm.imports.namespace`) |
| `routes[].lambda_arn_ssm_path` | string | Direct SSM path to Lambda ARN (alternative to `lambda_name`) |
| `routes[].skip_authorizer` | bool | Skip Cognito auth for this route |

---

## `sqs_stack`

SQS queues with DLQ, CloudWatch alarms, and auto-discovery from Lambda configs.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-sqs-consumer-queues",
  "description": "SQS queues for workflow consumers",
  "module": "sqs_stack",
  "enabled": true,
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "lambda_config_paths": [
    "./configs/stacks/lambda-workflow-sqs-handler.json",
    "./configs/stacks/lambda-validations.json"
  ],
  "sqs": {
    "queues": [
      {
        "name": "my-queue",
        "visibility_timeout": 300,
        "dlq": {
          "max_receive_count": 3
        },
        "alarms": {
          "queue_depth_threshold": 100
        }
      }
    ]
  }
}
```

Auto-exports (when `auto_export: true`): `arn`, `url`

| Field | Type | Description |
|-------|------|-------------|
| `lambda_config_paths` | array | Paths to Lambda stack configs — SQS auto-discovers consumer queues from these |
| `sqs.queues` | array | Explicit queue definitions (can be empty if using auto-discovery) |

### `lambda_config_paths` — Auto-Discovery

When `lambda_config_paths` is set, consumer queues are resolved at config load time (during `CdkConfig` resolution), not at CDK runtime. The resolver:

1. Scans all lambda stacks in the deployment for `sqs.queues` entries with `type: "consumer"`
2. Extracts the queue definitions (name, visibility timeout, etc.)
3. Appends them to the SQS stack's `sqs.queues` array (skipping duplicates)

By the time any stack's `build()` method runs, the queues are already plain resolved data in the config.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-sqs-consumer-queues",
  "module": "sqs_stack",
  "lambda_config_paths": [
    "./configs/stacks/lambdas/lambda-workflow-sqs-handler.json",
    "./configs/stacks/lambdas/lambda-workflow-app.json",
    "./configs/stacks/lambdas/lambda-validations.json"
  ],
  "sqs": {
    "queues": []
  }
}
```

The `sqs.queues` array starts empty and is populated during config resolution. The post-build snapshot at `.dynamic/config.json` reflects the fully merged state.

---

## `cognito_stack`

Cognito user pool — create new or import existing.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-cognito-primary",
  "description": "Primary Cognito user pool",
  "module": "cognito_stack",
  "enabled": true,
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "cognito": {
    "user_pool_id": "{{COGNITO_PRIMARY_USER_POOL_ID}}",
    "use_existing": true,
    "custom_attributes": [
      { "name": "tenant_id", "type": "String" },
      { "name": "role", "type": "String" }
    ]
  }
}
```

Auto-exports (when `auto_export: true`): `user-pool-id`

| Field | Type | Description |
|-------|------|-------------|
| `user_pool_id` | string? | Existing user pool ID (when `use_existing: true`) |
| `use_existing` | bool | Import existing pool vs create new |
| `custom_attributes` | array? | Custom user attributes |

---

## `route53_stack`

Route53 hosted zone and DNS records.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-route53",
  "description": "Route53 hosted zone",
  "module": "route53_stack",
  "enabled": true,
  "ssm": {
    "auto_export": true,
    "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
  },
  "route53": {
    "hosted_zone_id": "{{HOSTED_ZONE_ID}}",
    "hosted_zone_name": "{{HOSTED_ZONE_NAME}}",
    "use_existing": true
  }
}
```

Auto-exports (when `auto_export: true`): `hosted-zone-id`

| Field | Type | Description |
|-------|------|-------------|
| `hosted_zone_id` | string | Zone ID (for import) |
| `hosted_zone_name` | string | Zone domain name |
| `use_existing` | bool | Import existing zone vs create new |

---

## `ecr_stack`

ECR repositories.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-ecr-repos",
  "module": "ecr_stack",
  "enabled": true,
  "resources": [
    {
      "name": "my-org/my-service",
      "use_existing": true,
      "auto_delete_untagged_images": true
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Repository name |
| `use_existing` | bool | Import existing repo |
| `auto_delete_untagged_images` | bool | Lifecycle policy to clean untagged images |

Also registered as `ecr_library_module`.

---

## `step_function_stack`

Step Functions state machine.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-my-workflow",
  "module": "step_function_stack",
  "enabled": true,
  "step_function": {
    "name": "my-state-machine",
    "definition_file": "./state-machines/workflow.asl.json"
  }
}
```

The definition file supports `{{LAMBDA_ARN:function-name}}` placeholders that resolve Lambda ARNs from SSM at synth time.

---

## `monitoring_stack`

CloudWatch dashboard with SNS topics and log metric filters.

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-cloudwatch-dashboard",
  "description": "CloudWatch monitoring dashboard",
  "module": "monitoring_stack",
  "enabled": true,
  "depends_on": ["lambda-primary"],
  "ssm": {
    "imports": {
      "namespace": "my-workload/{{DEPLOYMENT_NAMESPACE}}"
    }
  },
  "monitoring": {
    "dashboard_name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-dashboard"
  }
}
```

> SSM imports are now at the top-level `ssm` block, not inside `monitoring.ssm`.

The monitoring stack reads Lambda ARNs from SSM (via namespace imports) to build dashboard widgets automatically.
