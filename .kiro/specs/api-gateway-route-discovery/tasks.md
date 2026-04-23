# Implementation Plan: API Gateway Route Discovery

## Overview

Implement automatic route discovery so Lambda configs are the single source of truth for API Gateway routes. The Lambda_Stack exports route metadata to SSM alongside ARN exports, and the API_Gateway_Stack discovers and merges those routes at synth time. Changes span `cdk-factory` (new utility + modifications to both stacks) and `Acme-SaaS-IaC` (config cleanup). All new pure-function logic is covered by Hypothesis property-based tests mapping to the 9 design correctness properties.

## Tasks

- [x] 1. Create RouteMetadataValidator utility
  - [x] 1.1 Create `cdk-factory/src/cdk_factory/utilities/route_metadata_validator.py`
    - Implement `RouteMetadataValidator` class with static methods: `validate_route`, `validate_method`, `validate_route_metadata`
    - `validate_route` checks non-empty string starting with `/`
    - `validate_method` checks method is one of GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD (case-insensitive)
    - `validate_route_metadata` validates the full metadata dict including any `routes` sub-array
    - Raise descriptive `ValueError` on invalid input referencing the lambda name
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 1.2 Write property test for route validation (Property 8)
    - **Property 8: Route validation accepts valid and rejects invalid**
    - Test that `validate_route` accepts any non-empty string starting with `/` and rejects all others
    - Test that `validate_method` accepts exactly the 7 valid HTTP methods (case-insensitive) and rejects all others
    - Use Hypothesis `text()` and `sampled_from()` strategies
    - Create file `cdk-factory/tests/unit/test_route_metadata_validator_properties.py`
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [ ]* 1.3 Write unit tests for RouteMetadataValidator
    - Test edge cases: empty string, missing `/` prefix, None values, unknown HTTP methods
    - Test `validate_route_metadata` with complete metadata dicts including `routes` sub-array
    - Verify error messages include lambda name for debugging
    - Create file `cdk-factory/tests/unit/test_route_metadata_validator.py`
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. Add route metadata SSM export to LambdaStack
  - [x] 2.1 Implement `__export_route_metadata_to_ssm` in `cdk-factory/src/cdk_factory/stack_library/aws_lambdas/lambda_stack.py`
    - Add new private method `__export_route_metadata_to_ssm` called from `build()` after `__export_lambda_arns_to_ssm()`
    - For each Lambda in `exported_lambda_arns` that has a non-None `config.api` with a non-empty `route`:
      - Call `RouteMetadataValidator.validate_route_metadata` on the api config dict
      - Serialize route metadata (route, method, skip_authorizer, authorization_type, routes) to JSON
      - Write SSM StringParameter at `{prefix}/{lambda_name}/api-route` with tier STANDARD
    - Skip export when `ssm.auto_export` is `false`
    - Skip Lambdas without an `api` section silently
    - Use the same namespace/prefix logic as `__export_lambda_arns_to_ssm`
    - Access the raw api config via `config.api._config` on `LambdaFunctionConfig`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 6.1, 6.2, 6.3_

  - [ ]* 2.2 Write property test for serialization round-trip (Property 1)
    - **Property 1: Route metadata serialization round-trip**
    - Generate random valid route metadata dicts and verify `json.dumps` → `json.loads` preserves all fields
    - Use Hypothesis strategies for route paths (starting with `/`), valid methods, booleans, and route arrays
    - Create file `cdk-factory/tests/unit/test_route_ssm_export_properties.py`
    - **Validates: Requirements 1.1, 1.2, 1.5**

  - [ ]* 2.3 Write property test for no-api-section produces no export (Property 2)
    - **Property 2: No api section produces no route export**
    - Generate Lambda configs without `api` sections and verify the export function produces no SSM parameter
    - **Validates: Requirements 1.3**

  - [ ]* 2.4 Write property test for SSM path naming convention (Property 3)
    - **Property 3: SSM path follows naming convention**
    - For any valid namespace and lambda name, verify the generated path equals `/{namespace}/lambda/{lambda-name}/api-route`
    - **Validates: Requirements 1.4, 6.1**

  - [ ]* 2.5 Write unit tests for route SSM export
    - Test that `ssm.auto_export=false` suppresses route export (Req 6.2)
    - Test SSM parameter tier is STANDARD (Req 6.3)
    - Test multi-route Lambda exports all routes in the `routes` array (Req 1.2)
    - Test Lambda without `api` section produces no route SSM param (Req 1.3)
    - Create file `cdk-factory/tests/unit/test_lambda_route_ssm_export.py`
    - _Requirements: 1.1, 1.2, 1.3, 6.2, 6.3_

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add route discovery and merge to ApiGatewayStack
  - [x] 4.1 Implement `_discover_routes_from_dependencies` in `cdk-factory/src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py`
    - Add method that iterates over `self.stack_config.dependencies`
    - For each dependency, build the SSM path `{prefix}/lambda/{lambda-name}/api-route` using the `ssm.imports.namespace` config
    - Read SSM parameters using `ssm.StringParameter.value_for_string_parameter`
    - Deserialize JSON route metadata and validate with `RouteMetadataValidator.validate_route_metadata`
    - Convert discovered metadata to the internal route dict format: `path` (from `route`), `method`, `lambda_name` (from SSM path), `skip_authorizer`, `authorization_type` (set to `NONE` if `skip_authorizer` is true)
    - Expand multi-route Lambdas: for each entry in the `routes` sub-array, create an additional route dict pointing to the same `lambda_name`
    - Silently skip non-Lambda dependencies and Lambdas without route exports (catch SSM not-found)
    - Log each discovered route at INFO level
    - _Requirements: 2.1, 2.6, 2.7, 2.8, 2.9, 2.10, 7.1, 7.2, 7.3, 7.4_

  - [x] 4.2 Implement `_merge_routes` in `api_gateway_stack.py`
    - Accept explicit routes list and discovered routes list
    - Index explicit routes by `(path, method.upper())` tuple
    - Start merged list with all explicit routes
    - For each discovered route, check if `(path, method)` key exists in explicit index
    - If conflict: log WARNING with path, method, and both sources; skip the discovered route
    - If no conflict: append discovered route to merged list; log INFO
    - Return the merged list
    - _Requirements: 2.1, 2.4, 2.5_

  - [x] 4.3 Update `_build` method to integrate discovery and merge
    - Call `_discover_routes_from_dependencies()` before route setup
    - Get explicit routes from `self.api_config.routes or []`
    - Call `_merge_routes(explicit, discovered)` to produce final route set
    - Fall back to default health route only if merged set is empty
    - Pass merged routes to existing `_create_rest_api` / `_create_http_api` flow
    - Ensure gateway-level settings (CORS, custom domain, Cognito, deploy_options) apply regardless of route source
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_

  - [ ]* 4.4 Write property test for merge produces union (Property 4)
    - **Property 4: Merge produces union minus conflicts**
    - Generate two disjoint sets of routes and verify merged set is the exact union
    - Use Hypothesis strategies for route path/method combinations
    - Create file `cdk-factory/tests/unit/test_route_discovery_properties.py`
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [ ]* 4.5 Write property test for explicit wins on conflict (Property 5)
    - **Property 5: Explicit routes win on path+method conflict**
    - Generate overlapping explicit and discovered routes; verify explicit definition is kept and count is exactly 1
    - **Validates: Requirements 2.5**

  - [ ]* 4.6 Write property test for authorization mapping (Property 6)
    - **Property 6: Authorization mapping from skip_authorizer**
    - Generate discovered routes with random `skip_authorizer` values; verify `authorization_type` is `NONE` when true, default otherwise
    - **Validates: Requirements 2.7, 2.8**

  - [ ]* 4.7 Write property test for multi-route expansion (Property 7)
    - **Property 7: Multi-route expansion**
    - Generate route metadata with a primary route and N sub-routes; verify expansion produces exactly N+1 routes with the same `lambda_name`
    - **Validates: Requirements 2.9, 4.2**

  - [ ]* 4.8 Write property test for discovery scoped to depends_on (Property 9)
    - **Property 9: Discovery scoped to depends_on**
    - Generate a set of available Lambda stacks and a `depends_on` subset; verify only routes from `depends_on` stacks appear in discovered routes
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 4.9 Write unit tests for route discovery and merge
    - Test non-Lambda `depends_on` entries are silently skipped (Req 7.3)
    - Test Lambda stacks without route exports are silently skipped (Req 7.4)
    - Test INFO logging for each discovered route (Req 2.10)
    - Test WARNING logging on path+method conflict (Req 2.5)
    - Test gateway-level settings applied regardless of route source (Req 3.2)
    - Test backward compatibility: explicit routes only, no discovery (Req 2.2)
    - Test discovery only: no explicit routes array in config (Req 2.3)
    - Create file `cdk-factory/tests/unit/test_route_discovery.py`
    - _Requirements: 2.2, 2.3, 2.5, 2.10, 3.2, 7.3, 7.4_

