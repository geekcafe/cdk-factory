# SSM Parameter Naming Convention

## Overview

All cdk-factory stacks export resource metadata to AWS SSM Parameter Store using a consistent `/{namespace}/{attribute}` pattern. The namespace is fully controlled by the stack's JSON config — the stack code never injects resource types or stack names into the path.

## Core Pattern

```
/{namespace}/{attribute}
```

- **namespace** — Configured in the stack's `ssm.namespace` field. Includes the workload, environment, resource type, and any additional context needed for uniqueness.
- **attribute** — The specific resource property being exported (e.g., `table_name`, `user_pool_id`, `arn`).

## Namespace Structure

The recommended namespace format is:

```
{workload}/{deployment}/{resource-type}/{resource-context}
```

Example namespaces:

| Stack Type | Namespace Example | Resulting SSM Path |
|-----------|-------------------|-------------------|
| Cognito | `aplos-nca-saas/beta/cognito` | `/aplos-nca-saas/beta/cognito/user_pool_id` |
| DynamoDB | `aplos-nca-saas/beta/dynamodb/app` | `/aplos-nca-saas/beta/dynamodb/app/table_name` |
| S3 Bucket | `aplos-nca-saas/beta/s3/uploads` | `/aplos-nca-saas/beta/s3/uploads/bucket_name` |
| Route53 | `aplos-nca-saas/beta/route53` | `/aplos-nca-saas/beta/route53/hosted-zone-id` |
| Lambda | `aplos-nca-saas/beta/lambda/subscriptions` | `/aplos-nca-saas/beta/lambda/subscriptions/{lambda-name}/arn` |
| SQS | `aplos-nca-saas/beta/sqs` | `/aplos-nca-saas/beta/sqs/{queue-name}/arn` |
| API Gateway | `aplos-nca-saas/beta/api-gateway` | `/aplos-nca-saas/beta/api-gateway/api_id` |
| VPC | `aplos-nca-saas/beta/vpc` | `/aplos-nca-saas/beta/vpc/vpc_id` |

## Stack Config

Enable SSM auto-export in any stack's JSON config:

```json
{
  "ssm": {
    "auto_export": true,
    "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}/cognito"
  }
}
```

- `auto_export: true` — Enables automatic SSM parameter creation for the stack's resources.
- `namespace` — The full prefix path. Supports placeholder variables like `{{DEPLOYMENT_NAMESPACE}}`.

When `auto_export` is true, `namespace` is required. The stack will raise a `ValueError` if it's missing.

## What Each Stack Exports

### Cognito (`cognito_stack`)
| Attribute | Description |
|-----------|-------------|
| `user_pool_id` | Cognito User Pool ID |
| `user_pool_name` | User Pool name |
| `user_pool_arn` | User Pool ARN |
| `app_client_{name}_id` | App client ID (per client, name sanitized) |
| `app_client_{name}_secret_arn` | Secrets Manager ARN for client secret |

### DynamoDB (`dynamodb_stack`)
| Attribute | Description |
|-----------|-------------|
| `table_name` | DynamoDB table name |
| `table_arn` | Table ARN |
| `table_stream_arn` | Stream ARN (if streams enabled) |
| `gsi_names` | Comma-separated GSI names (if any) |

### S3 Bucket (`bucket_stack`)
| Attribute | Description |
|-----------|-------------|
| `bucket_name` | S3 bucket name |
| `bucket_arn` | Bucket ARN |

### Route53 (`route53_stack`)
| Attribute | Description |
|-----------|-------------|
| `hosted-zone-id` | Hosted zone ID |

### Lambda (`lambda_stack`)

Lambda stacks export per-function parameters under `/{namespace}/{lambda-name}/`:

| Attribute | Description |
|-----------|-------------|
| `{lambda-name}/arn` | Lambda function ARN |
| `{lambda-name}/function-name` | Lambda function name |
| `{lambda-name}/api-route` | API route metadata (JSON, if API configured) |
| `{lambda-name}/ecr-repo` | ECR repo name (Docker lambdas only) |
| `docker-lambdas/manifest` | JSON manifest mapping ECR repos to Docker Lambda paths |

Each lambda stack should have its own unique namespace to avoid collisions (e.g., `lambda/subscriptions`, `lambda/tenants`, `lambda/workflow-sqs-handler`).

### SQS (`sqs_stack`)

SQS exports per-queue parameters under `/{namespace}/{queue-name}/`:

| Attribute | Description |
|-----------|-------------|
| `{queue-name}/arn` | Queue ARN |
| `{queue-name}/url` | Queue URL |
| `{queue-name}-dlq/arn` | DLQ ARN |
| `{queue-name}-dlq/url` | DLQ URL |

### API Gateway (`api_gateway_stack`)
| Attribute | Description |
|-----------|-------------|
| `api_id` | REST API ID |
| `api_arn` | API execution ARN |
| `root_resource_id` | Root resource ID |
| `api_url` | Constructed API URL |
| `authorizer_id` | Cognito authorizer ID (if configured) |

### VPC (`vpc_stack`)
| Attribute | Description |
|-----------|-------------|
| `vpc_id` | VPC ID |
| `public_subnet_ids` | Comma-separated public subnet IDs |
| `private_subnet_ids` | Comma-separated private subnet IDs |
| `isolated_subnet_ids` | Comma-separated isolated subnet IDs |
| `nat_gateway_ids` | Comma-separated NAT gateway IDs |
| `internet_gateway_id` | Internet gateway ID |

