# DynamoDB Stream ARN Export Fix — Bugfix Design

## Overview

CloudFormation fails with "Attribute 'StreamArn' does not exist" when deploying a DynamoDB table with `ssm.auto_export: true` because the system unconditionally exports `table_stream_arn` for all DynamoDB tables. The fix makes stream ARN export conditional on streams being explicitly enabled in the table configuration, adds `stream_specification` support to `DynamoDBConfig`, and replaces the unreliable `hasattr()` check with a config-driven check.

## Glossary

- **Bug_Condition (C)**: A DynamoDB table is deployed with `ssm.auto_export: true` but without DynamoDB Streams enabled — the system attempts to export `table_stream_arn` which doesn't exist on the deployed resource
- **Property (P)**: When streams are not enabled, `table_stream_arn` is excluded from SSM exports; when streams are enabled, it is included
- **Preservation**: All existing behavior for tables with streams enabled, tables without SSM auto-export, other resource types' auto-exports, and non-stream DynamoDB features (GSIs, TTL, replicas, PITR) must remain unchanged
- **`DynamoDBConfig`**: Configuration class in `src/cdk_factory/configurations/resources/dynamodb.py` that parses DynamoDB table settings from config dicts
- **`DynamoDBStack._export_ssm_parameters()`**: Method in `src/cdk_factory/stack_library/dynamodb/dynamodb_stack.py` that exports table attributes to SSM parameters
- **`RESOURCE_AUTO_EXPORTS`**: Dict in `src/cdk_factory/configurations/enhanced_ssm_config.py` mapping resource types to their auto-exportable attributes
- **`TableV2`**: AWS CDK construct for DynamoDB tables; always defines `table_stream_arn` as a class property regardless of whether streams are enabled

## Bug Details

### Bug Condition

The bug manifests when a DynamoDB table is created without DynamoDB Streams enabled and `ssm.auto_export` is true. Three defects combine to cause the failure:

1. `RESOURCE_AUTO_EXPORTS["dynamodb"]` unconditionally includes `table_stream_arn`
2. `_export_ssm_parameters()` uses `hasattr(self.table, "table_stream_arn")` which always returns `True` for CDK's `TableV2` (it's a class property, not an instance attribute)
3. `DynamoDBConfig` has no `stream_specification` property, so streams can never be intentionally enabled through configuration

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DynamoDBTableConfig
  OUTPUT: boolean

  RETURN input.ssm_auto_export = true
         AND input.stream_specification = NONE
         AND "table_stream_arn" IN RESOURCE_AUTO_EXPORTS["dynamodb"]
