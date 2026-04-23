# Implementation Plan: Config-Driven Naming

## Overview

Eliminate all hardcoded SSM path construction patterns and resource naming fallbacks across cdk-factory. Every change follows the same pattern: check for the config-driven value → use it → or raise `ValueError` with stack name, missing field, and corrective action. Two patterns (RUM stack, API GW integration Cognito auto-import) are already partially fixed — this plan completes the remaining work and adds comprehensive tests.

## Tasks

- [x] 1. Lambda Stack — remove SSM export fallbacks
  - [x] 1.1 Remove workload/environment fallback in `__export_lambda_arns_to_ssm()`
    - In `src/cdk_factory/stack_library/aws_lambdas/lambda_stack.py`, remove the `workload`/`environment` fallback branch in `__export_lambda_arns_to_ssm()`
    - When `ssm.auto_export` is true and `ssm.namespace` is missing, raise `ValueError` with stack name, missing field `ssm.namespace`, and corrective action
    - Remove the `workload = ssm_config.get("workload", ssm_config.get("organization", self.deployment.workload_name))` and `environment = ssm_config.get("environment", self.deployment.environment)` lines
    - Remove the `else: prefix = f"/{workload}/{environment}/lambda"` branch
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Remove workload/environment fallback in `__export_route_metadata_to_ssm()`
    - In the same file, apply the identical pattern to `__export_route_metadata_to_ssm()`
    - Remove the `workload`/`environment` fallback variables and the `else` branch that builds prefix from them
    - Raise `ValueError` when `ssm.namespace` is missing and `ssm.auto_export` is true
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 1.3 Write unit tests for Lambda stack SSM export error cases
    - Test that `__export_lambda_arns_to_ssm()` raises `ValueError` when `auto_export=true` and `namespace` is missing
    - Test that `__export_route_metadata_to_ssm()` raises `ValueError` when `auto_export=true` and `namespace` is missing
    - Test that both methods work correctly when `namespace` is provided
    - _Requirements: 1.1, 1.2, 2.1, 2.2_

  - [ ]* 1.4 Write property test for Lambda SSM export namespace prefix
    - **Property 1: Lambda SSM export paths use configured namespace**
    - For any valid namespace string and Lambda function names, when `auto_export` is true and `namespace` is defined, all SSM export paths start with `/{namespace}/lambda/`
    - **Validates: Requirements 1.1, 2.1**

- [x] 2. API Gateway Stack — remove Lambda discovery fallback
  - [x] 2.1 Remove workload/environment fallback in `_get_lambda_arn_from_ssm()`
    - In `src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py`, in the `lambda_name` auto-discovery branch, remove the `else` block that falls back to `workload`/`environment`
    - When `ssm.imports.namespace` is missing and a route uses `lambda_name`, raise `ValueError` with stack name, missing field `ssm.imports.namespace`, and the route's `lambda_name`
    - Remove the `workload = ssm_imports_config.get("workload", ...)` and `environment = ssm_imports_config.get("environment", ...)` lines
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 2.2 Write unit tests for API Gateway Lambda discovery error cases
    - Test that `_get_lambda_arn_from_ssm()` raises `ValueError` when `lambda_name` is set but `ssm.imports.namespace` is missing
    - Test that it constructs the correct path when `ssm.imports.namespace` is provided
    - _Requirements: 3.1, 3.2_

  - [ ]* 2.3 Write property test for API Gateway Lambda discovery path
    - **Property 2: API Gateway Lambda discovery uses imports namespace**
    - For any valid imports namespace and lambda_name, the constructed path equals `/{namespace}/lambda/{lambda_name}/arn`
    - **Validates: Requirements 3.1**

- [ ] 3. API Gateway Integration Utility — remove deployment fallback
  - [x] 3.1 Remove deployment fallback in Cognito SSM path resolution
    - In `src/cdk_factory/utilities/api_gateway_integration_utility.py`, in the `ssm_path == "auto"` branch, remove the `else` block that falls back to `deployment.workload_name`/`deployment.environment`
    - When `ssm.imports.namespace` is missing and `ssm_path` is `"auto"`, raise `ValueError` with stack name, missing field `ssm.imports.namespace`, and corrective action
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 3.2 Write unit tests for API GW Integration Utility error cases
    - Test that `ssm_path="auto"` without `ssm.imports.namespace` raises `ValueError`
    - Test that it constructs `/{namespace}/cognito/user-pool/arn` when namespace is provided
    - _Requirements: 4.1, 4.2_

  - [ ]* 3.3 Write property test for API GW Integration Cognito path
    - **Property 3: API Gateway Integration Utility Cognito path uses imports namespace**
    - For any valid imports namespace, the Cognito SSM path equals `/{namespace}/cognito/user-pool/arn`
    - **Validates: Requirements 4.1**

