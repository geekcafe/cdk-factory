# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Placeholder Cache Keys Cause Lookup Misses
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where Lambda resource configs on disk contain `{{WORKLOAD_NAME}}` and `{{DEPLOYMENT_NAMESPACE}}` placeholder tokens in the `name` field
  - Create a temporary directory structure mimicking `configs/stacks/lambdas/resources/` with subdirectories (e.g., `assets/`, `admin/`, `categories/`)
  - Write JSON files with placeholder names like `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"` in each subdirectory
  - Set `os.environ["WORKLOAD_NAME"]` and `os.environ["DEPLOYMENT_NAMESPACE"]` to known values (e.g., `"asset-workbench"` and `"dev"`)
  - Call `_build_lambda_folder_cache()` and then `_resolve_lambda_folder("asset-workbench-dev-asset-handler")`
  - Assert the result equals the relative folder path (e.g., `"assets"`) — NOT empty string
  - Also test end-to-end: build routes with resolved names, call `_group_routes()` with auto-grouping (no explicit grouping), assert routes are distributed across multiple groups (not all in "default")
  - Use Hypothesis to generate various workload names and deployment namespaces, asserting that for any combination, the resolved cache key matches what `_discover_routes_from_dependencies()` would produce
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists: cache stores raw `"{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler"` but lookup uses resolved `"asset-workbench-dev-asset-handler"`)
  - Document counterexamples found (e.g., `_resolve_lambda_folder("asset-workbench-dev-asset-handler")` returns `""` instead of `"assets"`)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Auto-Grouping Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for the following non-buggy inputs:
  - Observe: When explicit `nested_stacks.grouping` is configured, `_group_routes()` uses the explicit grouping map with longest prefix match (routes assigned to named groups)
  - Observe: When `nested_stacks.enabled` is false, no nested stacks are created and all routes remain in main stack
  - Observe: Lambda resource configs without an `api` section are skipped during route discovery
  - Observe: Lambda resource configs with literal (non-placeholder) names in the `name` field produce correct cache entries that can be looked up successfully
  - Observe: Lambdas that genuinely cannot be found on disk still fall back to the "default" group
  - Write property-based tests with Hypothesis that generate:
    - Random route sets with explicit `nested_stacks.grouping` configs — verify grouping output uses explicit map with longest prefix match
    - Random configs with `nested_stacks.enabled = false` — verify no grouping occurs
    - Random resource configs with literal (no-placeholder) names — verify cache stores literal names correctly and lookups succeed
    - Random lookups for lambda names not on disk — verify they return empty string (triggering "default" group)
  - Verify tests PASS on UNFIXED code (these test non-buggy code paths that must be preserved)
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for placeholder mismatch in lambda folder cache and route_group field support

  - [x] 3.1 Implement placeholder resolution in `_build_lambda_folder_cache()`
    - In `src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py`, modify `_build_lambda_folder_cache()`
    - Build a replacements dictionary once from `os.environ` before iterating files: `replacements = {f"{{{{{key}}}}}": value for key, value in os.environ.items()}`
    - After reading the `name` field from each JSON file, resolve placeholders by iterating `replacements` and calling `name = name.replace(placeholder, value)`
    - Store the resolved name as the cache key
    - _Bug_Condition: isBugCondition(input) where input.nested_stacks_enabled = true AND input.nested_stacks_grouping IS EMPTY AND resource configs contain placeholder tokens_
    - _Expected_Behavior: cache.get(resolved_name) returns relative_folder_path, not empty string_
    - _Preservation: Literal names without placeholders are stored unchanged (same as before)_
    - _Requirements: 2.1, 2.2, 2.3, 3.4_

  - [x] 3.2 Add `route_group` field extraction in `_build_lambda_folder_cache()` and propagation
    - While iterating JSON files in `_build_lambda_folder_cache()`, also read `config.get("api", {}).get("route_group")` if present
    - Store route_group info in a separate cache (e.g., `self._lambda_route_group_cache`) mapping resolved lambda name to route_group value
    - In `_discover_routes_from_dependencies()`, when building route dicts, include `"route_group": api_config.get("route_group")` in the route dict if the field is present
    - In `_group_routes()` auto-grouping branch, before calling `_resolve_lambda_folder()`, check if the route has a `route_group` key and use it directly as the group name if present
    - _Bug_Condition: N/A (enhancement)_
    - _Expected_Behavior: route_group field bypasses folder resolution and directly assigns the route to the named group_
    - _Preservation: Routes without route_group continue to use folder-based resolution_
    - _Requirements: 3.5, 2.3_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Placeholder Cache Keys Enable Correct Grouping
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (resolved names map to correct folders)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — cache now resolves placeholders before storing keys)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Auto-Grouping Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — explicit grouping, disabled nested stacks, literal names, and default fallback all unchanged)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite: `python -m pytest tests/ -v`
  - Ensure all existing tests pass including `test_api_gateway_group_routes.py`, `test_path_ownership_builder.py`, and the property-based tests in `tests/properties/`
  - Ensure the new bug condition exploration test (task 1) now PASSES
  - Ensure the new preservation tests (task 2) still PASS
  - Ensure no other tests have been broken by the fix
  - Ask the user if questions arise


