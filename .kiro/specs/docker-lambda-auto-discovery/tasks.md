# Implementation Plan: Docker Lambda Auto-Discovery

## Overview

Replace fragmented Docker Lambda image update tooling with a unified auto-discovery framework in cdk-factory. Implementation proceeds in three phases: (1) CDK stack manifest export and ECR metadata, (2) Unified CLI utility with all operating modes, (3) pipeline integration and migration documentation. All code is Python, tests use pytest + hypothesis.

## Tasks

- [ ] 1. Add `raw_ecr_name` property and discovery manifest export to LambdaStack
  - [ ] 1.1 Add `raw_ecr_name` property to `LambdaFunctionConfig`
    - Add a `raw_ecr_name` property to `cdk-factory/src/cdk_factory/configurations/resources/lambda_function.py` that returns `self.__config.get("ecr", {}).get("name", "")` — the raw ECR repo name without `build_resource_name()` transformation
    - _Requirements: 2.4_

  - [ ] 1.2 Export `ecr-repo` SSM parameter per Docker Lambda
    - In `lambda_stack.py` `__export_lambda_arns_to_ssm()`, after the existing Docker Lambda SSM exports, add an `ecr-repo` SSM StringParameter at `/{namespace}/{lambda-name}/ecr-repo` using `function_config.raw_ecr_name` as the value, STANDARD tier
    - Skip creation when `raw_ecr_name` is empty
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 1.3 Export discovery manifest SSM parameter
    - Add `__export_discovery_manifest_to_ssm()` method to `LambdaStack`
    - Build a dict mapping each distinct `raw_ecr_name` to a list of `/{namespace}/{lambda-name}` path prefixes for Docker Lambdas only
    - Write as JSON to `/{namespace}/docker-lambdas/manifest` SSM StringParameter, STANDARD tier
    - Skip manifest creation when no Docker Lambdas exist or `ssm.auto_export` is disabled
    - Call this method at the end of `__export_lambda_arns_to_ssm()`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4_

  - [ ] 1.4 Validate `ssm.namespace` when `ssm.auto_export` is true
    - Ensure existing `ValueError` is raised when `ssm.namespace` is missing — verify this is already handled in `__export_lambda_arns_to_ssm()`
    - _Requirements: 1.6_

  - [ ]* 1.5 Write property test: Manifest builder completeness and correctness (Property 1)
    - **Property 1: Manifest builder completeness and correctness**
    - Generate random lambda config sets with varying Docker/non-Docker mix and ECR repo names
    - Verify: (a) every Docker lambda with valid `ecr.name` appears exactly once under its ECR repo key, (b) no non-Docker lambda appears, (c) each distinct ECR repo has exactly one key, (d) manifest is empty when no Docker lambdas exist
    - Use hypothesis with min 100 iterations
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 7.1, 7.2**

  - [ ]* 1.6 Write property test: ECR repo metadata round-trip (Property 2)
    - **Property 2: ECR repo metadata round-trip**
    - Generate random ECR repo name strings, pass through the ecr-repo export logic, verify output equals input without transformation
    - **Validates: Requirements 2.1, 2.4**

  - [ ]* 1.7 Write unit tests for LambdaStack manifest and ECR repo exports
    - CDK synth test: verify CloudFormation template contains manifest and ecr-repo SSM parameters
    - Test empty stack (no Docker lambdas) produces no manifest
    - Test mixed Docker/non-Docker lambdas
    - Test multiple Docker lambdas sharing same ECR repo are grouped
    - Test multiple distinct ECR repos produce separate keys
    - _Requirements: 1.1–1.6, 2.1–2.4, 7.1–7.4_

