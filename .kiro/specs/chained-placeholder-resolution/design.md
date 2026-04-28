# Chained Placeholder Resolution Bugfix Design

## Overview

The `CdkConfig.__resolved_config()` method builds a `replacements` dictionary from `cdk.parameters` and passes it to `JsonLoadingUtility.recursive_replace()` to substitute `{{PLACEHOLDER}}` tokens throughout the config. When a parameter's `value` itself contains a reference to another parameter (a chained reference), the replacement values are applied as-is — meaning inner placeholders like `{{AWS_ACCOUNT}}` inside `TARGET_ACCOUNT_ROLE_ARN`'s value are never resolved. The fix adds a multi-pass pre-resolution step on the replacement dictionary values before they are applied to the config, mirroring the proven pattern already used in `acme-SaaS-IaC/cdk/deploy.py::_resolve_deployment_placeholders`.

## Glossary

- **Bug_Condition (C)**: A replacement value in the `replacements` dict contains a `{{PLACEHOLDER}}` token that matches another key in the same dict (a chained reference)
- **Property (P)**: After pre-resolution, every replacement value is fully resolved — no value contains any placeholder key from the dict
- **Preservation**: All non-chained replacement values, file inheritance resolution, skipped-section behavior, and empty-replacements behavior remain unchanged
- **`__resolved_config()`**: The method in `cdk_config.py` that builds the replacements dict and calls `recursive_replace()` on the loaded config
- **`recursive_replace()`**: The static method in `json_loading_utility.py` that performs find-and-replace across all string values and keys in a nested dict/list structure
- **Chained reference**: A parameter whose `value` contains `{{ANOTHER_PARAM}}` — requiring transitive resolution
- **Pre-resolution**: The multi-pass loop that resolves chained references within the replacements dict itself, before applying it to the config

## Bug Details

### Bug Condition

The bug manifests when a parameter's `value` field in `cdk.parameters` contains a `{{PLACEHOLDER}}` token that references another parameter in the same list. The `__resolved_config()` method builds the replacements dict in iteration order and passes it directly to `recursive_replace()`, which performs a single pass over the config. Since the replacement values themselves are never resolved against each other, inner placeholders remain as literal strings.

**Formal Specification:**
```
FUNCTION isBugCondition(replacements)
  INPUT: replacements of type Dict[str, str]
  OUTPUT: boolean

  FOR EACH (placeholder, value) IN replacements:
    IF isinstance(value, str) AND value contains any key from replacements:
      RETURN True
  RETURN False
END FUNCTION
```

### Examples

- `{{TARGET_ACCOUNT_ROLE_ARN}}` has value `"arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole"` and `{{AWS_ACCOUNT}}` resolves to `"959096737760"`. After replacement, the config contains the literal string `arn:aws:iam::{{AWS_ACCOUNT}}:role/DevOpsCrossAccountAccessRole` instead of `arn:aws:iam::959096737760:role/DevOpsCrossAccountAccessRole`.

- `{{TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME}}` has value `"/acme-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id"` and `{{DEPLOYMENT_NAMESPACE}}` resolves to `"beta"`. After replacement, the config contains `/acme-saas/{{DEPLOYMENT_NAMESPACE}}/route53/hosted-zone-id` instead of `/acme-saas/beta/route53/hosted-zone-id`.

- A three-level chain: `{{A}}` → `"prefix-{{B}}"`, `{{B}}` → `"mid-{{C}}"`, `{{C}}` → `"leaf"`. Expected final value of `{{A}}`: `"prefix-mid-leaf"`. Without the fix, `{{A}}` resolves to `"prefix-mid-{{C}}"` or `"prefix-{{B}}"` depending on iteration order.

