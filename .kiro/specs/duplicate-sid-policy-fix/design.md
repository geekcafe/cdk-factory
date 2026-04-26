# Duplicate SID Policy Fix — Bugfix Design

## Overview

The `_get_structured_permission()` method in `policy_docs.py` generates IAM policy Statement IDs (SIDs) by stripping dashes/underscores from resource names and truncating to 20 characters. When a lambda references multiple resources (DynamoDB tables, S3 buckets, or SSM paths) whose names share a long common prefix, the truncated slugs collide, producing duplicate SIDs. CloudFormation rejects the resulting policy with "Statement IDs (SID) in a single policy must be unique."

The fix will replace the naive truncation with a hash-based suffix approach that guarantees uniqueness while keeping SIDs human-readable and valid (alphanumeric only).

## Glossary

- **Bug_Condition (C)**: Two or more structured permissions in the same lambda produce identical SIDs because their resource name slugs collide after 20-character truncation
- **Property (P)**: Every structured permission in a lambda's permission list produces a unique, valid IAM SID
- **Preservation**: Existing behavior for single-resource lambdas, already-unique slugs, string permissions, and inline IAM dicts must remain unchanged
- **`_get_structured_permission()`**: The method in `policy_docs.py` that converts structured permission dicts (e.g., `{"dynamodb": "read", "table": "..."}`) into IAM policy statement details including SID generation
- **Slug**: The alphanumeric-only, truncated form of a resource name used as a SID suffix (e.g., `v3acmesaasalpha` from `v3-acme-saas-alpha-app-database`)
- **SID**: IAM Statement ID — must be alphanumeric and unique within a single policy document

## Bug Details

### Bug Condition

The bug manifests when a lambda has multiple structured permissions whose resource names, after slug transformation (stripping dashes, underscores, slashes, and asterisks), share the same first 20 characters. The `_get_structured_permission()` method truncates the slug to 20 characters, so any distinguishing characters beyond position 20 are lost.

**Formal Specification:**
```
FUNCTION isBugCondition(permissions)
  INPUT: permissions — list of structured permission dicts for a single lambda
  OUTPUT: boolean

  slugs := []
  FOR EACH perm IN permissions DO
    IF perm has "dynamodb" key THEN
      resource := perm["table"]
      slug := remove_dashes_underscores(resource)[:20]
      sid := action_prefix(perm["dynamodb"]) + slug
    ELSE IF perm has "s3" key THEN
      resource := perm["bucket"]
      slug := remove_dashes_underscores(resource)[:20]
      sid := action_prefix(perm["s3"]) + slug
    ELSE IF perm has "parameter_store" key THEN
      resource := perm["path"]
      slug := remove_slashes_dashes_asterisks(resource)[:20]
      sid := action_prefix(perm["parameter_store"]) + slug
    ELSE
      CONTINUE
    END IF
    IF sid IN slugs THEN RETURN true
    slugs.append(sid)
  END FOR
  RETURN false
END FUNCTION
```

### Examples

- **DynamoDB collision (real-world)**: Tables `v3-acme-saas-alpha-app-database` and `v3-acme-saas-alpha-audit-logger-database` both produce slug `v3acmesaasalphaa`. With `"dynamodb": "read"`, both generate SID `DynamoDbReadv3acmesaasalphaa` → duplicate SID error.

- **DynamoDB collision (same action, different tables)**: Tables `v3-acme-saas-alpha-app-database` and `v3-acme-saas-alpha-transient-database` both produce slug `v3acmesaasalphaa`. Read permissions on both → `DynamoDbReadv3acmesaasalphaa` appears twice.

- **S3 collision**: Buckets `v3-acme-saas-alpha-user-files` and `v3-acme-saas-alpha-analysis-upload-files` both produce slug `v3acmesaasalphau`. Read permissions on both → `S3Readv3acmesaasalphau` appears twice.

- **No collision (short names)**: Tables `users-table` and `orders-table` produce slugs `userstable` and `orderstable` — unique within 20 chars, no bug.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Single-resource structured permissions must continue to generate valid SIDs and policy statements
- Resources whose slugs are already unique within 20 characters must continue to produce the same SIDs as before (backward compatibility)
- String-based permissions (`cognito_admin`, `parameter_store_read`, etc.) must return identical permission dicts
- Inline IAM dict permissions (with explicit `actions`/`resources` keys) must return identical permission dicts
- All generated SIDs must remain valid IAM SID values (alphanumeric characters only, matching `[A-Za-z0-9]+`)
- The structure of returned permission dicts (keys: `name`, `description`, `sid`, `actions`, `resources`, `nag`) must remain unchanged

