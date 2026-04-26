# Implementation Plan: Retained Resource Cleanup

## Overview

Add an interactive post-destruction cleanup flow to `CdkDeploymentCommand` in `deployment_command.py`. The flow prompts operators to review and delete retained AWS resources (S3 buckets, DynamoDB tables) after stack destruction, with graceful handling of unsupported resource types. All changes go into `cdk-factory/src/cdk_factory/commands/deployment_command.py`.

## Tasks

- [ ] 1. Add CleanupResult dataclass
  - [ ] 1.1 Define the `CleanupResult` dataclass alongside the existing `RetainedResource` dataclass in `deployment_command.py`
    - Fields: `resource_type: str`, `resource_name: str`, `status: str` (DELETED/FAILED/SKIPPED/UNSUPPORTED), `error_reason: Optional[str] = None`
    - Use `@dataclass` decorator, import already exists
    - _Requirements: 9.1, 9.2, 9.3_

- [ ] 2. Add S3 bucket deletion method
  - [ ] 2.1 Implement `_delete_s3_bucket(self, session: boto3.Session, bucket_name: str) -> CleanupResult` on `CdkDeploymentCommand`
    - Create S3 client from session
    - Paginate `list_object_versions(Bucket=bucket_name)` to collect all Versions and DeleteMarkers
    - Batch `delete_objects` (up to 1000 per call) for each page
    - Call `delete_bucket(Bucket=bucket_name)` after emptying
    - Return `CleanupResult(status="DELETED")` on success
    - Wrap in `try/except Exception` — return `CleanupResult(status="FAILED", error_reason=str(e))` on failure
    - _Requirements: 4.1, 4.2, 4.3, 8.1, 8.2_

  - [ ]* 2.2 Write property test for S3 bucket emptying completeness
    - **Property 3: S3 bucket emptying completeness**
    - **Validates: Requirements 4.1, 4.2**

- [ ] 3. Add DynamoDB table deletion method
  - [ ] 3.1 Implement `_delete_dynamodb_table(self, session: boto3.Session, table_name: str) -> CleanupResult` on `CdkDeploymentCommand`
    - Create DynamoDB client from session
    - Call `describe_table(TableName=table_name)` to check `DeletionProtectionEnabled`
    - If protected: prompt "Deletion protection is enabled on '{table_name}'. Disable and delete? (y/N)"
      - If confirmed: call `update_table(TableName=table_name, DeletionProtectionEnabled=False)` then `delete_table`
      - If declined: return `CleanupResult(status="SKIPPED")`
    - If not protected: call `delete_table(TableName=table_name)` directly
    - Return `CleanupResult(status="DELETED")` on success
    - Wrap in `try/except Exception` — return `CleanupResult(status="FAILED", error_reason=str(e))` on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.1, 8.2_

- [ ] 4. Add unsupported resource handler
  - [ ] 4.1 Implement `_handle_unsupported_resource(self, resource: RetainedResource) -> CleanupResult` on `CdkDeploymentCommand`
    - Display type-specific messages for known unsupported types (Cognito User Pool, Route53 Hosted Zone, ECR Repository)
    - Display generic message for unknown types: "Automated deletion of {resource_type} is not currently supported. Please delete manually or open a GitHub issue/contribution."
    - Return `CleanupResult(status="UNSUPPORTED")` for all unsupported types
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 4.2 Write property test for unsupported resource type handling
    - **Property 5: Unsupported resource type handling**
    - **Validates: Requirements 6.4, 6.5**

- [ ] 5. Add per-resource selection method
  - [ ] 5.1 Implement `_select_resources_for_cleanup(self, retained_resources: List[RetainedResource]) -> List[RetainedResource]` on `CdkDeploymentCommand`
    - Iterate each `RetainedResource`, display type and name
    - Prompt "Delete {resource_type} '{name}'? (y/N)" for each
    - Collect resources where user responds "y" or "yes" (case-insensitive)
    - Return the selected list (may be empty)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 5.2 Write property test for affirmative input acceptance
    - **Property 1: Affirmative input acceptance**
    - **Validates: Requirements 1.2, 2.3, 3.3**

  - [ ]* 5.3 Write property test for non-affirmative input rejection
    - **Property 2: Non-affirmative input rejection**
    - **Validates: Requirements 1.3, 2.4, 3.4**

