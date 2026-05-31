# Implementation Plan

## Overview
Fix the `_do_push` function in `docker_build_cli.py` to support a top-level `ecr` field in `docker-images.json` for specifying the ECR push destination independently of `lambda_deployments`.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - ECR Field Push Ignored
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases: image config with `ecr: {account: "072708757319", region: "us-east-1"}` and no `lambda_deployments`
  - Test that `_do_push` with an `ecr` field and no `lambda_deployments` results in a push to `{ecr.account}.dkr.ecr.{ecr.region}.amazonaws.com/{repo_name}` (from Bug Condition in design)
  - Mock `DockerUtilities.execute_push_to_aws` and assert it is called with the correct ECR URI derived from the `ecr` field
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (the mock is never called because `_do_push` returns early with a warning)
  - Document counterexamples found: `_do_push` prints warning and returns without calling `execute_push_to_aws`
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 2.1_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Lambda Deployments Fallback Behavior
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `_do_push` with `lambda_deployments: [{account: "013453151395", region: "us-east-1", enabled: true}]` and no `ecr` field calls `execute_push_to_aws` with URI `013453151395.dkr.ecr.us-east-1.amazonaws.com` on unfixed code
  - Observe: `_do_push` with `lambda_deployments: [{enabled: false}]` and no `ecr` field skips that deployment on unfixed code
  - Observe: tag resolution produces version + environment + latest tags correctly on unfixed code
  - Write property-based test: for all valid `lambda_deployments` configs (no `ecr` field), `_do_push` calls `execute_push_to_aws` with ECR URI derived from deployment account/region (from Preservation Requirements in design)
  - Write property-based test: for all tag combinations (version, environment, CLI tags), tag resolution produces the same output
  - Verify tests pass on UNFIXED code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix: Add ECR field support to `_do_push`

  - [x] 3.1 Implement the fix
    - At the top of `_do_push`, extract `ecr_config = image_config.get("ecr")`
    - If `ecr_config` is present and has a non-empty `account`:
      - Extract `account` and `region` (default `"us-east-1"`)
      - Construct `ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"`
      - Resolve tags using the same logic as existing code (version, environment, CLI tags)
      - Build qualified tags: `[f"{ecr_uri}:{t}" for t in all_tags]`
      - Call `docker.execute_push_to_aws(aws_region=region, aws_ecr_uri=f"{account}.dkr.ecr.{region}.amazonaws.com", tags=qualified_tags, aws_profile=aws_profile)`
      - Return (do not fall through to `lambda_deployments` path)
    - If `ecr_config` is present but `account` is empty, print validation warning and return
    - If `ecr_config` is not present, fall through to existing `lambda_deployments` logic unchanged
    - Update the "no deployments" warning message to mention both `ecr` and `lambda_deployments`
    - _Bug_Condition: isBugCondition(input) where input.ecr is defined and input.lambda_deployments is empty_
    - _Expected_Behavior: push to ECR URI derived from ecr.account and ecr.region_
    - _Preservation: lambda_deployments fallback path unchanged when ecr field absent_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - ECR Field Push Works
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (push via `ecr` field)
    - When this test passes, it confirms the `ecr` field is read and used for push
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Lambda Deployments Fallback Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions to `lambda_deployments` path)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to confirm no regressions
  - Verify both the `ecr` field path and `lambda_deployments` fallback path work correctly
  - Ensure all tests pass, ask the user if questions arise

## Notes
- The fix is in the cdk-factory repo: `src/cdk_factory/pipeline/commands/docker_build_cli.py`
- The consumer config is in asset-workbench-services: `docker-images.json`
- Must be backward compatible with existing `lambda_deployments` configs

## Task Dependency Graph
```json
{
  "waves": [
    {"tasks": ["1", "2"]},
    {"tasks": ["3.1"]},
    {"tasks": ["3.2", "3.3"]},
    {"tasks": ["4"]}
  ]
}
```
