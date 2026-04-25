# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Stream ARN Export Fails When Streams Disabled
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to DynamoDB configs where `ssm.auto_export=true` and `stream_specification` is not set
  - Create test file `tests/unit/test_dynamodb_stream_arn_bug.py`
  - Test 1a: Create `DynamoDBConfig({"name": "t"})` and assert `config.stream_specification` is `None` — will fail with `AttributeError` on unfixed code because the property doesn't exist
  - Test 1b: Create `DynamoDBConfig({"name": "t"})` and assert `config.streams_enabled` is `False` — will fail with `AttributeError` on unfixed code
  - Test 1c: Build a `DynamoDBStack` with `ssm.auto_export: true`, `ssm.namespace: "test/dev/dynamodb/app"`, and no `stream_specification` — assert `table_stream_arn` is NOT in the exported SSM parameters. On unfixed code, `table_stream_arn` WILL be exported (bug condition), so this assertion fails
  - Test 1d (property-based): Use Hypothesis to generate random table names and verify that for any config without `stream_specification`, `streams_enabled` is `False` and `stream_specification` is `None` — will fail on unfixed code
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g., `AttributeError: 'DynamoDBConfig' has no attribute 'stream_specification'`, `table_stream_arn` present in SSM exports when streams not enabled)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Stream Config Properties and Stream-Enabled Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `tests/unit/test_dynamodb_stream_arn_preservation.py`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "my-table"}).name` returns `"my-table"`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "t", "gsi_count": 3}).gsi_count` returns `3`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "t", "ttl_attribute": "expires_at"}).ttl_attribute` returns `"expires_at"`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "t", "point_in_time_recovery": False}).point_in_time_recovery` returns `False`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "t", "enable_delete_protection": False}).enable_delete_protection` returns `False`
  - Observe on UNFIXED code: `DynamoDBConfig({"name": "t", "replica_regions": ["us-west-1"]}).replica_regions` returns `["us-west-1"]`
  - Observe on UNFIXED code: `RESOURCE_AUTO_EXPORTS` for non-DynamoDB types (vpc, rds, lambda, s3, cognito, api_gateway, security_group) are unchanged
  - Test 2a (property-based): Use Hypothesis to generate random DynamoDB configs (varying `name`, `gsi_count`, `ttl_attribute`, `point_in_time_recovery`, `enable_delete_protection`, `replica_regions`) and verify all non-stream properties return expected values — these should pass on both unfixed and fixed code
  - Test 2b: Verify `RESOURCE_AUTO_EXPORTS` for all non-DynamoDB resource types remain unchanged after fix
  - Test 2c: Verify that configs with `ssm.auto_export: false` do not trigger SSM exports
  - Verify tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for DynamoDB Stream ARN export failure when streams not enabled

  - [x] 3.1 Add `stream_specification` and `streams_enabled` properties to `DynamoDBConfig`
    - In `src/cdk_factory/configurations/resources/dynamodb.py`, add a `stream_specification` property that returns the optional stream view type string from config (`"NEW_AND_OLD_IMAGES"`, `"NEW_IMAGE"`, `"OLD_IMAGE"`, `"KEYS_ONLY"`) or `None` when not set
    - Add a `streams_enabled` convenience property that returns `True` when `stream_specification is not None`
    - Follow the existing property pattern in `DynamoDBConfig` (check `self.__config` is dict, use `.get()`)
    - _Bug_Condition: isBugCondition(input) where input.stream_specification = NONE and input.ssm_auto_export = true_
    - _Expected_Behavior: config.stream_specification returns None when not set; config.streams_enabled returns False when stream_specification is None_
    - _Preservation: All existing properties (name, use_existing, replica_regions, enable_delete_protection, point_in_time_recovery, gsi_count, ttl_attribute, global_secondary_indexes) unchanged_
    - _Requirements: 1.3, 2.3_

  - [x] 3.2 Pass stream config to `TableV2` constructor in `_create_new_table()`
    - In `src/cdk_factory/stack_library/dynamodb/dynamodb_stack.py`, in `_create_new_table()`, when `self.db_config.stream_specification` is set, add `dynamodb_stream` to the `TableV2` constructor props
    - Map string values to `dynamodb.StreamViewType` enum: `"NEW_AND_OLD_IMAGES"` → `dynamodb.StreamViewType.NEW_AND_OLD_IMAGES`, etc.
    - When `stream_specification` is `None`, do not add `dynamodb_stream` to props (preserves current behavior for tables without streams)
    - _Bug_Condition: Tables without stream_specification should not have dynamodb_stream in props_
    - _Expected_Behavior: Tables with stream_specification get the correct StreamViewType passed to TableV2_
    - _Preservation: Tables without stream_specification continue to be created without stream config_
    - _Requirements: 2.3, 3.3_

  - [x] 3.3 Replace `hasattr()` check with `self.db_config.streams_enabled` in `_export_ssm_parameters()`
    - In `src/cdk_factory/stack_library/dynamodb/dynamodb_stack.py`, in `_export_ssm_parameters()`, replace the `hasattr(self.table, "table_stream_arn")` guard with `self.db_config.streams_enabled`
    - Only include `table_stream_arn` in `resource_values` when `self.db_config.streams_enabled` is `True`
    - Always include `table_name` and `table_arn` when auto-export is enabled
    - _Bug_Condition: isBugCondition(input) where hasattr() always returns True for TableV2 class property_
    - _Expected_Behavior: table_stream_arn excluded from exports when streams_enabled is False_
    - _Preservation: table_stream_arn included in exports when streams_enabled is True_
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Stream ARN Not Exported When Streams Disabled
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run `pytest tests/unit/test_dynamodb_stream_arn_bug.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Stream Config Properties and Stream-Enabled Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run `pytest tests/unit/test_dynamodb_stream_arn_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run `pytest tests/unit/test_dynamodb_stream_arn_bug.py tests/unit/test_dynamodb_stream_arn_preservation.py tests/unit/test_dynamodb_config.py tests/unit/test_dynamodb_stack.py -v`
  - Ensure all new and existing DynamoDB tests pass
  - Ensure no regressions in existing test suite
  - Ask the user if questions arise
