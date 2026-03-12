# Implementation Plan: SSM Mixin Consolidation

## Overview

This plan implements the safe removal of unused SSM parameter mixins (EnhancedSsmParameterMixin, SsmParameterMixin, LiveSsmResolver) from the CDK Factory codebase. The cleanup follows a 5-phase approach with comprehensive verification at each step to ensure no breaking changes. All stacks will continue to use StandardizedSsmMixin via IStack inheritance without modification.

## Tasks

- [ ] 1. Phase 1: Pre-Cleanup Verification
  - [ ] 1.1 Create backup branch and verify git state
    - Create git branch `cleanup/ssm-mixin-consolidation`
    - Push branch to remote
    - Verify working directory is clean
    - _Requirements: 3.4_

  - [ ] 1.2 Run baseline test suite and record results
    - Execute full test suite with pytest
    - Save test results to baseline_test_results.txt
    - Save exit code to baseline_exit_code.txt
    - Verify no pre-existing test failures
    - _Requirements: 3.4, 7.3_

  - [ ] 1.3 Verify no active imports of classes to be deleted
    - Search for imports of EnhancedSsmParameterMixin in src/
    - Search for imports of SsmParameterMixin (excluding StandardizedSsmMixin) in src/
    - Search for imports of LiveSsmResolver in src/
    - Verify only matches are in files that will also be deleted
    - _Requirements: 1.5, 3.3, 6.5_

  - [ ] 1.4 Verify IStack inherits from StandardizedSsmMixin
    - Read src/cdk_factory/interfaces/istack.py
    - Confirm StandardizedSsmMixin is in IStack's inheritance chain
    - Fail if inheritance is missing
    - _Requirements: 3.2_

- [ ] 2. Phase 2: Code Cleanup
  - [ ] 2.1 Remove LiveSsmResolver usage from environment_services.py
    - Remove import statement for LiveSsmResolver (line ~18)
    - Remove LiveSsmResolver instantiation and usage (lines ~201-206)
    - Verify file still has valid Python syntax
    - _Requirements: 1.3, 1.5_

  - [ ]* 2.2 Run quick syntax check on environment_services.py
    - Use getDiagnostics to verify no syntax errors
    - _Requirements: 3.4_

  - [ ] 2.3 Delete unused mixin files
    - Delete src/cdk_factory/interfaces/enhanced_ssm_parameter_mixin.py
    - Delete src/cdk_factory/interfaces/ssm_parameter_mixin.py
    - Delete src/cdk_factory/interfaces/live_ssm_resolver.py
    - Verify each file no longer exists
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 2.4 Delete migration script from archive
    - Delete archive/migrate_to_enhanced_ssm.py
    - Verify file no longer exists
    - _Requirements: 1.4, 5.1_

  - [ ] 2.5 Delete test files for removed mixins
    - Delete tests/test_enhanced_ssm_migration.py
    - Delete tests/unit/test_enhanced_ssm_config_paths.py
    - Verify files no longer exist
    - _Requirements: 7.2_

- [ ] 3. Phase 3: Documentation Cleanup
  - [ ] 3.1 Delete obsolete documentation files
    - Delete docs/enhanced-ssm-parameter-pattern.md
    - Delete docs/ssm_parameter_pattern.md
    - Verify files no longer exist
    - _Requirements: 4.2, 4.3_

  - [ ] 3.2 Update archive/README.md to remove enhanced SSM migration references
    - Locate section about enhanced SSM migration (around lines 12-15)
    - Replace with note that migration was never completed
    - Update to reference StandardizedSsmMixin as the current approach
    - _Requirements: 5.2_

  - [ ] 3.3 Update samples/ssm_parameter_sharing/README.md
    - Replace references from SsmParameterMixin to StandardizedSsmMixin
    - Add note about IStack inheritance
    - Verify documentation is accurate
    - _Requirements: 4.3_

  - [ ] 3.4 Verify SSM_RESOLUTION_PATTERNS.md needs no changes
    - Read src/cdk_factory/interfaces/SSM_RESOLUTION_PATTERNS.md
    - Confirm it already references only StandardizedSsmMixin
    - No modifications needed
    - _Requirements: 4.1_

- [ ] 4. Phase 4: Post-Cleanup Verification
  - [ ] 4.1 Search for orphaned references to deleted classes
    - Search for "EnhancedSsmParameterMixin" in src/, docs/, tests/, samples/
    - Search for "SsmParameterMixin" (excluding "StandardizedSsmMixin") in src/, docs/, tests/, samples/
    - Search for "LiveSsmResolver" in src/, docs/, tests/, samples/
    - Report any findings (excluding external project directories)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 4.2 Verify StandardizedSsmMixin methods available via IStack
    - Create verification script to import IStack and StandardizedSsmMixin
    - Assert IStack has setup_ssm_integration method
    - Assert IStack has process_ssm_imports method
    - Assert IStack has export_ssm_parameters method
    - Assert IStack has get_ssm_imported_value method
    - _Requirements: 3.1, 3.2_

  - [ ]* 4.3 Run verification script
    - Execute the verification script created in 4.2
    - Confirm all assertions pass
    - _Requirements: 3.1, 3.2_

  - [ ] 4.4 Run post-cleanup test suite
    - Execute pytest excluding deleted test files
    - Save results to post_cleanup_test_results.txt
    - Save exit code to post_cleanup_exit_code.txt
    - Compare exit codes with baseline
    - Verify no new test failures introduced
    - _Requirements: 3.4, 7.1, 7.3, 7.4_

  - [ ]* 4.5 Verify stack synthesis works
    - Synthesize a sample stack that uses SSM parameters
    - Verify CDK synthesis succeeds with no errors
    - Confirm SSM parameter references are correctly generated
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 5. Phase 5: Commit and Review
  - [ ] 5.1 Review all changes with git
    - Run git status to see all modified/deleted files
    - Run git diff to review modifications
    - Run git ls-files --deleted to verify expected deletions
    - Confirm changes match the design document
    - _Requirements: All requirements_

  - [ ] 5.2 Stage and commit changes
    - Stage all changes with git add -A
    - Create commit with descriptive message
    - Include list of deleted files in commit message
    - Reference requirements document
    - _Requirements: All requirements_

  - [ ] 5.3 Push branch and prepare for PR
    - Push cleanup branch to remote
    - Document verification results
    - Prepare PR description with checklist
    - _Requirements: All requirements_

## Notes

- Tasks marked with `*` are optional verification tasks that can be skipped for faster execution
- Each phase must complete successfully before proceeding to the next phase
- If any verification fails, stop immediately and investigate before proceeding
- The cleanup is designed to be safe with no breaking changes to existing stacks
- All stacks continue to use StandardizedSsmMixin via IStack inheritance
- Rollback is available at any point via git reset
- External project references (my-app-real-estate-iac) are out of scope and should be ignored
