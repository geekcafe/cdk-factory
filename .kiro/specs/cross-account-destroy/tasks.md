# Implementation Plan: Cross-Account Destroy

## Overview

Implement the cross-account target resource destruction feature for the Acme SaaS IaC deployment CLI. All new functionality is added to `Acme-SaaS-IaC/cdk/deploy.py` (subclass methods) and `cdk-factory/src/cdk_factory/utilities/route53_delegation.py` (new `delete_ns_records` method). No base class changes are needed. Tasks follow the design document's method decomposition and build incrementally from data models through orchestration.

## Tasks

- [x] 1. Add data models, constants, and CLI arguments
  - [x] 1.1 Add data models and constants to `deploy.py`
    - Add `dataclasses` import and define `StackInfo`, `DeletionResult`, `DnsCleanupResult`, `RetainedResource` dataclasses
    - Add `STAGE_KEYWORDS` dict and `DELETION_ORDER` list constants
    - Place these above the `NcaSaasDeployment` class definition
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 1.2 Add new CLI arguments to `main()` in `deploy.py`
    - Add `--destroy-target` (store_true), `--target-profile` (str), `--confirm-destroy` (store_true), `--skip-dns-cleanup` (store_true), `--stack-delete-timeout` (int, default 1800), `--no-interactive-failures` (store_true) to the argparse parser
    - Pass the new arguments through to `instance.run()`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

- [x] 2. Implement destroy sub-menu and operation dispatch
  - [x] 2.1 Override `select_operation` in `NcaSaasDeployment`
    - When user selects "destroy", present a sub-menu with "Pipeline" and "Target Resources" options
    - Return "destroy" for Pipeline, "destroy-target" for Target Resources
    - Handle Escape/Ctrl-C cancellation with exit code 1
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.2 Override `run` in `NcaSaasDeployment`
    - Accept the new CLI arguments (`destroy_target`, `target_profile`, `confirm_destroy`, `skip_dns_cleanup`, `no_interactive_failures`, `stack_delete_timeout`)
    - When operation is "destroy-target" or `--destroy-target` flag is set, call `run_target_destroy`
    - When operation is "destroy" (Pipeline selected), call existing `run_cdk_destroy`
    - For all other operations, delegate to `super().run()`
    - _Requirements: 1.2, 1.3, 9.1_

- [x] 3. Implement profile selection and session creation
  - [x] 3.1 Implement `_select_target_profile`
    - Read `aws_profile` from the deployment config as the default
    - Present two options: use default profile or enter custom profile name
    - If `--target-profile` CLI arg is provided, skip the prompt
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Implement `_create_target_session`
    - Create a `boto3.Session` using the selected profile name
    - Validate the profile exists; on failure, display descriptive error and exit with code 1
    - _Requirements: 2.3, 2.4, 2.5_

- [x] 4. Implement stack discovery and classification
  - [x] 4.1 Implement `_discover_target_stacks`
    - Use CloudFormation `list_stacks` paginator with `StackStatusFilter` for active statuses only (`CREATE_COMPLETE`, `UPDATE_COMPLETE`, `UPDATE_ROLLBACK_COMPLETE`, `ROLLBACK_COMPLETE`)
    - Filter results by stack prefix pattern `{WORKLOAD_NAME}-{DEPLOYMENT_NAMESPACE}-`
    - Return list of stack summary dicts
    - _Requirements: 3.1, 3.2, 3.3, 11.1_

  - [x] 4.2 Implement `_classify_stacks_by_stage`
    - Classify stack names into stage groups using `STAGE_KEYWORDS` keyword matching on the stack name suffix
    - Assign unmatched stacks to the "unknown" group
    - Return ordered dict of stage → stack list
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.3 Implement `_get_deletion_order`
    - Return stages in reverse dependency order: unknown → network → compute → queues → persistent-resources
    - Use the `DELETION_ORDER` constant
    - _Requirements: 4.2_

  - [ ]* 4.4 Write property test for stack discovery filter correctness
    - **Property 1: Stack discovery filter correctness**
    - Use `hypothesis` to generate arbitrary stack summaries with random names and statuses
    - Verify only stacks matching the prefix AND having an allowed status are returned
    - Verify stacks with `DELETE_COMPLETE` status are excluded (idempotent re-run)
    - **Validates: Requirements 3.1, 3.2, 3.3, 11.1**

  - [ ]* 4.5 Write property test for stage classification and deletion ordering
    - **Property 2: Stage classification and deletion ordering**
    - Use `hypothesis` to generate arbitrary stack name suffixes
    - Verify each stack is assigned to exactly one stage group
    - Verify `_get_deletion_order` always returns stages in order: unknown → network → compute → queues → persistent-resources
    - Verify unmatched suffixes go to "unknown"
    - **Validates: Requirements 4.2, 4.3**