END FUNCTION
```

### Examples

- **Table without streams, auto-export on**: Config `{"dynamodb": {"name": "MyTable"}, "ssm": {"auto_export": true, ...}}` → CloudFormation fails with "Attribute 'StreamArn' does not exist" because `table_stream_arn` is exported but streams are not enabled. Expected: deployment succeeds, only `table_name` and `table_arn` are exported.
- **Table with streams, auto-export on**: Config `{"dynamodb": {"name": "MyTable", "stream_specification": "NEW_AND_OLD_IMAGES"}, "ssm": {"auto_export": true, ...}}` → Currently impossible to configure (no `stream_specification` property). Expected: deployment succeeds, `table_name`, `table_arn`, and `table_stream_arn` are all exported.
- **Table without streams, auto-export off**: Config `{"dynamodb": {"name": "MyTable"}, "ssm": {"auto_export": false}}` → Works correctly today (no SSM exports attempted). Expected: continues to work.
- **Edge case — hasattr check**: `hasattr(TableV2_instance, "table_stream_arn")` returns `True` even without streams enabled because `table_stream_arn` is a class-level property on `TableV2`. The value resolves to an unresolvable CloudFormation token at deploy time.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Tables with DynamoDB Streams enabled and `ssm.auto_export: true` must continue to export `table_stream_arn` along with `table_name` and `table_arn`
- Tables with `ssm.auto_export: false` or no SSM configuration must continue to skip all SSM exports
- All non-stream DynamoDB features (GSIs, TTL, replicas, PITR, delete protection, removal policy) must continue to work identically
- Other resource types in `RESOURCE_AUTO_EXPORTS` (VPC, RDS, Lambda, S3, Cognito, API Gateway, Security Group) must continue to export their attributes unchanged
- `table_name` and `table_arn` must always be exported when auto-export is enabled, regardless of stream settings

**Scope:**
All inputs that do NOT involve DynamoDB tables with `ssm.auto_export: true` and no stream configuration should be completely unaffected by this fix. This includes:
- Mouse/CLI interactions with other resource types
- DynamoDB tables with streams explicitly enabled
- DynamoDB tables without SSM auto-export
- All `RESOURCE_AUTO_IMPORTS` behavior

## Hypothesized Root Cause

Based on the bug description and code analysis, three defects combine:

1. **Unconditional Auto-Export Registration**: `RESOURCE_AUTO_EXPORTS["dynamodb"]` includes `"table_stream_arn"` unconditionally. The auto-export system in `EnhancedSsmConfig._get_auto_exports()` returns this list without checking whether streams are actually enabled. This is the root registration of the unwanted export.

2. **Unreliable hasattr() Guard**: `_export_ssm_parameters()` in `dynamodb_stack.py` uses `hasattr(self.table, "table_stream_arn")` as a guard, but CDK's `TableV2` always defines `table_stream_arn` as a class property. The property getter returns a CloudFormation token that only resolves at deploy time — `hasattr()` returns `True` even when streams are not enabled, so the guard never filters it out.

3. **Missing Stream Configuration**: `DynamoDBConfig` has no `stream_specification` property, so there is no config-level signal to determine whether streams are enabled. Even if the export logic wanted to check config, there's nothing to check against.

## Correctness Properties

Property 1: Bug Condition — Stream ARN Not Exported When Streams Disabled

_For any_ DynamoDB table configuration where `ssm.auto_export` is true and `stream_specification` is not set (None), the fixed `_export_ssm_parameters()` function SHALL NOT include `table_stream_arn` in the exported SSM parameters, and the deployment SHALL succeed with only `table_name` and `table_arn` exported.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Stream ARN Exported When Streams Enabled

_For any_ DynamoDB table configuration where `ssm.auto_export` is true and `stream_specification` IS set to a valid stream view type, the fixed code SHALL continue to export `table_stream_arn` along with `table_name` and `table_arn`, preserving the existing behavior for stream-enabled tables.

**Validates: Requirements 3.1, 3.3**

Property 3: Preservation — Non-Stream Config Properties Unchanged

_For any_ `DynamoDBConfig` input, the fixed code SHALL produce identical results for all non-stream properties (`name`, `use_existing`, `replica_regions`, `enable_delete_protection`, `point_in_time_recovery`, `gsi_count`, `ttl_attribute`, `global_secondary_indexes`), preserving all existing configuration behavior.

**Validates: Requirements 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/cdk_factory/configurations/resources/dynamodb.py`

**Class**: `DynamoDBConfig`

**Specific Changes**:
1. **Add `stream_specification` property**: Return the optional `stream_specification` value from config (e.g., `"NEW_AND_OLD_IMAGES"`, `"NEW_IMAGE"`, `"OLD_IMAGE"`, `"KEYS_ONLY"`). Return `None` when not set.
2. **Add `streams_enabled` convenience property**: Return `True` when `stream_specification` is not `None`. This provides a clean boolean check for the export logic.

---

**File**: `src/cdk_factory/stack_library/dynamodb/dynamodb_stack.py`

**Method**: `_create_new_table()` and `_export_ssm_parameters()`

**Specific Changes**:
3. **Pass stream config to TableV2**: In `_create_new_table()`, when `self.db_config.stream_specification` is set, add `dynamodb_stream` to the `TableV2` constructor props using `dynamodb.StreamViewType` mapping.
4. **Replace hasattr() with config check**: In `_export_ssm_parameters()`, replace `hasattr(self.table, "table_stream_arn")` with `self.db_config.streams_enabled`. Only include `table_stream_arn` in `resource_values` when streams are explicitly enabled in config.

---

**File**: `src/cdk_factory/configurations/enhanced_ssm_config.py`

**Constant**: `RESOURCE_AUTO_EXPORTS`

**Specific Changes**:
5. **Keep `table_stream_arn` in the list but handle conditionally**: The `RESOURCE_AUTO_EXPORTS["dynamodb"]` list can retain `table_stream_arn` for documentation purposes, since the actual filtering now happens in `_export_ssm_parameters()` based on config. Alternatively, remove it from the static list and let `_export_ssm_parameters()` add it dynamically when streams are enabled. The simpler approach is to keep the static list unchanged and let the stack-level export logic handle the conditional.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that create `DynamoDBConfig` instances without `stream_specification` and verify the export behavior. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Missing stream_specification property**: Create `DynamoDBConfig({"name": "t"})` and access `config.stream_specification` — will fail on unfixed code because the property doesn't exist
2. **hasattr always True**: Create a `TableV2` without streams and check `hasattr(table, "table_stream_arn")` — will return `True` on unfixed code, confirming the guard is unreliable
3. **Unconditional export**: Build a `DynamoDBStack` with auto-export enabled and no streams — will include `table_stream_arn` in exports on unfixed code
4. **Stream view type passthrough**: Create `DynamoDBConfig({"name": "t", "stream_specification": "NEW_AND_OLD_IMAGES"})` and access `config.stream_specification` — will fail on unfixed code

