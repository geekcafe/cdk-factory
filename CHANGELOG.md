# Changelog

All notable changes to cdk-factory are documented here.

## [1.11.0] — 2026-09-09

> ⚠️ **Upgrade impact:** This release makes SSM-import CloudFormation logical IDs
> deterministic. Upgrading from any earlier 1.10.x will produce a **one-time**
> CloudFormation diff on stacks that import SSM parameters. Most changes are
> cosmetic (a parameter's logical ID is renamed, resolved value unchanged), but
> where an SSM-imported value feeds a **replacement-sensitive** property the
> update can cascade into a resource replacement. **Run `cdk diff` before
> deploying** and see `MIGRATION.md` → "Deterministic SSM logical IDs (1.11.0)".

### Added
- **RDS `secret_logical_id_override`** (`rds` config): pins the generated
  credentials secret's (`AWS::SecretsManager::Secret`) CloudFormation logical ID
  to an explicit value. Use it to preserve an already-deployed credentials secret
  when a construct-path change (naming refactor, or moving a stack in/out of a
  pipeline Stage) would otherwise change the auto-generated logical ID and force
  CloudFormation to REPLACE the secret (destroy + recreate with a new password).
  Unset for new stacks. See `MIGRATION.md`.
- **CloudFront `response_headers_policy`** support in `CloudFrontDistributionConstruct`
  (the `cdn_stack` / `website_library_module` path) — matches the existing support
  in `cloudfront_library_module`. Accepts a managed policy name
  (`CORS-With-Preflight`, `CORS-And-SecurityHeaders`, `SecurityHeaders`) or a
  custom `cors` block. Attached to the default behavior; enables CDN-only S3
  distributions to serve cross-origin assets (fonts, etc.) with CORS.
- **CloudFront cross-stack OAC grant** in `CloudFrontDistributionConstruct`:
  `grant_read` block (`distribution_arns` + `fallback_to_account`) and legacy
  `grant_read_to_account` / `grant_read_to_distribution_arns`. Lets the S3 bucket
  owner stack grant OAC `s3:GetObject` to distributions defined in OTHER stacks
  (which import the bucket and therefore cannot author its policy). Account-scoped
  grant is greenfield-safe (no cross-stack ordering dependency).

### Changed
- **Deterministic SSM import logical IDs (upgrade-impacting).** All construct IDs
  for imported SSM parameters previously used Python's builtin `hash(path)`, which
  is randomized per process via `PYTHONHASHSEED`. That produced a DIFFERENT
  CloudFormation logical ID for the same SSM parameter on every `cdk synth`,
  causing resources that reference those parameters (e.g. an ECS service's
  `CapacityProviderStrategy` / `LoadBalancers`) to appear changed on every deploy —
  triggering spurious updates and, in the ECS case, a cascade that recreated the
  service's Application Auto Scaling target-tracking policies and failed with
  "Only one TargetTrackingScaling policy for a given metric specification is
  allowed." Replaced with a stable content hash
  (`int(hashlib.sha1(path.encode()).hexdigest(), 16) % 10000`) across:
  `interfaces/standardized_ssm_mixin.py` (`resolve_ssm_value`),
  `stack_library/ecs/ecs_service_stack.py`,
  `stack_library/cloudfront/cloudfront_stack.py`,
  `stack_library/security_group/security_group_full_stack.py`,
  `constructs/cloudfront/cloudfront_distribution_construct.py`,
  `stack_library/route53/route53_stack.py`,
  `stack_library/api_gateway/api_gateway_stack.py`,
  `stack_library/api_gateway/api_gateway_route_group_nested_stack.py`,
  `utilities/api_gateway_integration_utility.py`.

### Removed
- None

### Fixed
- **RDS credentials secret no longer silently at risk of replacement** on
  construct-path changes when `secret_logical_id_override` is set (see Added).

## [1.0.5] — 2026-04-21

### Added


- Structured `parameter_store` permission: `{"parameter_store": "read", "path": "/my-app/dev/cognito/*"}` — scoped SSM read with wildcard paths instead of blanket `"parameter_store_read"`.
- Warning message when `__inherits__` path falls through to dot-path resolution.

### Changed
- None
### Removed
- None
### Fixed
- None



## [1.0.4] — 2026-04-20

### Added

- `additional_permissions` and `additional_environment_variables` at the Lambda stack level — merged into every resource before CDK constructs are created. Resource-level entries take precedence.
- `skip_stack_defaults` flag on individual Lambda resources — opt out of stack-level merging.
- `merge_defaults.py` utility module — pure functions for permission/env var merging with `permission_key()` deduplication.
- `CdkConfig.save_config_snapshot()` — re-saves `.dynamic/config.json` after all stacks build, reflecting post-merge state.
- `CdkConfig._resolve_lambda_config_paths()` — resolves SQS consumer queue discovery at config load time from the already-resolved in-memory config. Replaces the old file-based runtime discovery.
- Better error messages in `JsonLoadingUtility.get_nested_config()` — descriptive errors for invalid `__inherits__` paths instead of cryptic `KeyError: ''`.

### Changed

- `auto_name` default changed from `false` to `true` — CDK generates Lambda function names from the construct path by default. Set `"auto_name": false` for explicit naming.
- SQS consumer queue discovery moved from `SQSStack._discover_consumer_queues_from_lambda_configs()` (runtime file loading) to `CdkConfig._resolve_lambda_config_paths()` (config load time). Queues are now plain resolved data by the time `build()` runs.
- `WorkloadFactory.__generate_deployments()` calls `save_config_snapshot()` after all deployments complete.

### Removed

- `SQSStack._discover_consumer_queues_from_lambda_configs()` — replaced by config-time resolution in `CdkConfig`.

## [1.0.0] — 2026-04-19

First stable release. All breaking changes from the beta period are consolidated here.

### Breaking Changes

- **Declarative stack naming** — Removed `naming` block (`prefix`, `stack_pattern`, `build_stack_name()`). The `name` field in stack configs is now the literal CloudFormation stack name. Use `{{PLACEHOLDER}}` tokens for dynamic prefixes.
- **SSM config at top level only** — Nested SSM blocks (`dynamodb.ssm`, `bucket.ssm`, etc.) are rejected. SSM must be a top-level peer of `name` and `module`.
- **`ssm.enabled` removed** — Use `ssm.auto_export: true` instead.
- **`bucket.exists` removed** — Use `bucket.use_existing` instead.
- **`dependencies` key removed** — Use `depends_on` only.
- **`stack_name` key removed** — Use `name` for the actual stack name, `description` for labels.
- **`naming` block in deployment configs rejected** — Raises `ValueError` with migration guidance.
- **Unresolved placeholders are errors** — Any `{{...}}` tokens remaining after resolution raise a descriptive error.

### Added

- `ConfigValidator` class — validates all stack configs before CDK constructs are created
- JSON Schema validation — 10 schema files validate config structure, types, and required fields
- `SchemaRegistry` — loads and caches `.schema.json` files from `src/cdk_factory/schemas/`
- `SchemaValidator` — placeholder-aware validation using `jsonschema.Draft7Validator`
- Resource name validation — S3 (3-63 chars), DynamoDB (3-255 chars), Lambda (1-64 chars)
- `StackConfig.ssm_config`, `ssm_namespace`, `ssm_auto_export` properties
- `StackConfig.description` property
- `CdkDeploymentCommand.run_cdk_destroy()` — `destroy` operation for CLI
- `CdkDeploymentCommand` auto-discovery — built-in `deployment.*.json` scanning and `{{PLACEHOLDER}}` resolution
- `MIGRATION.md` — comprehensive migration guide with before/after examples
- Standardized SSM export path: `/{namespace}/{resource_type}/{stack_name}/{attribute}`
- Lambda SSM export path: `/{namespace}/lambda/{lambda_name}/arn`

### Removed

- `DeploymentConfig.naming_prefix` property
- `DeploymentConfig.stack_pattern` property
- `DeploymentConfig.build_stack_name()` method
- `S3BucketConfig.exists` property
- `validation/config_validator.py` (old broken validator)
- `TestNamingPatternDeterminism` test class

### Changed

- All stack modules read SSM from `stack_config.ssm_config` (top-level) instead of resource-nested blocks
- `StackConfig.dependencies` reads from `depends_on` key (was `dependencies`)
- Lambda SSM exports use `/{namespace}/lambda/{lambda_name}/arn` (no stack_name segment)
- `PipelineFactory.__setup_stacks()` uses `stack_config.name` directly as `stack_name` kwarg

## [0.200.2] — 2026-04-18

Last beta release before v1.0 standardization.

## [0.200.1] and earlier

Beta releases. See git history for details.