- [x] 5. Checkpoint - Ensure discovery and classification work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement stack deletion execution and failure handling
  - [x] 6.1 Implement `_delete_single_stack`
    - Check current stack status; if `DELETE_IN_PROGRESS`, wait instead of re-issuing delete
    - If stack does not exist (already deleted), return `DELETE_COMPLETE`
    - Otherwise issue `delete_stack` and call `_wait_for_stack_delete`
    - _Requirements: 5.1, 11.4_

  - [x] 6.2 Implement `_wait_for_stack_delete`
    - Poll `describe_stacks` every 10 seconds until `DELETE_COMPLETE`, `DELETE_FAILED`, or timeout
    - Handle "does not exist" ClientError as `DELETE_COMPLETE`
    - Display progress updates during polling
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 6.3 Implement `_prompt_failure_action`
    - Display failure details (stack name, status, reason)
    - Present three options: "Wait/Retry", "Continue", "Exit"
    - When `--no-interactive-failures` is set, auto-return "continue"
    - _Requirements: 10.1, 10.2, 10.7_

  - [x] 6.4 Implement `_delete_stage_stacks`
    - Iterate stacks in a stage, calling `_delete_single_stack` for each
    - On failure/timeout, call `_prompt_failure_action`
    - Handle retry loop (Wait/Retry), skip (Continue), and abort (Exit)
    - Return list of result dicts and `should_exit` flag
    - _Requirements: 5.1, 5.2, 10.3, 10.4, 10.5_

  - [ ]* 6.5 Write unit tests for stack deletion and failure handling
    - Test `_delete_single_stack` with DELETE_IN_PROGRESS (waits), already-deleted (returns complete), normal delete
    - Test `_wait_for_stack_delete` with DELETE_COMPLETE, DELETE_FAILED, timeout scenarios
    - Test `_prompt_failure_action` returns correct action strings
    - Test `_delete_stage_stacks` retry loop, continue, and exit behaviors
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.7, 11.4_

- [x] 7. Implement confirmation flow
  - [x] 7.1 Implement `_confirm_destruction`
    - Display warning banner, account number, and stacks grouped by stage in deletion order
    - Prompt user to type the tenant name to confirm
    - When `--confirm-destroy` flag is set, skip the prompt
    - When `--destroy-target` is used without `--confirm-destroy`, still require the prompt
    - Return True if confirmed, abort with exit code 1 if incorrect or cancelled
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 9.5_

