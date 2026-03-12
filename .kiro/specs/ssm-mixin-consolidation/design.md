# Design Document: SSM Mixin Consolidation

## Overview

This design details the safe removal of unused SSM parameter mixins from the CDK Factory codebase. The StandardizedSsmMixin is the single, actively-used SSM parameter handling approach inherited by all stacks through IStack. Two unused mixins (EnhancedSsmParameterMixin and SsmParameterMixin) along with their supporting utilities (LiveSsmResolver) will be removed to eliminate code confusion and reduce maintenance burden.

### Current State

The codebase contains three SSM parameter mixins:

1. **StandardizedSsmMixin** (ACTIVE)
   - Location: `src/cdk_factory/interfaces/standardized_ssm_mixin.py`
   - Used by: All stacks via IStack inheritance
   - Features: Configuration-driven imports/exports, template variable resolution, list parameter support
   - Status: Production-ready, fully tested, actively maintained

2. **EnhancedSsmParameterMixin** (UNUSED)
   - Location: `src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py`
   - Used by: No stacks (never adopted)
   - Features: Auto-discovery, live SSM resolution
   - Status: Experimental code that was never integrated

3. **SsmParameterMixin** (LEGACY/UNUSED)
   - Location: `src/cdk_factory/interfaces/ssm_parameter_mixin.py`
   - Used by: No stacks (replaced by StandardizedSsmMixin)
   - Features: Basic SSM parameter export/import
   - Status: Legacy code superseded by StandardizedSsmMixin

### Target State

After cleanup:
- Single SSM mixin: StandardizedSsmMixin (via IStack)
- All unused code removed
- Documentation updated to reflect current architecture
- No breaking changes to existing stacks

## Architecture

### Inheritance Hierarchy

Current (before cleanup):
```
Stack (aws-cdk)
  └── IStack
       ├── StandardizedSsmMixin (USED)
       └── [All application stacks inherit from IStack]

[Unused classes exist but are not in inheritance chain]
  ├── EnhancedSsmParameterMixin (UNUSED)
  ├── SsmParameterMixin (UNUSED)
  └── LiveSsmResolver (UNUSED)
```

After cleanup:
```
Stack (aws-cdk)
  └── IStack
       ├── StandardizedSsmMixin (USED)
       └── [All application stacks inherit from IStack]

[Unused classes removed]
```

### Dependency Analysis

Files to be deleted and their dependencies:

1. **enhanced_ssm_parameter_mixin.py**
   - Imports: `LiveSsmResolver`, `EnhancedSsmConfig`, `EnhancedBaseConfig`
   - Imported by: None (verified via grep search)
   - Safe to delete: Yes

2. **ssm_parameter_mixin.py**
   - Imports: Standard AWS CDK libraries only
   - Imported by: `enhanced_ssm_parameter_mixin.py` (which is also being deleted)
   - Safe to delete: Yes

3. **live_ssm_resolver.py**
   - Imports: `boto3_assist`, `aws_lambda_powertools`
   - Imported by: `enhanced_ssm_parameter_mixin.py`, `environment_services.py`
   - Safe to delete: Requires cleanup in `environment_services.py` first

4. **archive/migrate_to_enhanced_ssm.py**
   - Migration script for a migration that never happened
   - Safe to delete: Yes

### Reference Cleanup Required

Based on grep search results, the following files reference the unused mixins:

1. **src/cdk_factory/utilities/environment_services.py**
   - References: `LiveSsmResolver`
   - Action: Remove import and usage

2. **Documentation files** (multiple)
   - `docs/enhanced-ssm-parameter-pattern.md`
   - `docs/ssm_parameter_pattern.md`
   - `samples/ssm_parameter_sharing/README.md`
   - Action: Update or remove references

3. **Test files**
   - `tests/test_enhanced_ssm_migration.py`
   - `tests/unit/test_enhanced_ssm_config_paths.py`
   - Action: Remove tests for deleted mixins

