# Docker Push ECR Config Bugfix Design

## Overview

The `_do_push` function in `docker_build_cli.py` cannot push Docker images to ECR unless `lambda_deployments` is configured, because it derives the ECR account and region exclusively from deployment entries. This couples two independent concerns: where an image is stored (ECR) and which Lambdas consume it. The fix introduces an optional top-level `ecr` field on image configs that directly specifies the push destination, with `lambda_deployments` as a backward-compatible fallback.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when `_do_push` is called with an image config that has no `lambda_deployments` and no `ecr` field
- **Property (P)**: The desired behavior — when an `ecr` field is present, the image is pushed to the specified ECR URI regardless of `lambda_deployments`
- **Preservation**: Existing push behavior via `lambda_deployments` must remain unchanged when no `ecr` field is present
- **`_do_push`**: The function in `docker_build_cli.py` that handles the Docker push action for a single image config
- **`ecr` field**: A new top-level field on image configs specifying `account` and `region` for the ECR push destination
- **`lambda_deployments`**: The existing field that lists Lambda deployment targets, currently used to derive ECR push destination

## Bug Details

### Bug Condition

The bug manifests when `_do_push` is called for an image config that has no `lambda_deployments` entries (empty array or missing field). The function immediately returns with a warning, skipping the push entirely, even though the user has a valid ECR repository to push to.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ImageConfig
  OUTPUT: boolean
  
  RETURN input.ecr IS DEFINED
         AND input.ecr.account IS NOT EMPTY
         AND input.ecr.region IS NOT EMPTY
         AND (input.lambda_deployments IS EMPTY OR input.lambda_deployments IS UNDEFINED)
END FUNCTION
```

Note: The bug condition identifies configs where the user intends to push via the `ecr` field but the current code cannot handle it because it only looks at `lambda_deployments`.

### Examples

- Config with `"ecr": {"account": "072708757319", "region": "us-east-1"}` and no `lambda_deployments` → image is NOT pushed (bug), should be pushed to `072708757319.dkr.ecr.us-east-1.amazonaws.com/repo_name`
- Config with `"ecr": {"account": "072708757319", "region": "us-east-1"}` and `lambda_deployments` present → image should be pushed to the `ecr` destination (ecr takes priority)
- Config with no `ecr` field and valid `lambda_deployments` → image is pushed via deployment entries (existing behavior, should be preserved)
- Config with neither `ecr` nor `lambda_deployments` → warning printed, push skipped (existing behavior, should be preserved)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Configs with `lambda_deployments` and no `ecr` field must continue to derive ECR URI from deployment account/region and push successfully
- ECR authentication via `aws ecr get-login-password` must continue to work the same way
- Tag resolution (version tags, environment tags, CLI tags) must remain unchanged
- The `build` and `tag` actions are completely unaffected by this fix
- The `--tag-version` flag continues to include the computed version as a push tag

**Scope:**
All inputs that do NOT involve the new `ecr` field should be completely unaffected by this fix. This includes:
- Image configs with only `lambda_deployments` (no `ecr` field)
- Image configs with neither field (warning + skip behavior)
- All `build` and `tag` action invocations
- Tag resolution logic
- Version computation logic

## Hypothesized Root Cause

Based on the code analysis, the root cause is straightforward:

1. **Missing ECR field support**: The `_do_push` function only knows how to derive ECR account/region from `lambda_deployments[].account` and `lambda_deployments[].region`. There is no code path to read a top-level `ecr` field.

2. **Early return on empty deployments**: Lines 280-285 check `if not deployments:` and immediately return, preventing any push from occurring. This guard was written assuming `lambda_deployments` is the only source of ECR information.

3. **Tight coupling of concerns**: The function conflates "where to push the image" with "which Lambdas use this image." These should be independent — an image can exist in ECR without any Lambda consuming it.

## Correctness Properties

Property 1: Bug Condition - ECR Field Push

_For any_ image config where an `ecr` field is present with valid `account` and `region` values, the fixed `_do_push` function SHALL construct the ECR URI from `ecr.account` and `ecr.region`, authenticate with ECR, and push the image with the resolved tags, regardless of whether `lambda_deployments` exists.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Lambda Deployments Fallback

_For any_ image config where no `ecr` field is present but valid `lambda_deployments` entries exist, the fixed `_do_push` function SHALL produce exactly the same behavior as the original function, deriving ECR URI from deployment entries and pushing the image identically.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `src/cdk_factory/pipeline/commands/docker_build_cli.py`

**Function**: `_do_push`

**Specific Changes**:

1. **Add ECR field extraction**: At the top of `_do_push`, check for `image_config.get("ecr")` before falling through to `lambda_deployments`.

2. **ECR field priority path**: When `ecr` field is present with valid `account` and `region`:
   - Construct ECR URI: `{ecr.account}.dkr.ecr.{ecr.region}.amazonaws.com/{repo_name}`
   - Resolve tags (same logic as existing code)
   - Authenticate and push (same `execute_push_to_aws` call)
   - Return after successful push (do not also push via `lambda_deployments`)

3. **Fallback to lambda_deployments**: If no `ecr` field is present, fall through to the existing `lambda_deployments` logic unchanged.

4. **Updated warning message**: When neither `ecr` nor `lambda_deployments` is available, update the warning to mention both options.

5. **Validation**: If `ecr` field is present but missing `account` or `region`, print a warning and skip (don't silently fail).

### Pseudocode

```
FUNCTION _do_push(docker, image_config, version, package_name, tags, tag_version, environment)
  repo_name := image_config.get("repo_name", package_name)
  ecr_config := image_config.get("ecr")
  
  IF ecr_config IS NOT NONE THEN
    account := ecr_config.get("account", "")
    region := ecr_config.get("region", "us-east-1")
    
    IF account IS EMPTY THEN
      PRINT warning: "ecr.account is required"
      RETURN
    END IF
    
    ecr_uri := "{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
    all_tags := resolve_tags(tags, tag_version, version, environment)
    qualified_tags := ["{ecr_uri}:{t}" for t in all_tags]
    
    docker.execute_push_to_aws(region, ecr_base_uri, qualified_tags, aws_profile)
    RETURN
  END IF
  
  // Existing lambda_deployments fallback (unchanged)
  deployments := image_config.get("lambda_deployments", [])
  IF NOT deployments THEN
    PRINT warning: "No ecr config or lambda_deployments found"
    RETURN
  END IF
  
  // ... existing deployment loop unchanged ...
