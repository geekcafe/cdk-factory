# API Gateway Route Grouping Fix — Bugfix Design

## Overview

The API Gateway nested stack auto-grouping mechanism fails because `_build_lambda_folder_cache()` reads raw JSON files from disk containing unresolved placeholder names (e.g., `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"`) while `_discover_routes_from_dependencies()` provides fully resolved names from the workload dictionary (e.g., `"asset-workbench-dev-asset-handler"`). The cache lookup always misses, sending all routes to the "default" group and exceeding CloudFormation's 500-resource limit.

The fix resolves placeholders in the `name` field when building the cache, using the same environment variables (`WORKLOAD_NAME`, `DEPLOYMENT_NAMESPACE`, etc.) available via `os.environ` during CDK synth. A secondary enhancement adds support for an explicit `route_group` field in Lambda resource configs' `api` section, allowing direct group assignment without folder resolution.

## Glossary

- **Bug_Condition (C)**: Auto-grouping is active (no explicit `nested_stacks.grouping`) AND Lambda resource configs on disk contain placeholder tokens in their `name` field
- **Property (P)**: The lambda folder cache maps resolved names to their folder paths, enabling correct route distribution across nested stacks
- **Preservation**: Explicit grouping, disabled nested stacks, resources without API sections, and mouse/click behavior all remain unchanged
- **`_build_lambda_folder_cache()`**: Method in `api_gateway_stack.py` (~line 457) that reads raw JSON from disk, extracts the `name` field, and maps it to the relative folder path
- **`_discover_routes_from_dependencies()`**: Method in `api_gateway_stack.py` (~line 545) that reads the resolved workload dictionary and produces routes with fully resolved lambda names
- **`_group_routes()`**: Method in `api_gateway_stack.py` (~line 375) that assigns routes to groups using either explicit grouping or auto-grouping by folder
- **`_resolve_lambda_folder()`**: Method in `api_gateway_stack.py` (~line 438) that looks up a lambda name in the folder cache
- **Workload dictionary**: The fully resolved config (`self.workload.dictionary`) where all `{{PLACEHOLDER}}` values have been replaced
- **`route_group`**: A new optional field in Lambda resource config's `api` section that explicitly assigns a route to a named group

## Bug Details

### Bug Condition

The bug manifests when auto-grouping is active (no explicit `nested_stacks.grouping` configured) and Lambda resource configs on disk contain placeholder tokens in their `name` field. The `_build_lambda_folder_cache()` method stores the raw unresolved name as the cache key, but `_discover_routes_from_dependencies()` provides routes with fully resolved names from the workload dictionary. The cache lookup in `_resolve_lambda_folder()` always returns an empty string, routing everything to "default".

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type RouteGroupingInput
  OUTPUT: boolean
  
  RETURN input.nested_stacks_enabled = true
         AND input.nested_stacks_grouping IS EMPTY
         AND EXISTS resource IN input.lambda_resource_configs_on_disk
             WHERE resource.name CONTAINS "{{" AND resource.name CONTAINS "}}"
             AND resource HAS api section
END FUNCTION
```

### Examples

- **Asset handler**: Raw name on disk is `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"`, resolved name in workload dict is `"asset-workbench-dev-asset-handler"`. Cache stores the raw name → lookup with resolved name misses → route goes to "default" instead of "assets" group.
- **Admin handler**: Raw name `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-admin-handler"` vs resolved `"asset-workbench-dev-admin-handler"`. Same cache miss → "default" group instead of "admin" group.
- **Category handler**: Raw name `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-category-handler"` vs resolved `"asset-workbench-dev-category-handler"`. Same cache miss → "default" group instead of "categories" group.
- **Edge case — no placeholders**: If a resource config has a literal name like `"my-lambda"`, the cache already works correctly (no bug condition).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Explicit `nested_stacks.grouping` configured in the API Gateway config must continue to use the explicit grouping map to assign routes to named groups
- When `nested_stacks.enabled` is false or absent, all routes must continue to be created in the main stack without nested stacks
- Lambda resource configs without an `api` section must continue to be skipped during route discovery
- Lambda resources that genuinely cannot be found on disk must still fall back to the "default" group
- Route discovery from `_discover_routes_from_dependencies()` must remain unchanged — it already produces correct resolved names
- The `_group_routes()` explicit grouping path (longest prefix match) must remain unchanged
- All existing property-based tests for `PathOwnershipBuilder` must continue to pass