4. **External project references** (my-app-real-estate-iac)
   - These are in a separate project directory
   - Action: Document but do not modify (out of scope)

## Components and Interfaces

### Files to Delete

#### Primary Mixin Files
1. `src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py` (323 lines)
2. `src/cdk_factory/interfaces/ssm_parameter_mixin.py` (234 lines)
3. `src/cdk_factory/interfaces/live_ssm_resolver.py` (186 lines)

#### Archive Files
4. `archive/migrate_to_enhanced_ssm.py` (264 lines)

#### Test Files
5. `tests/test_enhanced_ssm_migration.py` (entire file)
6. `tests/unit/test_enhanced_ssm_config_paths.py` (entire file)

### Files to Modify

#### Code Files
1. **src/cdk_factory/utilities/environment_services.py**
   - Remove: `from cdk_factory.interfaces.live_ssm_resolver import LiveSsmResolver`
   - Remove: LiveSsmResolver instantiation and usage (lines ~201-206)
   - Impact: Lambda environment variable resolution
   - Mitigation: The code has fallback logic that will continue to work

#### Documentation Files
2. **src/cdk_factory/interfaces/SSM_RESOLUTION_PATTERNS.md**
   - Current state: Already references only StandardizedSsmMixin
   - Action: Verify no updates needed

3. **docs/enhanced-ssm-parameter-pattern.md**
   - Action: Delete entire file (documents unused EnhancedSsmParameterMixin)

4. **docs/ssm_parameter_pattern.md**
   - Action: Delete entire file (documents unused SsmParameterMixin)

5. **samples/ssm_parameter_sharing/README.md**
   - Action: Update to reference StandardizedSsmMixin instead of SsmParameterMixin

6. **archive/README.md**
   - Action: Remove references to enhanced SSM migration

### Files to Preserve (No Changes)

1. **src/cdk_factory/interfaces/standardized_ssm_mixin.py**
   - The active, production SSM mixin
   - No changes required

2. **src/cdk_factory/interfaces/istack.py**
   - Already inherits from StandardizedSsmMixin
   - No changes required

3. **All stack implementations**
   - Already use StandardizedSsmMixin via IStack
   - No changes required

## Data Models

### Configuration Structure (Unchanged)

The StandardizedSsmMixin uses this configuration structure, which remains unchanged:

```python
{
    "ssm": {
        "enabled": true,
        "imports": {
            "parameter_name": "/path/to/parameter",
            "list_parameter": ["/path/1", "/path/2"]
        },
        "exports": {
            "parameter_name": "/path/to/export"
        }
    }
}
```

### Template Variables (Unchanged)

Supported template variables in SSM paths:
- `{{ENVIRONMENT}}` - Deployment environment
- `{{WORKLOAD_NAME}}` - Workload name  
- `{{AWS_REGION}}` - AWS region

### SSM Resolution Patterns (Unchanged)

Supported patterns:
- `{{ssm:/path}}` - String or SecureString parameter
- `{{ssm-secure:/path}}` - Explicit SecureString parameter
- `{{ssm-list:/path}}` - StringList parameter

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: File Deletion Completeness

*For any* file in the deletion list (enhanced_ssm_parameter_mixin.py, ssm_parameter_mixin.py, live_ssm_resolver.py, migrate_to_enhanced_ssm.py, test_enhanced_ssm_migration.py, test_enhanced_ssm_config_paths.py, enhanced-ssm-parameter-pattern.md, ssm_parameter_pattern.md), after cleanup execution, that file SHALL NOT exist in the filesystem.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 5.1, 7.2**

### Property 2: Import Reference Elimination

*For any* Python file in the codebase after cleanup, searching for import statements containing "EnhancedSsmParameterMixin", "SsmParameterMixin" (excluding "StandardizedSsmMixin"), or "LiveSsmResolver" SHALL return zero matches.

