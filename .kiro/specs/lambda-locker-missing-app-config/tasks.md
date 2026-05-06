# Implementation Plan

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Scanning From resources/ Misses Stack-Level Docker Lambdas
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate scanning from `lambdas/resources/` misses stack-level files in `lambdas/`
  - **Scoped PBT Approach**: Create a temp directory mimicking the real layout: a parent `lambdas/` dir containing `lambda-app-settings.json` (stack-level file with a `resources` array including `app-configurations` Docker lambda) and a `resources/` subdirectory with individual resource files. Scope the property to this concrete structure.
  - **Test file**: `cdk-factory/tests/unit/test_docker_version_locker.py` — add a new test class `TestBugConditionExploration`
  - **Test logic**:
    - Build temp dir: `lambdas/lambda-app-settings.json` with `{"name": "lambda-app-settings", "resources": [{"name": "app-configurations", "docker": {"image": true}, "ecr": {"name": "acme-systems/v3/acme-saas-core-services"}}]}`
    - Build temp dir: `lambdas/resources/tenants/get-tenant.json` with a valid individual Docker lambda
    - Call `scan_config_directory(str(tmp_path / "lambdas" / "resources"))` — simulating the bug condition (CONFIG_DIR points to subdirectory)
    - Assert `"app-configurations"` IS in the discovered names (this is the expected behavior)
    - Run on UNFIXED code — expect FAILURE because scanning from `resources/` never reaches the parent `lambdas/` directory
  - Document counterexamples: `scan_config_directory("lambdas/resources/")` returns entries from subdirectories but NOT `app-configurations` from `lambda-app-settings.json`
  - _Requirements: 1.1, 1.3, 2.3_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Parent Directory Scan Is Superset of Subdirectory Scan
  - **IMPORTANT**: Follow observation-first methodology
  - **Test file**: `cdk-factory/tests/unit/test_docker_version_locker.py` — add a new test class `TestPreservationProperty`
  - **Observation step**: On UNFIXED code, call `scan_config_directory()` on both a parent directory and its `resources/` subdirectory, observe that the parent result is always a superset of the subdirectory result
  - **Property-based test using Hypothesis**:
    - Generate random directory trees with `@given(...)` strategies producing varying numbers of:
      - Individual Docker lambda JSON files in `resources/` subdirectories (with random valid `name`, `ecr.name`, `docker.image=true`)
      - Stack-level JSON files in the parent directory (with `resources` arrays containing mixes of Docker and non-Docker entries)
      - Non-Docker JSON files (no `docker.image` or `docker.image=false`) scattered at both levels
      - Invalid JSON files and non-JSON files at both levels
    - For each generated tree, assert: `set(names from scan(parent)) ⊇ set(names from scan(parent/resources/))`
    - This property holds on UNFIXED code because `os.walk` is recursive — scanning from parent always includes subdirectory results
  - **Additional deterministic preservation tests**:
    - Observe: `scan_config_directory("lambdas/resources/")` finds `get-tenant` → verify same entry found when scanning from `lambdas/`
    - Observe: non-Docker files are skipped at both levels
    - Observe: stack-level files with mixed Docker/non-Docker resources extract only Docker entries
  - Verify all tests PASS on UNFIXED code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix CONFIG_DIR in run-lock-versions.sh

  - [ ] 3.1 Change CONFIG_DIR from resources/ to lambdas/
    - In `Acme-SaaS-IaC/cdk/commands/run-lock-versions.sh`, change line:
    - FROM: `CONFIG_DIR="${CDK_DIR}/configs/stacks/lambdas/resources"`
    - TO: `CONFIG_DIR="${CDK_DIR}/configs/stacks/lambdas"`
    - This is the only change required — no Python code modifications needed
    - _Bug_Condition: isBugCondition(input) where CONFIG_DIR = "${CDK_DIR}/configs/stacks/lambdas/resources" AND mode IN {--seed, --list}_
    - _Expected_Behavior: CONFIG_DIR = "${CDK_DIR}/configs/stacks/lambdas" so scan_config_directory() discovers stack-level Docker lambdas including app-configurations_
    - _Preservation: All Docker lambdas under resources/ subdirectories continue to be discovered via recursive os.walk from parent directory_
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Stack-Level Docker Lambdas Discovered
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 asserts `app-configurations` is discovered when scanning from the correct parent directory
    - Since the fix changes CONFIG_DIR to point to `lambdas/` (parent), the test scenario now correctly represents the fixed behavior
    - Update the exploration test to call `scan_config_directory(str(tmp_path / "lambdas"))` instead of `scan_config_directory(str(tmp_path / "lambdas" / "resources"))` to reflect the fixed CONFIG_DIR path
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — `app-configurations` is now discovered)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Parent Directory Scan Is Superset of Subdirectory Scan
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — all previously discovered lambdas still found)
    - Confirm all tests still pass after fix (no regressions)

- [ ] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `source cdk-factory/.venv/bin/activate && python -m pytest cdk-factory/tests/unit/test_docker_version_locker.py -v`
  - Ensure all existing tests plus new bug condition and preservation tests pass
  - Verify no regressions in any other test classes
  - Ask the user if questions arise