- A parameter with no chained references (e.g., `{{DEVOPS_ACCOUNT}}` → `"974817967438"`) should resolve identically before and after the fix.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Simple literal replacement values (no inner placeholders) must continue to resolve identically
- CDK context, environment variable, and static value resolution order in `__get_cdk_parameter_value()` must remain unchanged
- `__inherits__` and `__imports__` file-based resolution must continue to happen before placeholder substitution
- Placeholders in skipped sections (`cdk`, `deployments`) must continue to be left unresolved by `_check_unresolved_placeholders`
- Empty replacements dict must continue to return the config unchanged without errors
- `recursive_replace()` in `json_loading_utility.py` must not be modified — it is a general-purpose utility used elsewhere

**Scope:**
All replacement dictionaries where no value contains a `{{PLACEHOLDER}}` token referencing another key in the dict should be completely unaffected by this fix. The pre-resolution loop will detect no changes on the first pass and break immediately, making it a no-op for non-chained configs.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **No pre-resolution of replacement values**: The `__resolved_config()` method builds the `replacements` dict by iterating `cdk.parameters` and collecting `{placeholder: value}` pairs. It then passes this dict directly to `recursive_replace()`. At no point are the replacement VALUES themselves resolved against each other. When `recursive_replace()` encounters `{{TARGET_ACCOUNT_ROLE_ARN}}` in the config and replaces it with `"arn:aws:iam::{{AWS_ACCOUNT}}:role/..."`, the `{{AWS_ACCOUNT}}` token in that replacement string is never substituted because `recursive_replace()` only replaces placeholders in the config data — not within the replacement values.

2. **Iteration-order dependency**: Even if `recursive_replace()` were called multiple times, the issue would persist because the replacement values in the dict are static. The dict itself needs an internal resolution pass where each value is resolved using the other entries in the same dict.

3. **Proven pattern exists but was not applied here**: The `deploy.py` file in `acme-SaaS-IaC` already implements exactly this pattern — a multi-pass loop (up to 5 iterations) that resolves chained references within the parameters dict before applying them to the config. This pattern was not carried over to `CdkConfig.__resolved_config()`.

## Correctness Properties

Property 1: Bug Condition - Chained Placeholder Values Are Fully Resolved

_For any_ replacements dictionary where at least one value contains a `{{PLACEHOLDER}}` token matching another key in the dictionary, the pre-resolution step SHALL resolve all transitive references so that no replacement value contains any placeholder key from the dictionary.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Chained Replacements Produce Identical Results

_For any_ replacements dictionary where no value contains a `{{PLACEHOLDER}}` token matching another key in the dictionary, the pre-resolution step SHALL be a no-op — the replacement values and the final config output SHALL be identical to the original (unfixed) behavior.

**Validates: Requirements 3.1, 3.2, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `cdk-factory/src/cdk_factory/configurations/cdk_config.py`

**Function**: `__resolved_config()`

**Specific Changes**:

1. **Add multi-pass pre-resolution loop**: After building the `replacements` dict from `cdk.parameters` and before calling `recursive_replace()`, add a loop that resolves chained references within the replacement values themselves:
   ```python
   # Pre-resolve chained references in replacement values
   for _ in range(5):  # max passes to prevent infinite loops
       changed = False
       for key, value in replacements.items():
           if isinstance(value, str) and "{{" in value:
               new_value = value
               for find_str, replace_str in replacements.items():
                   if isinstance(replace_str, str):
                       new_value = new_value.replace(find_str, str(replace_str))
               if new_value != value:
                   replacements[key] = new_value
                   changed = True
       if not changed:
           break
   ```

2. **Placement**: The loop must be inserted after the `for parameter in parameters:` loop that builds the `replacements` dict, and before the `if replacements:` block that calls `recursive_replace()`.

3. **Max iterations guard**: The `range(5)` limit prevents infinite loops from circular references (e.g., `{{A}}` → `"{{B}}"`, `{{B}}` → `"{{A}}"`). Five passes is sufficient for any realistic chain depth and matches the pattern in `deploy.py`.

4. **Type safety**: The `isinstance(value, str)` and `isinstance(replace_str, str)` checks ensure non-string values (which can exist in the replacements dict) are handled safely.