**Expected Counterexamples**:
- `AttributeError` when accessing `config.stream_specification` (property doesn't exist)
- `table_stream_arn` present in exported parameters even when streams are not configured
- Possible causes: missing property on `DynamoDBConfig`, unreliable `hasattr()` guard, unconditional inclusion in `RESOURCE_AUTO_EXPORTS`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  config := DynamoDBConfig(input)
  ASSERT config.stream_specification = NONE
  ASSERT config.streams_enabled = false
  resource_values := _export_ssm_parameters(config)
  ASSERT "table_stream_arn" NOT IN resource_values
  ASSERT "table_name" IN resource_values
  ASSERT "table_arn" IN resource_values
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT DynamoDBConfig_original(input).name = DynamoDBConfig_fixed(input).name
  ASSERT DynamoDBConfig_original(input).use_existing = DynamoDBConfig_fixed(input).use_existing
  ASSERT DynamoDBConfig_original(input).gsi_count = DynamoDBConfig_fixed(input).gsi_count
  ASSERT DynamoDBConfig_original(input).ttl_attribute = DynamoDBConfig_fixed(input).ttl_attribute
  ASSERT DynamoDBConfig_original(input).point_in_time_recovery = DynamoDBConfig_fixed(input).point_in_time_recovery
  ASSERT DynamoDBConfig_original(input).enable_delete_protection = DynamoDBConfig_fixed(input).enable_delete_protection
  ASSERT DynamoDBConfig_original(input).replica_regions = DynamoDBConfig_fixed(input).replica_regions
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many DynamoDB config combinations automatically across the input domain
- It catches edge cases in config parsing that manual unit tests might miss
- It provides strong guarantees that non-stream behavior is unchanged for all config inputs

**Test Plan**: Observe behavior on UNFIXED code first for all non-stream properties, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Config Property Preservation**: Generate random DynamoDB configs (varying `name`, `gsi_count`, `ttl_attribute`, `point_in_time_recovery`, `enable_delete_protection`, `replica_regions`) and verify all properties return expected values — these should pass on both unfixed and fixed code
2. **Auto-Export List Preservation**: Verify `RESOURCE_AUTO_EXPORTS` for non-DynamoDB resource types (VPC, RDS, Lambda, S3, etc.) remain unchanged after the fix
3. **SSM Disabled Preservation**: Generate configs with `ssm.auto_export: false` and verify no SSM exports are attempted

### Unit Tests

- Test `DynamoDBConfig.stream_specification` returns `None` when not set
- Test `DynamoDBConfig.stream_specification` returns the correct value for each valid stream view type
- Test `DynamoDBConfig.streams_enabled` returns `False` when `stream_specification` is `None`
- Test `DynamoDBConfig.streams_enabled` returns `True` when `stream_specification` is set
- Test `_export_ssm_parameters()` excludes `table_stream_arn` when streams are not enabled
- Test `_export_ssm_parameters()` includes `table_stream_arn` when streams are enabled

### Property-Based Tests

- Generate random `DynamoDBConfig` dicts with and without `stream_specification` and verify `streams_enabled` matches `stream_specification is not None`
- Generate random DynamoDB configs without `stream_specification` and verify all existing properties (`name`, `gsi_count`, `ttl_attribute`, etc.) return identical values to unfixed code
- Generate random valid stream view types from `{"NEW_AND_OLD_IMAGES", "NEW_IMAGE", "OLD_IMAGE", "KEYS_ONLY"}` and verify `stream_specification` round-trips correctly

### Integration Tests

- Build a full `DynamoDBStack` without streams and with auto-export enabled — verify CloudFormation template does NOT contain `StreamArn` references in SSM parameters
- Build a full `DynamoDBStack` with `stream_specification: "NEW_AND_OLD_IMAGES"` and auto-export enabled — verify CloudFormation template contains `StreamArn` in SSM parameters
- Build a full `DynamoDBStack` with GSIs, TTL, and replicas but no streams — verify all features work correctly and no stream ARN is exported