- [ ] 6. Add batch confirmation and execution method
  - [ ] 6.1 Implement `_confirm_and_execute_cleanup(self, selected: List[RetainedResource], session: boto3.Session) -> List[CleanupResult]` on `CdkDeploymentCommand`
    - Display summary of selected resources (type and name for each)
    - Prompt "Proceed with deletion? (y/N)"
    - If declined: print "Cleanup cancelled" and return empty list
    - If confirmed: dispatch each resource to the appropriate handler using a dispatch dict (`"S3 Bucket"` → `_delete_s3_bucket`, `"DynamoDB Table"` → `_delete_dynamodb_table`, all others → `_handle_unsupported_resource`)
    - Wrap each dispatch in `try/except Exception` for error isolation
    - Print error inline via `self._print` on failure, continue to next resource
    - Return list of all `CleanupResult` entries
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 8.1, 8.2, 8.3_

  - [ ]* 6.2 Write property test for error isolation
    - **Property 4: Error isolation preserves remaining resource processing**
    - **Validates: Requirements 4.3, 5.6, 8.1, 8.2**

- [ ] 7. Add cleanup summary display method
  - [ ] 7.1 Implement `_display_cleanup_summary(self, cleanup_results: List[CleanupResult]) -> None` on `CdkDeploymentCommand`
    - Print section header "Cleanup Results"
    - For DELETED: print success indicator (✓) with resource type and name
    - For FAILED: print failure indicator (✗) with resource type, name, and error_reason
    - For SKIPPED/UNSUPPORTED: print skipped indicator (⊘) with resource type and name
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 7.2 Write property test for cleanup summary rendering correctness
    - **Property 6: Cleanup summary rendering correctness**
    - **Validates: Requirements 7.2, 7.3, 7.4**

- [ ] 8. Add top-level cleanup entry point
  - [ ] 8.1 Implement `_prompt_cleanup(self, retained_resources: List[RetainedResource], session: boto3.Session, no_interactive_failures: bool) -> Optional[List[CleanupResult]]` on `CdkDeploymentCommand`
    - If `no_interactive_failures` is True: return `None` immediately (skip cleanup in non-interactive mode)
    - If `retained_resources` is empty: return `None` (no prompt needed)
    - Prompt "Would you like to clean up retained resources? (y/N)"
    - If declined: return `None`
    - If accepted: call `_select_resources_for_cleanup` → if none selected, print "No resources selected for deletion" and return empty list → otherwise call `_confirm_and_execute_cleanup` → call `_display_cleanup_summary` on results → return results
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.5, 10.3, 10.4_

- [ ] 9. Checkpoint - Verify all new methods
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Integrate cleanup into run_target_destroy
  - [ ] 10.1 Modify `run_target_destroy` to call `_prompt_cleanup` between step 9 (retained resources) and step 10 (summary report)
    - After retained resource discovery and before `_display_summary_report`
    - Only call when `retained_resources` is not None and not aborted
    - Pass the existing `session` and `no_interactive_failures` flag
    - Store the returned `cleanup_results`
    - _Requirements: 10.1, 10.3, 10.4_

  - [ ] 10.2 Update `_display_summary_report` to accept an optional `cleanup_results: Optional[List[CleanupResult]] = None` parameter
    - Render the cleanup summary section (using `_display_cleanup_summary`) before the retained resources section
    - Only render when `cleanup_results` is not None and non-empty
    - Pass `cleanup_results` from `run_target_destroy` to `_display_summary_report`
    - _Requirements: 7.5, 10.2_

- [ ] 11. Final verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All code changes go into `cdk-factory/src/cdk_factory/commands/deployment_command.py`
- All tests go into `cdk-factory/tests/unit/test_retained_resource_cleanup.py`
- Each task references specific requirements for traceability
- Property tests use the `hypothesis` library (already in the project)
- Checkpoints ensure incremental validation