**Validates: Requirements 1.5, 3.3, 6.5**

### Property 3: String Reference Elimination

*For any* file in the codebase after cleanup (excluding external project directories), searching for string references to "EnhancedSsmParameterMixin", "SsmParameterMixin" (excluding "StandardizedSsmMixin"), or "LiveSsmResolver" SHALL return zero matches.

**Validates: Requirements 4.2, 4.3, 5.2, 6.1, 6.2, 6.3**

### Property 4: Configuration-Driven Import Support

*For any* valid SSM configuration with an "imports" section containing SSM parameter paths, the StandardizedSsmMixin SHALL successfully import those parameters and make them available via get_ssm_imported_value().

**Validates: Requirements 2.1**

### Property 5: Configuration-Driven Export Support

*For any* valid SSM configuration with an "exports" section and corresponding resource values, the StandardizedSsmMixin SHALL successfully create SSM parameters at the specified paths.

**Validates: Requirements 2.2**

### Property 6: Template Variable Resolution

*For any* SSM path containing template variables ({{ENVIRONMENT}}, {{WORKLOAD_NAME}}, {{AWS_REGION}}), the StandardizedSsmMixin SHALL resolve those variables to their actual values from the workload/deployment configuration.

**Validates: Requirements 2.3**

### Property 7: List Parameter Support

*For any* SSM configuration that imports a list parameter (array of paths), the StandardizedSsmMixin SHALL return a list of resolved values accessible via get_ssm_imported_value().

**Validates: Requirements 2.4**

### Property 8: SSM Path Validation