- [ ] 2. Checkpoint — Ensure all LambdaStack tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement Unified CLI core: config parsing, discovery, and update logic
  - [ ] 3.1 Create `docker_lambda_updater.py` module with `DockerLambdaUpdater` class
    - Create `cdk-factory/src/cdk_factory/utilities/docker_lambda_updater.py`
    - Implement `DockerLambdaUpdater.__init__()` accepting: `config_path`, `ssm_namespace`, `account`, `region`, `dry_run`, `refresh`, `image_name`, `locked_versions_path`, `cross_account_role`
    - Implement cross-account session management (STS assume role, session cache keyed by account ID, per-deployment `role_name` override)
    - Implement `_get_ssm_client()`, `_get_lambda_client()`, `_get_ecr_client()` with cross-account support
    - _Requirements: 10.1, 10.2, 11.4_

  - [ ] 3.2 Implement config loading and deployment entry validation
    - Implement `_load_config()` to read `docker-images.json` and validate `images` array exists
    - Implement `_validate_deployment_entry()` to check each entry has `ssm_parameter`, `ssm_namespace`, or `ssm_namespaces`; report validation error with image name and deployment index if neither present
    - Handle `ssm_namespace` (singular) by treating as single-element list
    - When both `ssm_parameter` and `ssm_namespace` are present, use `ssm_namespace` and log info that `ssm_parameter` is ignored
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.3_

  - [ ] 3.3 Implement manifest-based discovery logic
    - Implement `_discover_from_manifest(ssm_client, namespace, repo_name)` — reads `/{namespace}/docker-lambdas/manifest`, parses JSON, returns list of path prefixes for the given repo name
    - Log descriptive error if manifest SSM parameter not found (include path, account, region)
    - Log warning and return empty list if repo name not in manifest
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 3.4 Implement multi-namespace aggregation
    - Implement `_discover_from_namespaces(ssm_client, namespaces, repo_name)` — queries manifest in each namespace, aggregates all path prefixes, deduplicates
    - Log warning per namespace that fails, continue with remaining
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 3.5 Implement legacy `ssm_parameter` direct resolution
    - Implement `_resolve_ssm_parameter(ssm_client, parameter_path)` — reads SSM parameter value directly
    - Preserve backward compatibility with existing `docker-images.json` format
    - _Requirements: 3.6_

  - [ ] 3.6 Implement locked version tag resolution
    - Implement `_load_locked_versions(path)` to read `.docker-locked-versions.json`
    - Implement `_resolve_tag(lambda_name, deployment_tag, locked_versions)` returning `(resolved_tag, source)` where source is `"locked"`, `"deployment"`, or `"skipped"`
    - Matching entry with non-empty tag → use locked tag; empty tag → skip lambda; no match → use deployment tag
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 3.7 Write property test: Manifest-based discovery correctness (Property 3)
    - **Property 3: Manifest-based discovery correctness**
    - Generate random manifest dicts and repo name queries, verify lookup returns exact match or empty list
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 3.8 Write property test: Deployment entry validation (Property 4)
    - **Property 4: Deployment entry validation**
    - Generate deployment entry dicts missing both `ssm_parameter` and `ssm_namespace`/`ssm_namespaces`, verify validation error is reported
    - **Validates: Requirements 4.4**

  - [ ]* 3.9 Write property test: Multi-namespace aggregation (Property 5)
    - **Property 5: Multi-namespace aggregation**
    - Generate lists of namespace→manifest mappings, verify aggregated result equals union of path prefixes with no duplicates
    - **Validates: Requirements 5.2**

  - [ ]* 3.10 Write property test: Tag resolution correctness (Property 7)
    - **Property 7: Tag resolution correctness**
    - Generate random (lambda_name, deployment_tag, locked_versions_list) tuples, verify: matching entry with non-empty tag → locked tag; no match → deployment tag; matching entry with empty tag → skipped
    - **Validates: Requirements 8.2, 8.3, 8.5**

- [ ] 4. Implement Unified CLI operating modes: update, refresh, dry-run
  - [ ] 4.1 Implement config-driven update mode
    - Implement `_run_config_mode()` — iterate `images` array, for each image iterate `lambda_deployments`, per deployment: discover via manifest or resolve via `ssm_parameter`, resolve tags (with optional locked versions), call `update_function_code` with new image URI
    - Include retry with exponential backoff for ECR propagation `AccessDeniedException` (3 retries, 2s base)
    - Support per-deployment `ecr_account` (defaults to caller account)
    - _Requirements: 3.3, 10.5, 11.1, 11.2, 11.3_

  - [ ] 4.2 Implement direct namespace mode
    - Implement `_run_namespace_mode()` — discover all Docker Lambdas under namespace via `get_parameters_by_path` (recursive, filter `/arn` suffixes)
    - When `--refresh` not set, require `--image-name` to build new image URI
    - _Requirements: 10.4_

  - [ ] 4.3 Implement refresh mode
    - Implement `_refresh_lambda(lambda_client, function_arn)` — call `get_function` to get current image URI, then `update_function_code` with same URI
    - When `--locked-versions` also provided, build image URI from locked tag instead of reading current
    - Tag each updated Lambda with `LastImageRefresh` timestamp and `RefreshedBy=deployment-pipeline`
    - Log error and continue if current image URI cannot be retrieved
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ] 4.4 Implement dry-run mode
    - When `dry_run=True`: perform SSM reads and discovery, display each discovered Lambda path prefix, resolved ARN, new image URI, tag source, and count per namespace — but never call `update_function_code`
    - _Requirements: 6.1, 6.2, 6.3, 8.7_

  - [ ] 4.5 Implement deployment failure resilience
    - Wrap each deployment entry processing in try/except — log error for failed entries (account unreachable, role assumption fails, SSM errors) and continue with remaining entries
    - _Requirements: 11.5_

  - [ ]* 4.6 Write property test: Dry-run safety (Property 6)
    - **Property 6: Dry-run safety**
    - Generate random configs, run in dry-run mode with mocked clients, verify `update_function_code` call count is zero
    - **Validates: Requirements 6.3**

  - [ ]* 4.7 Write property test: Refresh mode image round-trip (Property 8)
    - **Property 8: Refresh mode image round-trip**
    - Generate random image URIs, mock `get_function` to return them, verify `update_function_code` receives the same URI
    - **Validates: Requirements 9.3**

  - [ ]* 4.8 Write property test: Deployment failure resilience (Property 9)
    - **Property 9: Deployment failure resilience**
    - Generate deployment entry lists with random failure injection, verify all entries are attempted (count of attempted == total count)
    - **Validates: Requirements 11.5**

