# Changelog

All notable changes to cdk-factory are documented here.

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
