# Implementation Plan: Per-Client SSM Namespace for Cognito App Clients

## Overview

Incrementally add an optional `ssm_namespace` field to Cognito app client configurations, update the stack to resolve per-client SSM namespaces during parameter export, add validation and warning logic, update the sample config, and cover everything with property-based and unit tests.

## Tasks

- [x] 1. Add `ssm_namespace` field to CognitoConfig and add helper for client namespace extraction
  - In `cdk-factory/src/cdk_factory/configurations/resources/cognito.py`, update the `app_clients` property docstring to document the optional `ssm_namespace` field
  - Add a module-level or static helper function `get_client_ssm_namespace(client_config: dict) -> str | None` that returns `client_config.get("ssm_namespace")`
  - _Requirements: 1.1, 1.2, 1.3, 5.2_

- [x] 2. Implement per-client namespace resolution and SSM export logic in CognitoStack
  - [x] 2.1 Add `_resolve_client_namespace` method to CognitoStack
    - In `cdk-factory/src/cdk_factory/stack_library/cognito/cognito_stack.py`, add a `_resolve_client_namespace(self, client_config: dict) -> str` method
    - If `ssm_namespace` is present and non-empty, return it; if absent/None, return `self.stack_config.ssm_namespace`
    - If `ssm_namespace` is an empty or whitespace-only string, raise `ValueError` with a descriptive message naming the client
    - _Requirements: 2.1, 2.3, 6.2_

  - [x] 2.2 Update `_export_ssm_parameters` to use per-client namespace
    - Modify the auto-export loop in `_export_ssm_parameters` so that pool-level parameters (`user_pool_id`, `user_pool_arn`, `user_pool_name`) always use the pool-level namespace
    - For each app client, look up the original `client_config` dict and call `_resolve_client_namespace` to determine the effective namespace for that client's SSM parameters
    - Export `app_client_{safe_name}_id` under the resolved client namespace instead of always using the pool namespace
    - _Requirements: 2.1, 2.3, 3.1, 3.2, 4.1, 4.2_

  - [x] 2.3 Update `_store_client_secret_in_secrets_manager` to use per-client namespace
    - Pass the `client_config` dict into `_store_client_secret_in_secrets_manager` (update the method signature)
    - Use `_resolve_client_namespace(client_config)` instead of `self.stack_config.ssm_namespace` when exporting the `secret_arn` SSM parameter
    - _Requirements: 2.2_

  - [x] 2.4 Add warning when `ssm_namespace` is set but auto_export is disabled
    - In `_create_app_clients`, after creating each client, check if the client has `ssm_namespace` set but `ssm.auto_export` is false and no explicit exports are configured
    - If so, log a warning using the existing `logger` instance
    - _Requirements: 6.1_

- [x] 3. Checkpoint - Verify core implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x]* 4. Property-based tests for namespace resolution logic
  - [x]* 4.1 Write property test: client namespace config parsing
    - **Property 1: Client namespace config parsing**
    - Use Hypothesis to generate random dicts with/without `ssm_namespace` keys; verify `get_client_ssm_namespace` returns the value when present and `None` when absent
    - Create test in `cdk-factory/tests/unit/test_cognito_ssm_namespace_properties.py`
    - **Validates: Requirements 1.1, 1.2, 1.3, 5.2**

  - [x]* 4.2 Write property test: SSM path resolution uses correct namespace
    - **Property 2: SSM path resolution uses correct namespace**
    - Use Hypothesis to generate (client_name, client_namespace, pool_namespace) tuples; verify `_resolve_client_namespace` returns client namespace when present, pool namespace when absent
    - **Validates: Requirements 2.1, 2.3, 4.1, 4.2**

  - [x]* 4.3 Write property test: safe client name transformation is idempotent
    - **Property 3: Safe client name transformation is idempotent**
    - Use Hypothesis to generate random client name strings; verify applying the safe-name transformation twice produces the same result as applying it once
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x]* 4.4 Write property test: empty string namespace rejection
    - **Property 4: Empty string namespace rejection**
    - Use Hypothesis to generate whitespace-only strings (including empty string); verify `_resolve_client_namespace` raises `ValueError`
    - **Validates: Requirements 6.2**

- [x]* 5. Unit tests for per-client SSM namespace behavior
  - [x]* 5.1 Write unit test: client with `ssm_namespace` exports under client namespace
    - Synthesize a CognitoStack with one app client that has `ssm_namespace` set and `auto_export: true`; assert the SSM parameter path uses the client-level namespace
    - Create test in `cdk-factory/tests/unit/test_cognito_stack.py` or a new file `cdk-factory/tests/unit/test_cognito_ssm_namespace.py`
    - _Requirements: 2.1, 4.1_

  - [x]* 5.2 Write unit test: client without `ssm_namespace` exports under pool namespace
    - Synthesize a stack with a client that has no `ssm_namespace`; assert the SSM parameter path uses the pool-level namespace
    - _Requirements: 2.3, 5.1_

  - [x]* 5.3 Write unit test: pool-level parameters always use pool namespace
    - Synthesize a stack where a client has a custom `ssm_namespace`; assert `user_pool_id`, `user_pool_arn`, `user_pool_name` are still exported under the pool namespace
    - _Requirements: 3.1, 3.2_

  - [x]* 5.4 Write unit test: warning logged when `ssm_namespace` set but auto_export disabled
    - Configure a client with `ssm_namespace` but `auto_export: false`; assert a warning is logged
    - _Requirements: 6.1_

  - [x]* 5.5 Write unit test: empty `ssm_namespace` raises ValueError
    - Configure a client with `ssm_namespace: ""`; assert `ValueError` is raised with a descriptive message
    - _Requirements: 6.2_

  - [x]* 5.6 Write unit test: mixed clients with different namespaces
    - Synthesize a stack with two clients — one with `ssm_namespace` and one without; assert each client's SSM parameters are under the correct namespace
    - _Requirements: 4.1, 4.2_

  - [x]* 5.7 Write unit test: secret ARN exported under client namespace
    - Synthesize a stack with a client that has `generate_secret: true` and a custom `ssm_namespace`; assert the secret ARN SSM parameter uses the client namespace
    - _Requirements: 2.2_

- [x] 6. Checkpoint - Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update sample configuration to demonstrate per-client SSM namespace
  - In `cdk-factory/samples/cognito/app_clients_sample.json`, add `ssm_namespace` to at least one app client entry (e.g., `"ssm_namespace": "my-app/prod/web-auth"` on the `amplify-web-app` client)
  - Ensure at least one other client in the sample does NOT have `ssm_namespace`, demonstrating the fallback behavior
  - _Requirements: 7.1, 7.2_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases using CDK template assertions
- The implementation language is Python, matching the existing codebase and design document
