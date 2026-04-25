# SSM Auto-Export Audit

Pattern: `/{namespace}/{attribute}` — namespace is fully controlled by config, stack appends only the attribute name.

## Stack Status

| Stack | Export Method | Pattern | Status |
|-------|-------------|---------|--------|
| cognito_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| bucket_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| dynamodb_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| route53_stack | `ssm.StringParameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| lambda_stack | `ssm.StringParameter()` direct | `/{namespace}/{name}/{attr}` | ✅ Fixed |
| api_gateway_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| auto_scaling_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| vpc_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| ecs_cluster_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| ecs_capacity_provider_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| rum_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| step_function_stack | `export_ssm_parameter()` direct | `/{namespace}/{attr}` | ✅ Fixed |
| sqs_stack | `ssm.StringParameter()` direct | `/{namespace}/{name}/{attr}` | ✅ Fixed |
| monitoring_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| cloudfront_stack | `ssm.StringParameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| rds_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| acm_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| static_website_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| load_balancer_stack | `export_resource_to_ssm()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| security_group_stack | `export_resource_to_ssm()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| security_group_full_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| ecs_service_stack | `export_ssm_parameter()` with explicit exports | Explicit only, no auto_export | ✅ OK (explicit) |
| ecr_stack | No SSM exports | N/A | ✅ OK (none) |
| code_artifact_stack | No SSM exports | N/A | ✅ OK (none) |
| lambda_edge_stack | No SSM exports | N/A | ✅ OK (none) |

## Stacks Fixed

All stacks now support `auto_export: true` with `/{namespace}/{attribute}` pattern. When `auto_export` is enabled with a `namespace`, each stack uses `export_ssm_parameter()` (singular) to create parameters directly under the namespace. When `auto_export` is off, stacks fall back to the mixin's `export_ssm_parameters()` for explicit `exports` config entries.
