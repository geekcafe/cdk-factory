# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Chained Placeholder Values Remain Unresolved
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate chained references are not resolved
  - **Scoped PBT Approach**: Scope the property to concrete chained reference cases that mirror real config patterns
  - **Test file**: `cdk-factory/tests/unit/test_chained_placeholder_resolution.py`
  - **Test class**: `TestBugConditionChainedPlaceholdersUnresolved`
  - Write a hypothesis strategy that generates replacements dicts where at least one value contains a `{{PLACEHOLDER}}` token matching another key in the dict (the bug condition from `isBugCondition` in design)
  - Property-based test: for any such chained replacements dict, after calling `recursive_replace(config, replacements)` on a config containing those placeholders, assert that all `{{...}}` tokens referencing keys in the replacements dict are fully resolved in the output (this will FAIL on unfixed code because `__resolved_config` has no pre-resolution step)
  - Concrete test case 1: `{{TARGET_ACCOUNT_ROLE_ARN}}` with value `"arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole"` where `{{AWS_ACCOUNT}}` → `"959096737760"`. Assert the output contains `"959096737760"` not literal `"{{AWS_ACCOUNT}}"`
  - Concrete test case 2: `{{TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME}}` with value `"/acme-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id"` where `{{DEPLOYMENT_NAMESPACE}}` → `"beta"`. Assert the output contains `"/acme-saas/beta/route53/hosted-zone-id"`
  - Concrete test case 3: Three-level chain `{{A}}` → `"prefix-{{B}}"`, `{{B}}` → `"mid-{{C}}"`, `{{C}}` → `"leaf"`. Assert final value of `{{A}}` is `"prefix-mid-leaf"`
  - Run test on UNFIXED code: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_chained_placeholder_resolution.py::TestBugConditionChainedPlaceholdersUnresolved -v`
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists because `recursive_replace` does a single pass and replacement values are never resolved against each other)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Chained Replacements Produce Identical Results
  - **IMPORTANT**: Follow observation-first methodology
  - **Test file**: `cdk-factory/tests/unit/test_chained_placeholder_resolution.py`
  - **Test class**: `TestPreservationNonChainedReplacements`
  - Observe on UNFIXED code: `recursive_replace({"name": "{{workload-name}}", "env": "{{env}}"}, {"{{workload-name}}": "myapp", "{{env}}": "prod"})` returns `{"name": "myapp", "env": "prod"}`
  - Observe on UNFIXED code: `recursive_replace(config, {})` returns config unchanged
  - Observe on UNFIXED code: `recursive_replace({"nested": {"key": "{{val}}"}}, {"{{val}}": "resolved"})` returns `{"nested": {"key": "resolved"}}`
  - Write hypothesis strategy that generates replacements dicts where NO value contains any key from the dict (the negation of `isBugCondition` — these are non-chained replacements)
  - Write hypothesis strategy that generates nested config structures (dicts, lists, strings) containing placeholder tokens from the generated replacements
  - Property-based test: for any non-chained replacements dict and config, `recursive_replace(config, replacements)` produces the same output before and after the fix (pre-resolution is a no-op when no values contain chained refs)
  - Concrete preservation test: empty replacements dict returns config unchanged
  - Concrete preservation test: simple literal replacements (no inner placeholders) resolve identically
  - Concrete preservation test: replacements where values contain `{{` but no matching key in the dict are left as-is (e.g., `{{UNKNOWN}}` in a value when `{{UNKNOWN}}` is not a key)
  - Run tests on UNFIXED code: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_chained_placeholder_resolution.py::TestPreservationNonChainedReplacements -v`
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.5_

- [x] 3. Fix for chained placeholder resolution in `__resolved_config()`

  - [x] 3.1 Implement the fix in `cdk_config.py`
    - Add a multi-pass pre-resolution loop in `CdkConfig.__resolved_config()` after the `for parameter in parameters:` loop builds the `replacements` dict and BEFORE the `if replacements:` block that calls `recursive_replace()`
    - The loop iterates up to 5 times (matching the proven pattern in `deploy.py`), resolving chained references within replacement values themselves
    - On each pass, for each `(key, value)` in `replacements` where `value` is a string containing `{{`, substitute all other replacement keys found in that value
    - Track whether any value changed; if no changes occurred, break early (makes it a no-op for non-chained configs)
    - The `range(5)` limit prevents infinite loops from circular references (e.g., `{{A}}` → `"{{B}}"`, `{{B}}` → `"{{A}}"`)
    - Add `isinstance(value, str)` and `isinstance(replace_str, str)` type guards for safety
    - Do NOT modify `recursive_replace()` in `json_loading_utility.py` — it is a general-purpose utility
    - _Bug_Condition: isBugCondition(replacements) where any replacement value contains a `{{PLACEHOLDER}}` token matching another key in the dict_
    - _Expected_Behavior: After pre-resolution, every replacement value is fully resolved — no value contains any placeholder key from the dict_
    - _Preservation: Non-chained replacement values, file inheritance resolution, skipped-section behavior, and empty-replacements behavior remain unchanged_
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Chained Placeholder Values Are Fully Resolved
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (all chained refs fully resolved)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_chained_placeholder_resolution.py::TestBugConditionChainedPlaceholdersUnresolved -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — chained placeholders are now fully resolved)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Chained Replacements Produce Identical Results
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_chained_placeholder_resolution.py::TestPreservationNonChainedReplacements -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — non-chained behavior is unchanged)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_chained_placeholder_resolution.py -v`
  - Ensure all tests pass, ask the user if questions arise.