- [ ] 5. Checkpoint — Ensure all Unified CLI core tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement CLI entry point, environment variable support, and summary output
  - [ ] 6.1 Implement CLI argument parser and `main()` entry point
    - Add `argparse`-based CLI with arguments: `--config`, `--ssm-namespace`, `--account`, `--region`, `--refresh`, `--locked-versions`, `--dry-run`, `--image-name`, `--cross-account-role`
    - Add `__main__.py` or `if __name__ == "__main__"` block for `python -m cdk_factory.utilities.docker_lambda_updater` execution
    - Validate at least one of `--config` or `--ssm-namespace` (or env vars) is provided; exit with code 1 and usage error if neither
    - _Requirements: 10.2, 10.3, 10.6_

  - [ ] 6.2 Implement environment variable fallback
    - Accept `SSM_DOCKER_LAMBDAS_PATH`, `AWS_ACCOUNT_NUMBER`, `AWS_REGION`, `CROSS_ACCOUNT_ROLE_ARN` as fallbacks
    - When env vars set and no CLI args → operate in direct namespace Refresh_Mode
    - CLI arguments take precedence over env vars
    - _Requirements: 12.1, 12.2, 12.3_

  - [ ] 6.3 Implement `run()` method with summary output and exit codes
    - Write summary to stdout: count of Docker Lambdas discovered, updated successfully, and failed
    - Exit 0 on success, non-zero on failure
    - _Requirements: 12.4, 12.5_

  - [ ]* 6.4 Write property test: CLI argument precedence over environment variables (Property 10)
    - **Property 10: CLI argument precedence over environment variables**
    - Generate random (cli_value, env_value) pairs, verify CLI value wins when both are set
    - **Validates: Requirements 12.3**

  - [ ]* 6.5 Write unit tests for CLI entry point and environment variable handling
    - Test `--config` mode, `--ssm-namespace` mode, env var fallback, precedence rules
    - Test exit code 0 on success, non-zero on failure
    - Test usage error when neither `--config` nor `--ssm-namespace` provided
    - _Requirements: 10.2–10.6, 12.1–12.5_

- [ ] 7. Checkpoint — Ensure all CLI tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Create migration documentation
  - [ ] 8.1 Write migration guide document
    - Create `cdk-factory/docs/migration-docker-lambda-auto-discovery.md`
    - Describe steps to replace `LambdaImageUpdater` in Acme-SaaS-DevOps-CDK with the Unified CLI
    - Describe how to wire the Unified CLI into acme-SaaS-IaC CDK pipeline as a post-deployment shell step, replacing the legacy `lambda_boto3_utilities.py` pattern
    - Describe how to update `docker-images.json` from `ssm_parameter` to `ssm_namespace` format
    - Describe how to configure locked version tags with `--locked-versions`
    - Describe the pattern clearly enough for prompt-based find/replace in other workspaces
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [ ] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–10)
- Unit tests validate specific examples and edge cases
- All code is Python; tests use pytest + hypothesis
- The Unified CLI lives in `cdk_factory.utilities.docker_lambda_updater` and is executable via `python -m cdk_factory.utilities.docker_lambda_updater`
- Pipeline integration in acme-SaaS-IaC is documented in the migration guide (task 8) — actual pipeline config changes are done by consuming projects following the guide