### ECS Cluster (`ecs_cluster_stack`)
| Attribute | Description |
|-----------|-------------|
| `cluster_name` | ECS cluster name |
| `cluster_arn` | Cluster ARN |
| `instance_role_arn` | Instance role ARN |
| `security_group_id` | Cluster security group ID |
| `instance_profile_arn` | Instance profile ARN |

### Auto Scaling (`auto_scaling_stack`)
| Attribute | Description |
|-----------|-------------|
| `auto_scaling_group_name` | ASG name |

### RUM (`rum_stack`)
| Attribute | Description |
|-----------|-------------|
| `app_monitor_name` | RUM app monitor name |
| `app_monitor_id` | App monitor ID |
| `identity_pool_id` | Cognito identity pool ID |
| `user_pool_id` | Cognito user pool ID |

### Step Functions (`step_function_stack`)
| Attribute | Description |
|-----------|-------------|
| `state_machine_arn` | State machine ARN |
| `state_machine_name` | State machine name |

## Docker Lambda ECR Registration

When a Lambda stack deploys Docker Lambdas with `ssm.auto_export: true`, each Docker Lambda registers itself at a well-known ECR-keyed path:

```
/{workload}/{deployment}/ecr/{safe-repo-name}/{lambda-name}/arn
/{workload}/{deployment}/ecr/{safe-repo-name}/{lambda-name}/function-name
```

Where `safe-repo-name` is the ECR repo name with `/` replaced by `-` (e.g., `aplos-analytics-v3-aplos-saas-core-services`).

The `{workload}/{deployment}` prefix is derived from the lambda stack's `ssm.namespace` by stripping the `/lambda/...` suffix.

Example SSM tree:

```
/aplos-nca-saas/beta/ecr/
├── aplos-analytics-v3-aplos-saas-core-services/
│   ├── subscription-create/
│   │   ├── arn
│   │   └── function-name
│   ├── tenant-get/
│   │   ├── arn
│   │   └── function-name
│   └── user-create/
│       ├── arn
│       └── function-name
├── aplos-analytics-v3-aplos-nca-orchestration-services/
│   ├── workflow-step-processor/
│   │   ├── arn
│   │   └── function-name
│   └── analysis-send-to-queue/
│       ├── arn
│       └── function-name
```

### Discovery

To find all Docker Lambdas for a given ECR repo, the `docker_lambda_updater` CLI does a single `get_parameters_by_path` call:

```
Path: /{ssm_prefix}/ecr/{safe-repo-name}/
Recursive: true
Filter: params ending with /arn
```

### docker-images.json

The config only needs the workload/deployment prefix — the CLI constructs the ECR path from the `repo_name`:

```json
{
  "images": [
    {
      "repo_name": "aplos-analytics/v3/aplos-saas-core-services",
      "lambda_deployments": [
        {
          "account": "959096737760",
          "region": "us-east-1",
          "ssm_prefix": "aplos-nca-saas/dev",
          "tag": "dev"
        }
      ]
    }
  ]
}
```

See `docs/migration-docker-lambda-auto-discovery.md` for full usage details.

## Importing SSM Parameters

### API Gateway Lambda Import

The API gateway discovers Lambda ARNs via `ssm.imports.namespace`:

```json
{
  "ssm": {
    "imports": {
      "namespace": "aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}/lambda/subscriptions"
    }
  }
}
```

When a route references `lambda_name: "subscription-get"`, the API gateway resolves the ARN from `/{imports.namespace}/{lambda_name}/arn`.

### Direct SSM References

Any config value starting with `/` is treated as an SSM parameter path and resolved at synth time:

```json
{
  "environment_variables": [
    {
      "name": "COGNITO_USER_POOL_ID_SSM",
      "value": "/aplos-nca-saas/{{DEPLOYMENT_NAMESPACE}}/cognito/user_pool_id"
    }
  ]
}
```

## Stacks Using Explicit Exports Only

Some stacks don't use `auto_export` and instead define explicit `ssm.exports` with full paths:

- `cloudfront_stack` — `ssm.exports.distribution_id`, `ssm.exports.distribution_domain`
- `rds_stack` — `ssm.exports.db_endpoint`, `ssm.exports.db_port`, etc.
- `acm_stack` — `ssm.exports.certificate_arn`
- `static_website_stack` — `ssm.exports.bucket_name`, `ssm.exports.cloudfront_domain`
- `load_balancer_stack` — `ssm.exports.alb_dns_name`, `ssm.exports.alb_arn`, etc.
- `security_group_stack` — `ssm.exports.security_group_id`
- `ecs_service_stack` — `ssm.exports.service_name`, `ssm.exports.service_arn`, etc.
- `monitoring_stack` — `ssm.exports.sns_topic_{name}`

These stacks use the full SSM path in the config and don't need `auto_export` or `namespace`.

## Key Rules

1. **Namespace controls the full prefix** — The stack code appends only the attribute name. No resource types or stack names are injected.
2. **Each stack needs a unique namespace** — Especially lambda stacks, which export per-function sub-paths. Use suffixes like `lambda/subscriptions`, `lambda/tenants`.
3. **`auto_export: true` requires `namespace`** — The stack will error if namespace is missing.
4. **Backward compatible** — Stacks with explicit `exports` still work. `auto_export` is additive.
5. **Placeholders supported** — Use `{{DEPLOYMENT_NAMESPACE}}`, `{{WORKLOAD_NAME}}`, etc. in namespace values.