- [x] 5. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Clean up Acme-SaaS-IaC config
  - [x] 6.1 Remove duplicated routes from `Acme-SaaS-IaC/cdk/configs/stacks/network/api-gateway-primary.json`
    - Remove the `routes` array from the `api_gateway` section entirely
    - Keep all gateway-level settings: `name`, `api_type`, `description`, `deploy_options`, `custom_domain`, `cognito`, `cors`
    - Keep `depends_on` array referencing `lambda-app-settings` and `lambda-workflow-sqs`
    - Keep `ssm` block with `auto_export` and `imports.namespace`
    - _Requirements: 3.1, 3.2, 3.3, 4.1_

  - [ ]* 6.2 Write integration test for end-to-end route discovery
    - Verify a CDK synth with Lambda stack exporting routes and API Gateway stack discovering them produces correct CloudFormation resources
    - Verify migration scenario: routes in both explicit config and discovery produce correct merged output with warnings
    - Create file `cdk-factory/tests/integration/test_route_discovery_integration.py`
    - _Requirements: 2.1, 4.2, 4.3_

- [x] 7. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (Python)
- Unit tests validate specific examples and edge cases
- All code changes are in Python targeting `cdk-factory` and `Acme-SaaS-IaC`
- The `api` attribute on `LambdaFunctionConfig` is an `ApiGatewayConfigRouteConfig` instance; access raw dict via `._config`
- Route discovery uses the existing `depends_on` array — no new config fields needed