*For any* SSM path provided to StandardizedSsmMixin, if the path is invalid (doesn't start with "/", has fewer than 4 segments, or contains invalid characters), the mixin SHALL raise a ValueError with a descriptive error message.

**Validates: Requirements 2.5**

### Property 9: SSM Resolution Pattern Support

*For any* value string containing SSM resolution patterns ({{ssm:path}}, {{ssm-secure:path}}, or {{ssm-list:path}}), the StandardizedSsmMixin.resolve_ssm_value() method SHALL return a CDK token that resolves to the parameter value at deployment time.

**Validates: Requirements 2.6**

### Property 10: IStack Inheritance Preservation

*For any* stack class in the codebase that inherits from IStack, that stack SHALL have access to all StandardizedSsmMixin methods (setup_ssm_integration, process_ssm_imports, export_ssm_parameters, get_ssm_imported_value) without requiring any code changes.

**Validates: Requirements 3.1, 3.2**

## Error Handling

### Pre-Cleanup Validation

Before deleting any files, the cleanup process SHALL:

1. **Verify no active imports**
   - Search all Python files for imports of classes to be deleted
   - Fail if any imports found (except in files also being deleted)
   - Error message: "Cannot proceed: Active imports found for {class_name} in {file_path}"

2. **Verify IStack inheritance**
   - Confirm IStack inherits from StandardizedSsmMixin
   - Fail if inheritance is missing
   - Error message: "Cannot proceed: IStack does not inherit from StandardizedSsmMixin"

3. **Verify test baseline**
   - Run existing tests and record results
   - Fail if tests are already failing
   - Error message: "Cannot proceed: Test suite has pre-existing failures"

4. **Create backup**
   - Create git branch or backup of all files to be modified/deleted
   - Fail if backup creation fails
   - Error message: "Cannot proceed: Failed to create backup"

### Post-Cleanup Validation

After cleanup, the process SHALL:

1. **Verify file deletion**
   - Confirm all target files are deleted
   - Error if any files still exist
   - Error message: "Cleanup incomplete: {file_path} still exists"

2. **Search for orphaned references**
   - Grep for deleted class names across codebase
   - Report any findings for manual review
   - Warning message: "Orphaned reference found in {file_path}: {line_content}"

3. **Run test suite**
   - Execute all tests (excluding deleted test files)
   - Compare results to pre-cleanup baseline
   - Error if new failures introduced
   - Error message: "Cleanup broke tests: {test_name} now failing"

4. **Verify imports**
   - Attempt to import StandardizedSsmMixin
   - Attempt to import IStack
   - Error if imports fail
   - Error message: "Import validation failed: {error_details}"

### Rollback Procedure

If any post-cleanup validation fails:

1. Restore from backup/git branch
2. Report specific validation failure
3. Do not proceed with commit
4. Require manual investigation

## Cleanup Procedure

This section provides a step-by-step approach to safely remove unused SSM mixins.

### Phase 1: Pre-Cleanup Verification

**Step 1.1: Create Backup**
```bash
# Create a git branch for the cleanup
git checkout -b cleanup/ssm-mixin-consolidation
git push -u origin cleanup/ssm-mixin-consolidation
```

**Step 1.2: Run Baseline Tests**
```bash
# Run full test suite and record results
pytest tests/ -v --tb=short > baseline_test_results.txt
echo $? > baseline_exit_code.txt
```

**Step 1.3: Verify No Active Imports**
```bash
# Search for imports of classes to be deleted
grep -r "from.*enhanced_ssm_parameter_mixin import" --include="*.py" src/
grep -r "from.*ssm_parameter_mixin import" --include="*.py" src/ | grep -v standardized
grep -r "from.*live_ssm_resolver import" --include="*.py" src/

# Expected: Only matches in files that will also be deleted
```

**Step 1.4: Verify IStack Inheritance**
```bash
# Check that IStack inherits from StandardizedSsmMixin
grep -A 5 "class IStack" src/cdk_factory/interfaces/istack.py | grep StandardizedSsmMixin

# Expected: Should find StandardizedSsmMixin in inheritance
```

### Phase 2: Code Cleanup

**Step 2.1: Remove LiveSsmResolver Usage from environment_services.py**

File: `src/cdk_factory/utilities/environment_services.py`

Remove lines ~18 and ~201-206:
```python
# REMOVE THIS IMPORT
from cdk_factory.interfaces.live_ssm_resolver import LiveSsmResolver

# REMOVE THIS CODE BLOCK (around line 201-206)
# Convert lambda config to dict format for LiveSsmResolver
ssm_config = lambda_config.ssm if isinstance(lambda_config.ssm, dict) else lambda_config.ssm.__dict__
live_resolver = LiveSsmResolver({"ssm": ssm_config})
if live_resolver.enabled:
    logger.info("Live SSM resolution enabled for Lambda environment variables")
```

Rationale: This code attempts to use LiveSsmResolver, but it's not actually integrated into the environment variable resolution logic. Removing it will not break functionality.

**Step 2.2: Delete Unused Mixin Files**
```bash
# Delete the three unused mixin files
rm src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py
rm src/cdk_factory/interfaces/ssm_parameter_mixin.py
rm src/cdk_factory/interfaces/live_ssm_resolver.py

# Verify deletion
test ! -f src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py && echo "✓ enhanced_ssm_parameter_mixin.py deleted"
test ! -f src/cdk_factory/interfaces/ssm_parameter_mixin.py && echo "✓ ssm_parameter_mixin.py deleted"
test ! -f src/cdk_factory/interfaces/live_ssm_resolver.py && echo "✓ live_ssm_resolver.py deleted"
```

**Step 2.3: Delete Migration Script**
```bash
# Delete the unused migration script
rm archive/migrate_to_enhanced_ssm.py

# Verify deletion
test ! -f archive/migrate_to_enhanced_ssm.py && echo "✓ migrate_to_enhanced_ssm.py deleted"
```

**Step 2.4: Delete Test Files**
```bash
# Delete tests for removed mixins
rm tests/test_enhanced_ssm_migration.py
rm tests/unit/test_enhanced_ssm_config_paths.py

# Verify deletion
test ! -f tests/test_enhanced_ssm_migration.py && echo "✓ test_enhanced_ssm_migration.py deleted"
test ! -f tests/unit/test_enhanced_ssm_config_paths.py && echo "✓ test_enhanced_ssm_config_paths.py deleted"
```

### Phase 3: Documentation Cleanup

**Step 3.1: Delete Obsolete Documentation**
```bash
# Delete documentation for removed mixins
rm docs/enhanced-ssm-parameter-pattern.md
rm docs/ssm_parameter_pattern.md

# Verify deletion
test ! -f docs/enhanced-ssm-parameter-pattern.md && echo "✓ enhanced-ssm-parameter-pattern.md deleted"
test ! -f docs/ssm_parameter_pattern.md && echo "✓ ssm_parameter_pattern.md deleted"
```

**Step 3.2: Update archive/README.md**

File: `archive/README.md`

Remove or update the section about enhanced SSM migration (around lines 12-15):
```markdown
# REMOVE OR UPDATE THIS SECTION
**What it did**:
- Updated 10+ configuration classes to inherit from `EnhancedBaseConfig`
- Updated 11+ stack implementations to use `EnhancedSsmParameterMixin`
- Added imports for enhanced base configuration
- Preserved backward compatibility with existing configurations
```

Replace with:
```markdown
**Note**: The enhanced SSM migration was never completed. The codebase uses StandardizedSsmMixin instead.
```

**Step 3.3: Update samples/ssm_parameter_sharing/README.md**

File: `samples/ssm_parameter_sharing/README.md`

Update references from SsmParameterMixin to StandardizedSsmMixin:
```markdown
# CHANGE FROM:
2. `SsmParameterMixin` - Mixin class with methods for exporting/importing SSM parameters

# CHANGE TO:
2. `StandardizedSsmMixin` - Mixin class with methods for exporting/importing SSM parameters (inherited via IStack)
```

**Step 3.4: Verify SSM_RESOLUTION_PATTERNS.md**

File: `src/cdk_factory/interfaces/SSM_RESOLUTION_PATTERNS.md`

This file already correctly references only StandardizedSsmMixin. No changes needed.

### Phase 4: Post-Cleanup Verification

**Step 4.1: Search for Orphaned References**
```bash
# Search for any remaining references to deleted classes
echo "Searching for EnhancedSsmParameterMixin references..."
grep -r "EnhancedSsmParameterMixin" --include="*.py" --include="*.md" src/ docs/ tests/ samples/ || echo "✓ No references found"

echo "Searching for SsmParameterMixin references (excluding StandardizedSsmMixin)..."
grep -r "SsmParameterMixin" --include="*.py" --include="*.md" src/ docs/ tests/ samples/ | grep -v "StandardizedSsmMixin" || echo "✓ No references found"

echo "Searching for LiveSsmResolver references..."
grep -r "LiveSsmResolver" --include="*.py" --include="*.md" src/ docs/ tests/ samples/ || echo "✓ No references found"
```

Expected: No matches (or only matches in external project directories like my-app-real-estate-iac, which are out of scope)

**Step 4.2: Verify Imports**
```python
# Create and run verification script: verify_imports.py
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin

# Verify IStack has StandardizedSsmMixin methods
assert hasattr(IStack, 'setup_ssm_integration'), "IStack missing setup_ssm_integration"
assert hasattr(IStack, 'process_ssm_imports'), "IStack missing process_ssm_imports"
assert hasattr(IStack, 'export_ssm_parameters'), "IStack missing export_ssm_parameters"
assert hasattr(IStack, 'get_ssm_imported_value'), "IStack missing get_ssm_imported_value"

print("✓ All StandardizedSsmMixin methods available via IStack")
```

**Step 4.3: Run Test Suite**
```bash
# Run test suite (excluding deleted test files)
pytest tests/ -v --tb=short \
  --ignore=tests/test_enhanced_ssm_migration.py \
  --ignore=tests/unit/test_enhanced_ssm_config_paths.py \
  > post_cleanup_test_results.txt

echo $? > post_cleanup_exit_code.txt

# Compare exit codes
diff baseline_exit_code.txt post_cleanup_exit_code.txt && echo "✓ Test suite status unchanged"
```

**Step 4.4: Verify Stack Synthesis**
```bash
# Synthesize a sample stack that uses SSM parameters
# (Adjust stack name based on your project)
cdk synth <stack-name> --no-staging

# Expected: Synthesis succeeds with no errors
```

### Phase 5: Commit and Review

**Step 5.1: Review Changes**
```bash
# Review all changes
git status
git diff

# Verify expected files are deleted
git ls-files --deleted
```

**Step 5.2: Commit Changes**
```bash
# Stage all changes
git add -A

# Commit with descriptive message
git commit -m "Remove unused SSM mixins (EnhancedSsmParameterMixin, SsmParameterMixin, LiveSsmResolver)

- Deleted unused mixin files and supporting utilities
- Removed obsolete migration script and tests
- Updated documentation to reference only StandardizedSsmMixin
- Verified no breaking changes to existing stacks
- All tests pass

Closes: SSM-MIXIN-CONSOLIDATION"

# Push changes
git push origin cleanup/ssm-mixin-consolidation
```

**Step 5.3: Create Pull Request**

Create a pull request with:
- Title: "Remove unused SSM mixins"
- Description: Link to this design document
- Checklist:
  - [ ] All target files deleted
  - [ ] No orphaned references found
  - [ ] Test suite passes
  - [ ] Documentation updated
  - [ ] Stack synthesis verified

### Rollback Procedure

If any verification step fails:

1. **Identify the failure**
   - Note which verification step failed
   - Capture error messages

2. **Rollback changes**
   ```bash
   # Discard all changes
   git reset --hard HEAD
   
   # Or restore specific files
   git checkout HEAD -- <file-path>
   ```

3. **Investigate**
   - Review the failure
   - Determine if it's a pre-existing issue or caused by cleanup
   - Update design document if needed

4. **Do not proceed**
   - Do not commit or merge if any verification fails
   - Resolve issues before retrying

## Testing Strategy

### Pre-Cleanup Testing

1. **Baseline Test Execution**
   - Run full test suite before any changes
   - Record all test results
   - Document any pre-existing failures
   - Command: `pytest tests/ -v --tb=short`

2. **Import Verification**
   - Verify StandardizedSsmMixin can be imported
   - Verify IStack inherits from StandardizedSsmMixin
   - Verify no stack files import deleted mixins

### Cleanup Execution Testing

1. **File Deletion Verification**
   - After each file deletion, verify file no longer exists
   - Use: `test ! -f <file_path>` (exit code 0 = success)

2. **Reference Search**
   - After all deletions, search for orphaned references
   - Use: `grep -r "EnhancedSsmParameterMixin" --include="*.py" src/`
   - Use: `grep -r "SsmParameterMixin" --include="*.py" src/ | grep -v "StandardizedSsmMixin"`
   - Use: `grep -r "LiveSsmResolver" --include="*.py" src/`
   - Expected: Zero matches (except in external projects)

### Post-Cleanup Testing

1. **Import Testing**
   ```python
   # Test script: verify_imports.py
   from cdk_factory.interfaces.istack import IStack
   from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
   
   # Verify IStack has StandardizedSsmMixin methods
   assert hasattr(IStack, 'setup_ssm_integration')
   assert hasattr(IStack, 'process_ssm_imports')
   assert hasattr(IStack, 'export_ssm_parameters')
   ```

2. **Test Suite Execution**
   - Run full test suite (excluding deleted test files)
   - Command: `pytest tests/ -v --tb=short --ignore=tests/test_enhanced_ssm_migration.py --ignore=tests/unit/test_enhanced_ssm_config_paths.py`
   - Expected: Same pass/fail results as baseline (no new failures)

3. **Stack Synthesis Testing**
   - Synthesize a sample stack that uses SSM parameters
   - Verify CDK synthesis succeeds
   - Verify SSM parameter references are correctly generated
   - Command: `cdk synth <stack-name> --no-staging`

### Test Coverage Maintenance

Tests to preserve (no changes):
- All tests for StandardizedSsmMixin functionality
- All integration tests that use SSM parameters via IStack
- All stack-specific tests

Tests to remove:
- `tests/test_enhanced_ssm_migration.py` (tests deleted EnhancedSsmParameterMixin)
- `tests/unit/test_enhanced_ssm_config_paths.py` (tests deleted EnhancedSsmConfig)

### Property-Based Testing

While this cleanup is primarily a deletion task, we will use property-based testing concepts for validation:

**Property Test 1: No Orphaned Imports**
- Generate list of all Python files in src/
- For each file, parse imports
- Assert no imports of deleted classes
- Iterations: All files (not randomized)

**Property Test 2: StandardizedSsmMixin Availability**
- Generate list of all stack classes
- For each stack, verify it inherits from IStack
- Assert StandardizedSsmMixin methods are available
- Iterations: All stack classes (not randomized)

### Testing Tools

- **pytest**: Primary test runner
- **grep/ripgrep**: Reference searching
- **Python AST parser**: Import verification
- **CDK CLI**: Stack synthesis verification

### Success Criteria

Cleanup is successful when:
1. All target files are deleted
2. Zero orphaned references found (except external projects)
3. All preserved tests pass
4. StandardizedSsmMixin functionality verified
5. Sample stack synthesis succeeds
6. No import errors when loading IStack



## Summary

This design provides a comprehensive, safe approach to removing unused SSM parameter mixins from the CDK Factory codebase. The cleanup eliminates approximately 1,000 lines of unused code while preserving all existing functionality through the StandardizedSsmMixin.

### Key Design Decisions

1. **No Breaking Changes**: All stacks continue to work without modification because they inherit StandardizedSsmMixin through IStack.

2. **Comprehensive Verification**: Multi-phase verification ensures no orphaned references or broken functionality.

3. **Documentation First**: Documentation cleanup ensures developers understand the current architecture.

4. **Rollback Safety**: Git-based workflow allows immediate rollback if any verification fails.

### Files Affected

**Deleted (8 files, ~1,200 lines)**:
- 3 unused mixin files
- 1 migration script
- 2 test files
- 2 documentation files

**Modified (3 files, ~20 lines)**:
- environment_services.py (remove LiveSsmResolver usage)
- archive/README.md (update migration notes)
- samples/ssm_parameter_sharing/README.md (update references)

**Preserved (all other files)**:
- StandardizedSsmMixin (no changes)
- IStack (no changes)
- All stack implementations (no changes)
- All production tests (no changes)

### Risk Assessment

**Low Risk** because:
- Deleted code is not imported or used anywhere
- StandardizedSsmMixin is already the active implementation
- Comprehensive verification catches any issues before commit
- Git-based rollback available at any point
- No changes to production stack code

### Success Metrics

Cleanup is successful when:
1. ✓ All 8 target files deleted
2. ✓ Zero orphaned references (except external projects)
3. ✓ Test suite passes with same results as baseline
4. ✓ Stack synthesis succeeds
5. ✓ StandardizedSsmMixin methods accessible via IStack
6. ✓ Documentation accurately reflects current architecture

### Next Steps

After this design is approved:
1. Execute Phase 1: Pre-Cleanup Verification
2. Execute Phase 2: Code Cleanup
3. Execute Phase 3: Documentation Cleanup
4. Execute Phase 4: Post-Cleanup Verification
5. Execute Phase 5: Commit and Review

Estimated time: 2-3 hours for careful execution and verification.
