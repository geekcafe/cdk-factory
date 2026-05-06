# Lambda Locker Missing App Config — Bugfix Design

## Overview

The `run-lock-versions.sh` shell script sets `CONFIG_DIR` to `${CDK_DIR}/configs/stacks/lambdas/resources` instead of `${CDK_DIR}/configs/stacks/lambdas`. This causes `scan_config_directory()` to never traverse the parent `lambdas/` directory where stack-level JSON files (like `lambda-app-settings.json`) reside. The `app-configurations` Docker lambda defined inside that file is therefore missing from both `--seed` and `--list` output.

The fix is a single-line change in the shell script to point `CONFIG_DIR` at the parent `lambdas/` directory. The Python scanner already handles both file formats (individual resource files and stack-level files with `resources` arrays) via recursive `os.walk()`, so no Python changes are needed.

## Glossary

- **Bug_Condition (C)**: `CONFIG_DIR` points to `lambdas/resources/` instead of `lambdas/`, causing stack-level config files in the parent directory to be excluded from scanning
- **Property (P)**: All Docker lambdas — including those defined in stack-level files with `resources` arrays — are discovered by `scan_config_directory()` and appear in seed/list output
- **Preservation**: All Docker lambdas previously discovered under `lambdas/resources/` subdirectories continue to be discovered when scanning from the parent `lambdas/` directory (since `os.walk` is recursive)
- **`scan_config_directory()`**: The method in `docker_version_locker.py` that recursively walks a directory tree, reads JSON files, and extracts Docker lambda entries
- **`_extract_docker_entry()`**: Static method that checks a dict for `docker.image=true` + valid `ecr.name` + valid `name` and returns a seed entry
- **Stack-level file**: A JSON config file (e.g., `lambda-app-settings.json`) that contains a `resources` array of lambda definitions rather than a single top-level lambda definition
- **Individual resource file**: A JSON config file (e.g., `resources/tenants/get-tenant.json`) that defines a single lambda at the top level

## Bug Details

### Bug Condition

The bug manifests when `run-lock-versions.sh` is invoked with `--seed` or `--list`. The script passes `--config-dir` as `${CDK_DIR}/configs/stacks/lambdas/resources`, which is a subdirectory. Stack-level JSON files like `lambda-app-settings.json` live in the parent `lambdas/` directory and are never reached by `os.walk()` starting from `resources/`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ShellScriptInvocation (script path + arguments + CONFIG_DIR value)
  OUTPUT: boolean

  RETURN input.CONFIG_DIR = "${CDK_DIR}/configs/stacks/lambdas/resources"
         AND input.mode IN {"--seed", "--list"}
         AND EXISTS file IN parent_directory(input.CONFIG_DIR) WHERE
           file.has_resources_array = true
           AND any_resource_in(file).docker.image = true
           AND any_resource_in(file).ecr.name IS NOT EMPTY