END FUNCTION
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that the current code skips push when `ecr` field is present but no `lambda_deployments` exist.

**Test Plan**: Write tests that call `_do_push` with image configs containing an `ecr` field but no `lambda_deployments`. Run these tests on the UNFIXED code to observe the warning/skip behavior.

**Test Cases**:
1. **ECR field only**: Config with `ecr: {account, region}` and no `lambda_deployments` → push is skipped (will fail on unfixed code because push doesn't happen)
2. **ECR field with empty deployments**: Config with `ecr` and `lambda_deployments: []` → push is skipped (will fail on unfixed code)
3. **ECR field with disabled deployments**: Config with `ecr` and all deployments disabled → push is skipped (will fail on unfixed code)

**Expected Counterexamples**:
- `_do_push` returns early with warning when `lambda_deployments` is empty, ignoring the `ecr` field entirely
- The `ecr` field is never read by the current implementation

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function pushes to the ECR URI derived from the `ecr` field.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := _do_push_fixed(input)
  ASSERT image_pushed_to(ecr_uri_from(input.ecr))
  ASSERT tags_applied_correctly(result)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (no `ecr` field, valid `lambda_deployments`), the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT _do_push_original(input) = _do_push_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of deployment configs automatically
- It catches edge cases in tag resolution that manual tests might miss
- It provides strong guarantees that the fallback path is unchanged

**Test Plan**: Observe behavior on UNFIXED code first for configs with `lambda_deployments` (no `ecr` field), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Single deployment preservation**: Config with one enabled deployment → same ECR URI, same tags
2. **Multiple deployments preservation**: Config with multiple deployments → each pushed correctly
3. **Tag resolution preservation**: Version tags, environment tags, CLI tags all resolve identically
4. **Disabled deployment preservation**: Disabled entries are still skipped

### Unit Tests

- Test `_do_push` with `ecr` field only (no `lambda_deployments`)
- Test `_do_push` with `ecr` field taking priority over `lambda_deployments`
- Test `_do_push` with `ecr` field missing `account` (validation error)
- Test `_do_push` fallback to `lambda_deployments` when no `ecr` field
- Test `_do_push` with neither field (warning + skip)

### Property-Based Tests

- Generate random valid `ecr` configs and verify push is attempted with correct URI
- Generate random `lambda_deployments` configs (no `ecr` field) and verify behavior matches original
- Generate random tag combinations and verify tag resolution is consistent across both paths

### Integration Tests

- End-to-end test: build → tag → push with `ecr` field config
- End-to-end test: build → tag → push with `lambda_deployments` config (regression)
- Test with real `docker-images.json` format containing `ecr` field