**Scope:**
All inputs that do NOT involve auto-grouping with placeholder-containing resource configs should be completely unaffected by this fix. This includes:
- Stacks with explicit grouping configured
- Stacks with nested stacks disabled
- Resource configs that already have literal (non-placeholder) names
- The entire route discovery mechanism
- Custom domain setup, SSM exports, and all other API Gateway features

## Hypothesized Root Cause

Based on the bug description, the root cause is:

1. **Placeholder mismatch in cache keys**: `_build_lambda_folder_cache()` reads raw JSON files from disk at `configs/stacks/lambdas/resources/`. The `name` field in these files contains unresolved placeholders like `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"`. These raw values are stored as cache keys.

2. **Resolved names in route discovery**: `_discover_routes_from_dependencies()` reads `self.workload.dictionary`, which is the fully resolved config (generated by `CdkConfig.__resolved_config()` which applies `JsonLoadingUtility.recursive_replace()` with all parameter values). Lambda names in this dictionary are fully resolved like `"asset-workbench-dev-asset-handler"`.

3. **Cache lookup always misses**: When `_resolve_lambda_folder("asset-workbench-dev-asset-handler")` is called, it looks up the resolved name in a cache keyed by unresolved names. The key `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"` never equals `"asset-workbench-dev-asset-handler"`, so the lookup returns `""`.

4. **All routes fall to "default"**: Since every `_resolve_lambda_folder()` call returns `""`, `_group_routes()` assigns every route to the "default" group, creating a single nested stack that exceeds CloudFormation limits.

## Correctness Properties

Property 1: Bug Condition - Resolved Cache Keys Enable Correct Grouping

_For any_ input where auto-grouping is active and Lambda resource configs on disk contain placeholder names, the fixed `_build_lambda_folder_cache()` SHALL resolve those placeholders using available environment variables before storing them as cache keys, such that subsequent lookups with resolved lambda names return the correct relative folder path.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Auto-Grouping Behavior Unchanged

_For any_ input where the bug condition does NOT hold (explicit grouping is configured, nested stacks are disabled, or resource configs have no placeholders), the fixed code SHALL produce exactly the same grouping result as the original code, preserving all existing behavior for explicit grouping, disabled nested stacks, and literal-name configs.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py`

**Function**: `_build_lambda_folder_cache()`

**Specific Changes**:

1. **Resolve placeholders in `name` field**: After reading the `name` from each JSON file, apply placeholder resolution using environment variables from `os.environ`. Build a replacements dictionary from known environment variables (at minimum `{{WORKLOAD_NAME}}` and `{{DEPLOYMENT_NAMESPACE}}`), then use string replacement to resolve the name before storing it as a cache key.

   ```python
   # Build replacements from os.environ (same vars available during CDK synth)
   replacements = {}
   for key, value in os.environ.items():
       replacements[f"{{{{{key}}}}}"] = value
   
   # After reading name from JSON:
   if name:
       for placeholder, value in replacements.items():
           name = name.replace(placeholder, value)
       cache[name] = relative_folder
   ```

2. **Extract `route_group` from `api` section**: While iterating JSON files, also check for an `api.route_group` field. If present, store it alongside the folder path so `_group_routes()` can use it directly.

**Function**: `_group_routes()` (auto-grouping branch)

**Specific Changes**:

3. **Support `route_group` field**: In the auto-grouping branch, before calling `_resolve_lambda_folder()`, check if the route has a `route_group` attribute (populated during discovery). If so, use it directly as the group name, bypassing folder resolution.

**Function**: `_discover_routes_from_dependencies()`

**Specific Changes**:

4. **Propagate `route_group` field**: When building route dicts from discovered resources, include the `route_group` value from the resource's `api` section (if present) so it's available to `_group_routes()`.

5. **Cache the replacements dict**: Build the replacements dictionary once (not per-file) and reuse it across all file reads for performance.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that create mock Lambda resource configs with placeholder names, build the folder cache, and assert that lookups with resolved names succeed. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Single placeholder name test**: Create a resource config with `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-handler"`, build cache, look up `"myapp-dev-handler"` (will fail on unfixed code — returns `""`)
2. **Multiple resources test**: Create several resource configs across different folders, all with placeholder names. Verify cache maps resolved names to correct folders (will fail on unfixed code)
3. **Mixed placeholder and literal test**: Some configs have placeholders, some have literal names. Verify all lookups succeed (will partially fail on unfixed code)
4. **Route grouping end-to-end test**: Build routes with resolved names, call `_group_routes()`, verify routes are distributed across groups (will produce single "default" group on unfixed code)