- [x] 4. Checkpoint — Verify stack-layer changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. CloudFront Distribution Construct — require explicit IP gate SSM path
  - [x] 5.1 Remove auto-derived SSM path in `__get_lambda_edge_associations()`
    - In `src/cdk_factory/constructs/cloudfront/cloudfront_distribution_construct.py`, remove the `default_ssm_path = f"/{environment}/{workload_name}/lambda-edge/version-arn"` auto-derivation
    - When `enable_ip_gating` is true and `ip_gate_function_ssm_path` is not provided, raise `ValueError` stating the field is required
    - Remove the `environment`/`workload_name` extraction logic that was only used for the default path
    - Keep the environment/workload_name validation only if used elsewhere in the method; otherwise remove
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 5.2 Write unit tests for CloudFront IP gate error cases
    - Test that `enable_ip_gating=true` without `ip_gate_function_ssm_path` raises `ValueError`
    - Test that an explicitly provided `ip_gate_function_ssm_path` is used as-is
    - _Requirements: 6.1, 6.2_

  - [ ]* 5.3 Write property test for CloudFront IP gate explicit path
    - **Property 4: CloudFront IP gate uses explicitly provided SSM path**
    - For any valid SSM path string, the construct uses that exact path without modification
    - **Validates: Requirements 6.1**

- [ ] 6. Configuration classes — require explicit fields
  - [x] 6.1 ACM Config — require `ssm.namespace` or explicit exports
    - In `src/cdk_factory/configurations/resources/acm.py`, modify the `ssm_exports` property
    - Remove the auto-generation of `/{workload_env}/{workload_name}/certificate/arn` from deployment properties
    - When no explicit exports are defined and `ssm.auto_export` is enabled, require `ssm.namespace` and use it; raise `ValueError` if missing
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.2 ECR Config — require namespace for `ecr_ref` derivation
    - In `src/cdk_factory/configurations/resources/ecr.py`, modify the `ecr_ssm_path` property
    - Remove the `/{workload}/{env}/ecr/{ref}` auto-derivation from `deployment.workload_name`/`deployment.environment`
    - When `ecr_ref` is provided, look for `ssm.namespace` or `ssm.imports.namespace` in the config; raise `ValueError` if neither is available
    - Explicit `ecr_ssm_path` continues to take priority unchanged
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 6.3 RDS Config — require explicit `secret_name`
    - In `src/cdk_factory/configurations/resources/rds.py`, modify the `secret_name` property
    - Remove the `/{env_name}/{workload_name}/rds/credentials` auto-derivation
    - When `secret_name` is not in config, raise `ValueError` stating it is required
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 6.4 Write unit tests for config class error cases
    - Test ACM `ssm_exports` raises `ValueError` when no exports and no namespace
    - Test ECR `ecr_ssm_path` raises `ValueError` when `ecr_ref` is set but no namespace
    - Test RDS `secret_name` raises `ValueError` when not provided
    - Test all three return correct values when properly configured
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3, 9.1, 9.2_

  - [ ]* 6.5 Write property tests for config class value pass-through and derivation
    - **Property 5: Explicit config values are returned unchanged**
    - For any valid string provided as explicit `ssm.exports` (ACM), `ecr_ssm_path` (ECR), or `secret_name` (RDS), the config class returns that exact value
    - **Validates: Requirements 7.1, 8.1, 9.1**
    - **Property 6: ECR SSM path derivation from namespace and ecr_ref**
    - For any valid namespace and ecr_ref, the derived path equals `/{namespace}/ecr/{ecr_ref}`
    - **Validates: Requirements 8.2**

- [ ] 7. Enhanced SSM Config — remove "default" fallback
  - [x] 7.1 Remove "default" fallback in `workload` property
    - In `src/cdk_factory/configurations/enhanced_ssm_config.py`, modify the `workload` property
    - Replace `self.config.get("workload", self.config.get("organization", "default"))` with a check that raises `ValueError` when neither `workload` nor `organization` is defined
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 7.2 Write unit tests for Enhanced SSM Config error cases
    - Test that `workload` raises `ValueError` when neither `ssm.workload` nor `ssm.organization` is defined
    - Test that it returns the configured value when present
    - _Requirements: 10.1, 10.2_

  - [ ]* 7.3 Write property test for Enhanced SSM Config workload resolution
    - **Property 7: Enhanced SSM Config workload resolution**
    - For any valid workload string provided as `ssm.workload` or `ssm.organization`, the property returns that exact value and never returns `"default"`
    - **Validates: Requirements 10.1, 10.3**