**Scope:**
All inputs that do NOT involve multiple structured permissions with colliding 20-character slugs should be completely unaffected by this fix. This includes:
- Any lambda with only one structured permission per resource type/action combination
- Any lambda with structured permissions whose resource names differ within the first 20 slug characters
- All string-based and inline IAM dict permissions
- The `_dynamodb_permissions()`, `__s3_read_permissions()`, `__s3_write_permissions()`, `__s3_delete_permissions()` helper methods (they receive the SID as a parameter)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is clear and singular:

1. **Naive Truncation of Resource Name Slugs**: The slug generation in `_get_structured_permission()` uses a fixed 20-character truncation after stripping separator characters. This appears in three places:
   - Line 369: `table_slug = table.replace("-", "").replace("_", "")[:20]` (DynamoDB)
   - Line 387: `bucket_slug = bucket.replace("-", "").replace("_", "")[:20]` (S3)
   - Line 417: `path_slug = path.replace("/", "").replace("-", "").replace("*", "All")[:20]` (SSM)

2. **Real-World Name Patterns Exceed 20 Characters**: The deployment configs use naming patterns like `v3-{{WORKLOAD_NAME}}-{{TENANT_NAME}}-<resource-specific-suffix>`. After template resolution (e.g., `v3-acme-saas-alpha-app-database`), the common prefix `v3acmesaasalpha` is already 19 characters, leaving only 1 character to differentiate resources. Since both `app-database` and `audit-logger-database` start with `a`, the 20th character is identical.

3. **No Collision Detection or Avoidance**: The method processes each permission independently with no awareness of other permissions in the same policy. There is no mechanism to detect or resolve SID collisions.

## Correctness Properties

Property 1: Bug Condition — Unique SIDs for Colliding Slugs

_For any_ set of distinct resource names (DynamoDB tables, S3 buckets, or SSM paths) where the current 20-character truncation produces identical slugs, the fixed slug generation function SHALL produce distinct SID suffixes for each resource name, ensuring no two permissions in the same policy share a SID.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — SID Validity and Non-Colliding Behavior

_For any_ resource name input, the fixed slug generation function SHALL produce a SID that is a valid IAM SID value (alphanumeric characters only, matching `[A-Za-z0-9]+`), and for resource names whose slugs are already unique within 20 characters, the function SHALL preserve backward-compatible SID generation.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.8**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `cdk-factory/src/cdk_factory/constructs/lambdas/policies/policy_docs.py`

**Function**: `_get_structured_permission()`

**Specific Changes**:

1. **Extract a shared `_make_sid_slug()` helper method**: Create a new private method that encapsulates the slug generation logic. This centralizes the fix and eliminates the three separate truncation sites.

2. **Replace truncation with hash-based suffix**: Instead of `slug[:20]`, use a scheme that takes a prefix of the cleaned name (e.g., 12 characters) and appends a short hash (e.g., 8 hex characters from a deterministic hash of the full cleaned name). This guarantees uniqueness for distinct inputs while keeping SIDs readable.
   - Example: `v3-acme-saas-alpha-app-database` → `v3acmesa` + `a1b2c3d4` → `v3acmesaa1b2c3d4`
   - Example: `v3-acme-saas-alpha-audit-logger-database` → `v3acmesa` + `e5f6a7b8` → `v3acmesae5f6a7b8`

3. **Ensure alphanumeric output**: The hash must use only alphanumeric characters (hex digits `[0-9a-f]` satisfy this). The total slug length should remain ≤ 20 characters to avoid excessively long SIDs.

4. **Update DynamoDB slug generation** (line 369): Replace `table.replace("-", "").replace("_", "")[:20]` with call to `_make_sid_slug(table)`.

5. **Update S3 slug generation** (line 387): Replace `bucket.replace("-", "").replace("_", "")[:20]` with call to `_make_sid_slug(bucket)`.

6. **Update SSM slug generation** (line 417): Replace `path.replace("/", "").replace("-", "").replace("*", "All")[:20]` with call to `_make_sid_slug(path)`, where the helper handles the SSM-specific character stripping.

### Proposed `_make_sid_slug()` Implementation