**Expected Counterexamples**:
- `_build_lambda_folder_cache()` stores `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"` as key
- `_resolve_lambda_folder("asset-workbench-dev-asset-handler")` returns `""` instead of `"assets"`
- All routes end up in `{"default": [all_routes]}` instead of `{"assets": [...], "admin": [...], "categories": [...]}`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  // Set up environment variables for placeholder resolution
  SET os.environ["WORKLOAD_NAME"] = input.workload_name
  SET os.environ["DEPLOYMENT_NAMESPACE"] = input.deployment_namespace
  
  cache := buildLambdaFolderCache_fixed(input.resources_dir)
  
  FOR ALL resource IN input.lambda_resources_on_disk DO
    resolved_name := resolve_placeholders(resource.name, os.environ)
    folder := cache.get(resolved_name)
    ASSERT folder != ""
    ASSERT folder = relative_path_of(resource.json_file, input.resources_dir)
  END FOR
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT groupRoutes_original(input) = groupRoutes_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for explicit grouping and disabled nested stacks, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Explicit grouping preservation**: Generate random route sets with explicit `nested_stacks.grouping` configured. Verify grouping output is identical before and after fix.
2. **Disabled nested stacks preservation**: Generate configs with `nested_stacks.enabled = false`. Verify no nested stacks are created.
3. **Literal name preservation**: Generate resource configs without placeholders. Verify cache behavior is identical.
4. **Default fallback preservation**: Generate lookups for lambda names that don't exist on disk. Verify they still fall to "default" group.

### Unit Tests

- Test `_build_lambda_folder_cache()` with placeholder names + environment variables set → resolved keys in cache
- Test `_build_lambda_folder_cache()` with literal names → literal keys in cache (unchanged behavior)
- Test `_resolve_lambda_folder()` with resolved name → correct folder path
- Test `_group_routes()` auto-grouping with resolved cache → multiple groups
- Test `_group_routes()` with `route_group` field → direct group assignment
- Test edge cases: missing env vars, partial placeholders, nested folder paths

### Property-Based Tests

- Generate random workload names, deployment namespaces, and folder structures. Verify that for any placeholder-bearing config, the resolved cache key matches the name that would appear in the workload dictionary.
- Generate random route sets with explicit grouping configs. Verify that the fix does not alter the grouping output for explicit grouping scenarios.
- Generate random configs where `route_group` is set. Verify the group name equals `route_group` regardless of folder structure.

### Integration Tests

- End-to-end test with a real-world-like config: multiple Lambda resource folders, placeholder names, auto-grouping active. Verify routes are distributed across nested stacks matching folder structure.
- Test with mixed explicit grouping + auto-grouping fallback to ensure both paths coexist correctly.
- Test with `route_group` field on some resources and folder-based resolution on others.