- [x] 8. Implement DNS delegation cleanup
  - [x] 8.1 Add `delete_ns_records` method to `Route53Delegation` in `cdk-factory/src/cdk_factory/utilities/route53_delegation.py`
    - Check if NS record exists for the given record name (idempotency check)
    - If found, delete the NS record set using `change_resource_record_sets` with DELETE action
    - Return True if deleted, False if record not found (already cleaned up)
    - _Requirements: 6.2, 6.3, 6.7_

  - [x] 8.2 Implement `_prompt_dns_cleanup` in `deploy.py`
    - Check if a Route53 stack was present in the discovered stacks
    - Prompt user for DNS cleanup confirmation
    - When `--skip-dns-cleanup` flag is set, skip the prompt and return False
    - _Requirements: 6.1, 9.4_

  - [x] 8.3 Implement `_delete_dns_delegation` in `deploy.py`
    - Read management account config from env vars (`MANAGEMENT_ACCOUNT_ROLE_ARN`, `MGMT_R53_HOSTED_ZONE_ID`, `HOSTED_ZONE_NAME`)
    - Call `Route53Delegation().delete_ns_records(...)` with management role ARN
    - Include retry loop with interactive failure prompt on errors
    - Handle role assumption failures gracefully with interactive prompt
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 10.6_

  - [ ]* 8.4 Write unit tests for DNS delegation cleanup
    - Test `delete_ns_records` with record found (deletes), record not found (returns False)
    - Test `_delete_dns_delegation` with success, already cleaned up, failure with retry
    - Test role assumption failure triggers interactive prompt
    - _Requirements: 6.2, 6.3, 6.7, 6.8, 10.6_

- [x] 9. Checkpoint - Ensure deletion and DNS cleanup work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement retained resources discovery and summary report
  - [x] 10.1 Implement `_discover_retained_resources`
    - Query target account for S3 buckets, DynamoDB tables, Cognito user pools, Route53 hosted zones, and ECR repositories
    - Match by known resource names from deployment config AND workload/tenant prefix pattern
    - Wrap each resource type check in its own try/except for graceful error handling
    - Return list of `RetainedResource` entries; never attempt to delete anything
    - _Requirements: 12.1, 12.2, 12.3, 12.6, 12.7_

  - [x] 10.2 Implement `_display_summary_report`
    - Print summary table with each stack's name and final status (✓/✗ indicators)
    - Include DNS delegation cleanup status when attempted
    - Include Retained Resources section when resources are found; show clean message when none found
    - When `partial=True`, indicate operation was aborted early and suggest re-running
    - Return exit code: 0 for all success, 1 for any failure or partial abort
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 12.4, 12.5_

  - [ ]* 10.3 Write unit tests for retained resources and summary report
    - Test `_discover_retained_resources` finds matching resources and handles API errors gracefully
    - Test `_display_summary_report` with all success (exit 0), mixed results (exit 1), partial abort
    - Test retained resources section appears in summary when resources found
    - Test no retained resources shows clean message
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 12.1, 12.2, 12.4, 12.5, 12.7_

- [x] 11. Implement orchestrator and wire everything together
  - [x] 11.1 Implement `run_target_destroy` orchestrator method
    - Wire the full flow: profile selection → session creation → stack discovery → classification → confirmation → stage-by-stage deletion in reverse order → DNS cleanup prompt → DNS deletion → retained resources discovery → summary report
    - Handle early exit when no stacks found (exit 0)
    - Handle user abort (Exit) at any failure prompt — display partial summary and exit 1
    - Pass through all CLI flags (`confirm_destroy`, `skip_dns_cleanup`, `no_interactive_failures`, `stack_delete_timeout`)
    - _Requirements: 1.3, 3.4, 3.5, 4.2, 5.1, 5.2, 6.1, 7.1, 8.1, 9.1, 9.5, 10.5, 11.1, 11.2, 12.1_

  - [ ]* 11.2 Write integration tests for end-to-end target destroy flow
    - Test full flow with mocked CloudFormation and Route53 APIs
    - Test re-run scenario: first run partially fails, second run discovers only remaining stacks
    - Test non-interactive mode with `--destroy-target --confirm-destroy --no-interactive-failures`
    - _Requirements: 5.1, 5.2, 6.3, 9.1, 9.3, 9.6, 11.1, 11.2, 11.3_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- All new code goes in `deploy.py` (subclass) and `route53_delegation.py` (new method) — no base class changes
- Property tests validate the two pure-logic functions (stack filtering and stage classification)
- Unit tests cover interactive flows and conditional logic using mocks
- The design uses Python throughout, matching the existing codebase