```python
import hashlib

def _make_sid_slug(self, resource_name: str, extra_strip: dict | None = None) -> str:
    """Generate a unique, alphanumeric SID slug from a resource name.
    
    Uses a prefix + hash approach to guarantee uniqueness while maintaining readability.
    """
    # Strip non-alphanumeric characters
    cleaned = resource_name.replace("-", "").replace("_", "")
    if extra_strip:
        for char, replacement in extra_strip.items():
            cleaned = cleaned.replace(char, replacement)
    
    # Short hash of the full cleaned name for uniqueness
    hash_suffix = hashlib.md5(cleaned.encode()).hexdigest()[:8]
    
    # Prefix (12 chars) + hash (8 chars) = 20 chars total
    prefix = cleaned[:12]
    return f"{prefix}{hash_suffix}"
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `_get_structured_permission()` with pairs of resource names known to collide under the current 20-character truncation. Run these tests on the UNFIXED code to observe the duplicate SIDs.

**Test Cases**:
1. **DynamoDB Read Collision**: Call with `{"dynamodb": "read", "table": "v3-acme-saas-alpha-app-database"}` and `{"dynamodb": "read", "table": "v3-acme-saas-alpha-audit-logger-database"}` — verify SIDs are identical (will fail uniqueness on unfixed code)
2. **DynamoDB Mixed Action Collision**: Call with `{"dynamodb": "read", "table": "v3-acme-saas-alpha-app-database"}` and `{"dynamodb": "read", "table": "v3-acme-saas-alpha-transient-database"}` — verify SIDs collide (will fail on unfixed code)
3. **S3 Bucket Collision**: Call with two buckets sharing a long prefix — verify SIDs collide (will fail on unfixed code)
4. **SSM Path Collision**: Call with two SSM paths sharing a long prefix — verify SIDs collide (will fail on unfixed code)

**Expected Counterexamples**:
- SIDs are identical for distinct resource names because the slug truncation discards the differentiating suffix
- Root cause confirmed: the `[:20]` truncation is the sole source of collision

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces unique SIDs.

**Pseudocode:**
```
FOR ALL (name_a, name_b) WHERE name_a != name_b DO
  slug_a := make_sid_slug(name_a)
  slug_b := make_sid_slug(name_b)
  ASSERT slug_a != slug_b
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces valid SIDs and the overall permission dict structure is unchanged.

**Pseudocode:**
```
FOR ALL resource_name DO
  slug := make_sid_slug(resource_name)
  ASSERT slug matches [A-Za-z0-9]+
  ASSERT len(slug) > 0
  ASSERT len(slug) <= 20
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many resource name strings automatically across the input domain
- It catches edge cases that manual unit tests might miss (empty strings, very long names, special characters)
- It provides strong guarantees that SID validity is maintained for all inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-colliding resource names, then write property-based tests capturing that behavior.

**Test Cases**:
1. **SID Validity Preservation**: For any generated slug, verify it matches `[A-Za-z0-9]+` — alphanumeric only
2. **Single Resource Preservation**: Verify single-table/bucket/path permissions still generate valid policy dicts with all expected keys
3. **String Permission Preservation**: Verify `cognito_admin`, `parameter_store_read`, etc. return identical dicts
4. **Inline IAM Preservation**: Verify inline dicts with `actions`/`resources` keys return identical dicts

### Unit Tests

- Test `_make_sid_slug()` with known colliding pairs to verify distinct outputs
- Test `_make_sid_slug()` with short names that don't collide to verify reasonable output
- Test `_make_sid_slug()` with edge cases: empty-ish names, single character, very long names
- Test `_get_structured_permission()` end-to-end with colliding DynamoDB table names
- Test `_get_structured_permission()` end-to-end with colliding S3 bucket names
- Test `_get_structured_permission()` end-to-end with colliding SSM paths
- Test that string-based permissions are unaffected
- Test that inline IAM dict permissions are unaffected

### Property-Based Tests

- Generate random pairs of distinct resource names and verify `_make_sid_slug()` produces distinct slugs (fix checking)
- Generate random resource names and verify all slugs are alphanumeric and non-empty (preservation)
- Generate random resource names and verify slug length is bounded (≤ 20 characters)
- Generate lists of distinct resource names and verify all slugs in the list are unique (batch uniqueness)

### Integration Tests

- Test full `generate_and_bind_lambda_policy_docs()` flow with a lambda config containing multiple DynamoDB tables with colliding prefixes
- Test full flow with mixed resource types (DynamoDB + S3 + SSM) all with colliding prefixes
- Test that CDK synth succeeds for a lambda with the real-world table names from `deployment.alpha.json`