- [x] 8. Checkpoint — Verify config-layer changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. StandardizedSsmMixin — remove fallback defaults and environment allowlist
  - [x] 9.1 Remove hardcoded fallback defaults in `_resolve_template_variables()`
    - In `src/cdk_factory/interfaces/standardized_ssm_mixin.py`, remove the `"test"`, `"test-workload"`, `"us-east-1"` fallback defaults
    - When resolving template variables, only resolve variables that actually appear in the template string
    - If a needed variable (`ENVIRONMENT`, `WORKLOAD_NAME`) cannot be resolved from workload or deployment config, raise `ValueError`
    - Remove the final `else` block that falls back to environment variables with hardcoded defaults
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 9.2 Remove hardcoded environment allowlist in `_validate_ssm_path()`
    - In the same file, in `StandardizedSsmMixin._validate_ssm_path()`, remove the `if environment not in ["dev", "staging", "prod", ...]` warning block
    - Keep structural validation (leading `/`, minimum 4 segments)
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 9.3 Remove template variable requirement in `SsmStandardValidator._validate_ssm_path()`
    - In the `SsmStandardValidator` class in the same file, remove the check that emits an error when `{{ENVIRONMENT}}` or `{{WORKLOAD_NAME}}` is not in the path
    - Keep structural validation (leading `/`, minimum segments)
    - _Requirements: 13.1, 13.2, 13.3_

  - [ ]* 9.4 Write unit tests for mixin and validator changes
    - Test that `_resolve_template_variables()` raises `ValueError` when `{{ENVIRONMENT}}` is in template but no config provides it
    - Test that `_resolve_template_variables()` correctly resolves when workload config provides values
    - Test that `_validate_ssm_path()` no longer warns on custom environment names
    - Test that `SsmStandardValidator._validate_ssm_path()` accepts paths without template variables
    - _Requirements: 11.1, 11.2, 12.1, 12.2, 13.1, 13.2_

  - [ ]* 9.5 Write property tests for template resolution and path validation
    - **Property 8: Template variable resolution uses config values**
    - For any valid environment and workload_name in config, resolving `{{ENVIRONMENT}}` and `{{WORKLOAD_NAME}}` produces the correct substitutions with no `"test"` artifacts
    - **Validates: Requirements 11.1, 11.3**
    - **Property 9: SSM path validation accepts any structurally valid path**
    - For any string starting with `/` and having at least 4 segments, the validator accepts it regardless of environment segment value or template variable presence
    - **Validates: Requirements 12.1, 12.2, 12.3, 13.1, 13.2, 13.3**

- [ ] 10. DeploymentConfig — require `ssm_namespace` parameter
  - [x] 10.1 Modify `get_ssm_parameter_name()` to require `ssm_namespace`
    - In `src/cdk_factory/configurations/deployment.py`, add `ssm_namespace: Optional[str] = None` parameter to `get_ssm_parameter_name()`
    - When `ssm_namespace` is provided, construct path as `/{ssm_namespace}/{resource_type}/{resource_name}[/{resource_property}]`
    - When `ssm_namespace` is not provided, raise `ValueError` instead of using the hardcoded `/{environment}/{workload_name}/...` pattern
    - _Requirements: 15.1, 15.2, 15.3_

  - [ ]* 10.2 Write unit tests for DeploymentConfig error cases
    - Test that `get_ssm_parameter_name()` raises `ValueError` when no `ssm_namespace` is provided
    - Test that it constructs the correct path when `ssm_namespace` is provided
    - _Requirements: 15.1, 15.2_

  - [ ]* 10.3 Write property test for DeploymentConfig namespace path
    - **Property 11: DeploymentConfig SSM path uses provided namespace**
    - For any valid namespace, resource_type, resource_name, and optional resource_property, the path is `/{namespace}/{resource_type}/{resource_name}[/{resource_property}]` (lowercased)
    - **Validates: Requirements 15.1**

- [ ] 11. Error message consistency — verify diagnostic components
  - [ ]* 11.1 Write property test for error message diagnostic components
    - **Property 10: Error messages contain required diagnostic components**
    - For any stack name and missing config field path, every `ValueError` raised by the config-driven naming changes contains the stack/component name, the missing field path, and a corrective action
    - **Validates: Requirements 14.2**

- [ ] 12. RUM Stack — verify existing fix and add regression test
  - [ ]* 12.1 Write regression test for RUM stack config-driven SSM
    - Verify that the RUM stack does not auto-inject SSM imports from deployment properties
    - Verify that when SSM imports are explicitly configured, they are used correctly
    - Verify existing `test_rum_stack.py` tests still pass
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 13. Final checkpoint — full test suite
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design uses Python throughout — all code changes are in Python files within `cdk-factory/src/cdk_factory/`
- Property-based tests use `hypothesis` (Python PBT library) with minimum 100 iterations per property
- RUM stack (Req 5) is already fixed — task 12 is a verification/regression test only
- The API Gateway Integration Utility (Req 4) has a remaining deployment fallback that must be converted to an error
- All `ValueError` messages follow the pattern: stack/component name + missing field path + corrective action
- This is intentionally breaking for consumers who relied on silent fallbacks — the migration path is: run `cdk synth` → get clear error → add missing config → re-run