END FUNCTION
```

### Examples

- **`--seed` mode**: User runs `./run-lock-versions.sh --seed`. The script passes `--config-dir lambdas/resources/`. `scan_config_directory()` finds individual resource files (e.g., `get-tenant.json`) but never sees `lambda-app-settings.json`. The resulting `.docker-locked-versions.json` is missing the `app-configurations` entry.
- **`--list` mode**: User runs `./run-lock-versions.sh --list`. Same `CONFIG_DIR` is passed. The mapping summary omits `app-configurations` and its ECR repo `acme-systems/v3/acme-saas-core-services`.
- **Multiple stack-level files affected**: Any stack-level file in `lambdas/` with Docker resources in its `resources` array (e.g., `lambda-file-system.json`, `lambda-tenants.json`) would also be missed if they contain Docker lambdas not duplicated as individual resource files.
- **Edge case — `--apply` mode**: Not affected because `--apply` reads from the already-generated `.docker-locked-versions.json` file, not from `CONFIG_DIR`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- All Docker lambdas previously discovered under `lambdas/resources/` subdirectories (e.g., `resources/tenants/get-tenant.json`, `resources/file-system/post-file-upload-processing-v3.json`) must continue to be discovered
- Non-Docker JSON files (files without `"docker": {"image": true}`) must continue to be skipped without error
- Stack-level files with `resources` arrays containing a mix of Docker and non-Docker entries must continue to extract only Docker entries
- Existing entries in the locked versions file with non-empty tags must continue to be preserved during seed merge
- `--apply` mode must continue to work unchanged (it reads from the locked versions file, not CONFIG_DIR)
- Invalid JSON files must continue to be skipped gracefully with a warning

**Scope:**
All inputs that do NOT involve the `CONFIG_DIR` path are completely unaffected by this fix. This includes:
- `--apply` mode (reads locked versions file directly)
- Normal resolve mode without `--seed` (reads locked versions file directly)
- The Python `scan_config_directory()` logic itself (unchanged — only the shell script's directory argument changes)

## Hypothesized Root Cause

Based on the bug description, the root cause is straightforward:

1. **Incorrect CONFIG_DIR path in shell script**: Line in `run-lock-versions.sh` sets `CONFIG_DIR="${CDK_DIR}/configs/stacks/lambdas/resources"` — this was likely correct when all lambda configs were individual resource files in subdirectories, but became incorrect when stack-level files (like `lambda-app-settings.json`) were added to the parent `lambdas/` directory.

2. **No regression in Python code**: `scan_config_directory()` already handles both formats correctly:
   - Individual resource files: checks top-level `docker.image`, `ecr.name`, `name`
   - Stack-level files: iterates `resources` array and calls `_extract_docker_entry()` on each element
   - Uses `os.walk()` which is inherently recursive from whatever root it's given

3. **Historical evolution**: The config directory structure evolved to include stack-level files at the `lambdas/` level, but the shell script was never updated to reflect the new root.

## Correctness Properties

Property 1: Bug Condition — Stack-Level Docker Lambdas Discovered

_For any_ invocation of `run-lock-versions.sh` with `--seed` or `--list` where stack-level JSON files exist in `lambdas/` containing Docker lambda definitions in their `resources` arrays, the fixed script SHALL pass `--config-dir` pointing to `lambdas/` so that `scan_config_directory()` discovers those lambdas (including `app-configurations` from `lambda-app-settings.json`).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Existing Resource Subdirectory Lambdas Still Discovered

_For any_ invocation where `CONFIG_DIR` is changed from `lambdas/resources/` to `lambdas/`, the fixed script SHALL produce a superset of the previously discovered entries, because `os.walk("lambdas/")` recursively traverses `lambdas/resources/` and all its subdirectories, preserving discovery of all individual resource files.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `Acme-SaaS-IaC/cdk/commands/run-lock-versions.sh`

**Variable**: `CONFIG_DIR`

**Specific Changes**:
1. **Change CONFIG_DIR assignment** (line ~18):
   - FROM: `CONFIG_DIR="${CDK_DIR}/configs/stacks/lambdas/resources"`
   - TO: `CONFIG_DIR="${CDK_DIR}/configs/stacks/lambdas"`

That is the only change required. No Python code modifications needed.

**Rationale**: `os.walk()` in `scan_config_directory()` already recursively descends into all subdirectories from whatever root it's given. Moving the root up one level means it will:
- Still find all files under `resources/` (recursive descent)
- Additionally find stack-level files like `lambda-app-settings.json` in the `lambdas/` directory itself
- Additionally find any files in `lambdas/pre/` if they contain Docker lambdas

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write a test that creates a directory structure mimicking the real layout (parent dir with stack-level files + `resources/` subdirectory with individual files), then calls `scan_config_directory()` with the subdirectory path (simulating the bug) and asserts that stack-level entries are missing.

**Test Cases**:
1. **Missing stack-level entries**: Call `scan_config_directory("lambdas/resources/")` and assert `app-configurations` is NOT in the result (will demonstrate the bug on unfixed code)
2. **Subdirectory entries still found**: Call `scan_config_directory("lambdas/resources/")` and assert individual resource files ARE found (confirms the scanner works for the subdirectory)
3. **Shell script verification**: Run `--list` with the current `CONFIG_DIR` and confirm `app-configurations` is absent from output

**Expected Counterexamples**:
- `scan_config_directory("lambdas/resources/")` returns entries from subdirectories but NOT from `lambda-app-settings.json`
- Root cause confirmed: the Python scanner works correctly; only the directory path is wrong

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := scan_config_directory("lambdas/")
  ASSERT "app-configurations" IN result.names
  ASSERT result.entry("app-configurations").ecr = "acme-systems/v3/acme-saas-core-services"
  ASSERT result.entry("app-configurations").tag = ""
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  // Scanning from parent is a superset of scanning from subdirectory
  ASSERT scan_config_directory("lambdas/") ⊇ scan_config_directory("lambdas/resources/")
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It can generate many directory structures with varying mixes of Docker/non-Docker files
- It catches edge cases like empty directories, invalid JSON, non-dict top-level values
- It provides strong guarantees that the superset relationship holds for all configurations

**Test Plan**: Observe behavior on UNFIXED code first (scanning from `resources/`), then write property-based tests that verify scanning from `lambdas/` always produces a superset.

**Test Cases**:
1. **Superset property**: For any directory tree, `scan_config_directory(parent)` results always contain all entries from `scan_config_directory(parent/resources/)`
2. **Individual resource files preserved**: All files under `resources/` subdirectories continue to be discovered
3. **Non-Docker files still skipped**: Files without `docker.image=true` are not included regardless of scan root
4. **Merge behavior preserved**: Existing pinned tags in locked versions file are never overwritten during seed merge

### Unit Tests

- Test `scan_config_directory()` with a directory tree that has both stack-level files in the root and individual files in subdirectories
- Test that scanning from a parent directory discovers entries from both levels
- Test that scanning from a subdirectory only discovers entries at that level and below
- Test edge cases: empty `resources` arrays, mixed Docker/non-Docker resources, invalid JSON files

### Property-Based Tests

- Generate random directory trees with varying numbers of stack-level and individual resource files, verify `scan_config_directory(parent)` ⊇ `scan_config_directory(parent/child)`
- Generate random resource dicts with varying `docker`, `ecr`, and `name` fields, verify `_extract_docker_entry()` correctly identifies Docker lambdas
- Generate random existing + discovered entry lists, verify `merge_entries()` preserves non-empty tags and adds new entries

### Integration Tests

- Run `--seed` with `CONFIG_DIR` pointing to `lambdas/` on a realistic directory structure and verify `app-configurations` appears in the output file
- Run `--list` with `CONFIG_DIR` pointing to `lambdas/` and verify the mapping summary includes `app-configurations` under `acme-systems/v3/acme-saas-core-services`
- Verify `--apply` mode continues to work unchanged after the fix
