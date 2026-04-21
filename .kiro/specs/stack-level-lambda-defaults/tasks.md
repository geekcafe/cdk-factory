# Implementation Plan: Stack-Level Lambda Defaults

## Overview

Implement stack-level `additional_permissions` and `additional_environment_variables` for the Lambda stack module. The approach creates a pure merge utility module first, validates it with property-based tests, then integrates into `LambdaStack.build()`. All merge logic is pure dict/list manipulation with no CDK dependencies.

## Tasks

- [x] 1. Create merge utility module with core functions
  - [x] 1.1 Create `cdk_factory/utilities/merge_defaults.py` with `permission_key()` helper
    - Implement the `permission_key(entry: dict | str) -> Hashable` function that extracts a comparable key from any permission format
    - Support all four formats: structured DynamoDB `(action, table)`, structured S3 `(action, bucket)`, string keys, and inline IAM `(frozenset(actions), frozenset(resources))`
    - _Requirements: 1.4, 3.3_

  - [x] 1.2 Implement `merge_permissions()` function
    - Takes `resource_permissions` and `stack_permissions` lists
    - Returns resource permissions plus stack-level entries whose `permission_key` does not match any resource-level entry
    - Resource-level entries are never modified or removed
    - _Requirements: 1.1, 1.2, 3.1, 3.3_

  - [x] 1.3 Implement `merge_environment_variables()` function
    - Takes `resource_env_vars` and `stack_env_vars` lists
    - Returns resource env vars plus stack-level entries whose `name` does not match any resource-level entry's `name`
    - _Requirements: 2.1, 2.2, 3.2, 3.4_

  - [x] 1.4 Implement `merge_stack_defaults_into_resources()` function
    - Iterates each resource dict in the `resources` list
    - Skips resources where `skip_stack_defaults` is `true`
    - Mutates each resource dict in-place, merging `permissions` and `environment_variables`
    - Initializes missing `permissions` or `environment_variables` keys to `[]` before merging
    - _Requirements: 1.1, 2.1, 4.1, 4.2, 4.3_

- [x] 2. Property-based tests for merge utility
  - [x]* 2.1 Write property test: permissions merge with resource-level precedence
    - **Property 1: Permissions merge with resource-level precedence**
    - Use Hypothesis to generate random resource dicts with permissions and random stack-level permissions
    - Verify merged result contains all originals plus only non-matching stack-level entries
    - **Validates: Requirements 1.1, 1.2, 3.1, 3.3**

  - [x]* 2.2 Write property test: environment variables merge with name-based precedence
    - **Property 2: Environment variables merge with name-based precedence**
    - Use Hypothesis to generate random resource dicts with env vars and random stack-level env vars
    - Verify merged result contains all originals plus only entries with new names
    - **Validates: Requirements 2.1, 2.2, 3.2, 3.4**

  - [x]* 2.3 Write property test: absent or empty stack-level fields are a no-op
    - **Property 3: Absent or empty stack-level fields are a no-op**
    - Use Hypothesis to generate random resource dicts, merge with empty/absent fields
    - Verify output equals input
    - **Validates: Requirements 1.3, 2.3, 4.1, 4.2, 4.3, 4.4**

  - [x]* 2.4 Write property test: all permission formats supported in merge
    - **Property 4: All permission formats are supported in merge**
    - Use Hypothesis to generate permissions of all four formats
    - Verify merge completes without error and deduplication works across formats
    - **Validates: Requirements 1.4**

  - [x]* 2.5 Write property test: skip_stack_defaults opt-out is honored
    - **Property 5: skip_stack_defaults opt-out is honored**
    - Use Hypothesis to generate resource dicts with `skip_stack_defaults: true` and non-empty stack-level defaults
    - Verify the resource's permissions and environment_variables are identical to originals after merge
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Example-based unit tests for merge utility
  - [x]* 4.1 Write unit tests for `permission_key()` helper
    - Test each permission format returns the expected key
    - Test DynamoDB same table different action produces different keys
    - Test S3 same bucket different action produces different keys
    - Test inline IAM with same actions/resources matches
    - _Requirements: 1.4, 3.3_

  - [x]* 4.2 Write unit tests for merge edge cases
    - Test resource with no `permissions` key gets stack-level permissions added
    - Test resource with no `environment_variables` key gets stack-level env vars added
    - Test mixed permission formats in a single merge (structured + string + inline IAM)
    - Test duplicate env var name keeps resource-level value
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

  - [x]* 4.3 Write unit tests for `skip_stack_defaults` behavior
    - Test `skip_stack_defaults: true` skips merge entirely
    - Test `skip_stack_defaults: false` merges normally
    - Test absent `skip_stack_defaults` merges normally (defaults to false)
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 5. Add optional StackConfig convenience properties
  - [x] 5.1 Add `additional_permissions` and `additional_environment_variables` properties to `StackConfig`
    - Add `additional_permissions` property returning `self.dictionary.get("additional_permissions", [])`
    - Add `additional_environment_variables` property returning `self.dictionary.get("additional_environment_variables", [])`
    - _Requirements: 1.1, 2.1, 5.1, 5.2_

- [x] 6. Integrate merge into LambdaStack.build()
  - [x] 6.1 Call `merge_stack_defaults_into_resources()` in `LambdaStack.build()`
    - Import `merge_stack_defaults_into_resources` from `cdk_factory.utilities.merge_defaults`
    - After loading the `resources` list and before the `LambdaFunctionConfig` loop, read `additional_permissions` and `additional_environment_variables` from `stack_config.dictionary`
    - Call `merge_stack_defaults_into_resources(resources, additional_permissions, additional_env_vars)`
    - _Requirements: 1.1, 2.1, 6.1, 6.2, 6.3_

  - [ ]* 6.2 Write integration test for LambdaStack with stack-level defaults
    - Build a `LambdaStack` with `additional_permissions` and `additional_environment_variables` in the stack config JSON
    - Verify the `LambdaFunctionConfig` objects receive the merged permissions and environment variables
    - Verify a resource with `skip_stack_defaults: true` is unaffected
    - _Requirements: 1.1, 2.1, 4.1, 5.1, 6.3_

- [x] 7. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The merge utility module has zero CDK dependencies, making it easy to test in isolation
- Property tests use Hypothesis with minimum 100 iterations per property
- All merge logic operates on raw dicts before `LambdaFunctionConfig` instantiation
- `__inherits__` resolution is handled by `JsonLoadingUtility` before our code runs (Requirement 7)
