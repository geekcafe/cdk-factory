# cdk-factory — Roadmap to v1.0

Tracking the remaining work to exit beta. Items are ordered by priority.

## Completed

- [x] **Config Consistency Audit** — Standardized SSM config (top-level only), `auto_export`, `use_existing`, `depends_on`, resource name validation, unresolved placeholder detection, ConfigValidator class
- [x] **Declarative Stack Naming** — Removed `naming` block, `name` is the literal CF stack name with `{{PLACEHOLDER}}` tokens, no more implicit name transformation
- [x] **Documentation Overhaul** — Updated all 6 docs + MIGRATION.md to reflect both changes
- [x] **Destroy Operation** — Added `cdk destroy` support to `CdkDeploymentCommand`

## In Progress / Planned

### 1. JSON Schema Validation for Stack Configs
**Priority: High** — Biggest source of "why isn't this working" debugging time.
- Add JSON schema definitions for each stack module's config shape
- Validate configs at load time before CDK synth
- Catch typos, missing fields, wrong types early with clear error messages
- Reconcile the existing `cdk_factory/validation/config_validator.py` (uses jsonschema) with the new `configurations/config_validator.py`

### 2. Integration Test Fix
**Priority: High** — Integration tests are completely blocked.
- Fix the `jsonschema` import error in `tests/integration/test_auto_scaling_standardized.py`
- Either add `jsonschema` as a dependency or remove the import
- Get integration test suite running again

### 3. Stack Module Error Handling Audit
**Priority: Medium** — Some modules swallow errors or have bare `except` blocks.
- Audit all stack modules for error handling quality
- Replace bare `except` with specific exception types
- Ensure all errors surface with clear, actionable messages
- Add context (stack name, resource type) to error messages

### 4. Test Coverage for Stack Modules
**Priority: Medium** — Config layer is well-tested, stack modules less so.
- Identify stack modules with low/no test coverage
- Add unit tests for S3BucketStack, CognitoStack, Route53Stack, SQSStack build paths
- Add tests for error conditions (missing config, invalid values)

### 5. Deploy CLI as First-Class Feature
**Priority: Low** — Works but pattern is duplicated across consumers.
- Move deployment file discovery into `CdkDeploymentCommand` base class
- Make parameter resolution (multi-pass `{{PLACEHOLDER}}`) a built-in capability
- Reduce boilerplate needed in consumer `deploy.py` files

### 6. Changelog and Versioning
**Priority: Low** — Needed before 1.0 release.
- Create `CHANGELOG.md` with entries for all beta changes
- Set up proper semver tagging
- Document the release process