5. **No changes to `recursive_replace()`**: The fix is entirely within `__resolved_config()`. The `recursive_replace()` utility remains a general-purpose single-pass replacer, preserving its contract for all other callers.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write a unit test that constructs a replacements dict with chained references (mimicking the real `config.json` parameters) and calls the pre-resolution logic. Run on UNFIXED code to observe that inner placeholders remain unresolved.

**Test Cases**:
1. **Single-level chain test**: Build replacements where `{{TARGET_ACCOUNT_ROLE_ARN}}` value contains `{{AWS_ACCOUNT}}`. Verify `{{AWS_ACCOUNT}}` remains literal after `recursive_replace()` (will fail on unfixed code)
2. **SSM parameter chain test**: Build replacements where `{{TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME}}` value contains `{{DEPLOYMENT_NAMESPACE}}`. Verify `{{DEPLOYMENT_NAMESPACE}}` remains literal (will fail on unfixed code)
3. **Multi-level chain test**: Build a 3-level chain `{{A}}` → `{{B}}` → `{{C}}` → literal. Verify intermediate placeholders remain (will fail on unfixed code)
4. **Circular reference test**: Build `{{A}}` → `{{B}}`, `{{B}}` → `{{A}}`. Verify the loop terminates without hanging (may fail on unfixed code)

**Expected Counterexamples**:
- Replacement values containing `{{...}}` tokens are passed through to the config unchanged
- Cause: no pre-resolution step exists in `__resolved_config()`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL replacements WHERE isBugCondition(replacements) DO
  pre_resolved := multiPassResolve(replacements)
  FOR EACH (key, value) IN pre_resolved:
    FOR EACH other_key IN pre_resolved:
      ASSERT other_key NOT IN value  // no unresolved chained refs
  result := recursive_replace(config, pre_resolved)
  ASSERT no "{{...}}" tokens in result (outside skipped sections)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL replacements WHERE NOT isBugCondition(replacements) DO
  ASSERT multiPassResolve(replacements) == replacements  // no-op
  ASSERT recursive_replace(config, replacements) == recursive_replace(config, replacements)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many replacement dictionaries automatically across the input domain
- It catches edge cases like empty dicts, single-entry dicts, and values with `{{` but no matching key
- It provides strong guarantees that behavior is unchanged for all non-chained configs

**Test Plan**: Observe behavior on UNFIXED code first for non-chained replacements, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Simple literal preservation**: Generate random replacements dicts where no value contains any key. Verify pre-resolution is a no-op and `recursive_replace` output is identical.
2. **Empty replacements preservation**: Verify empty dict passes through unchanged.
3. **Non-string value preservation**: Verify replacements with integer/boolean values are handled correctly.
4. **Config structure preservation**: Verify nested dicts, lists, and mixed structures are unchanged when replacements have no chained refs.

### Unit Tests

- Test multi-pass resolution with single-level chained references (TARGET_ACCOUNT_ROLE_ARN scenario)
- Test multi-pass resolution with multi-level chained references (3+ levels deep)
- Test that circular references terminate gracefully within 5 passes
- Test that non-chained replacements are unchanged after pre-resolution
- Test empty replacements dict
- Test replacements where values contain `{{` but no matching key in the dict

### Property-Based Tests

- Generate random replacements dicts with chained references and verify all values are fully resolved after pre-resolution (no value contains any dict key as substring)
- Generate random replacements dicts without chained references and verify pre-resolution is a no-op (output equals input)
- Generate random config structures and random non-chained replacements, verify `recursive_replace` output is identical before and after the fix

### Integration Tests

- Test full `__resolved_config()` flow with a config.json containing `TARGET_ACCOUNT_ROLE_ARN` and `TARGET_HOSTED_ZONE_ID_SSM_PARAMETER_NAME` chained references
- Test that `_check_unresolved_placeholders` passes after fix for configs with valid chained references
- Test end-to-end with real-world config patterns from Acme-SaaS-UI/devops/cdk/config.json
