# Implementation Plan: Extract Deployment to CdkFactory

## Overview

Migrate cross-account target resource destruction logic from `Acme-SaaS-IaC/cdk/deploy.py` (NcaSaasDeployment subclass) into the `CdkDeploymentCommand` base class in `cdk-factory/src/cdk_factory/commands/deployment_command.py`. After migration, rewrite `deploy.py` as a thin wrapper keeping only project-specific overrides.

## Tasks

- [x] 1. Add dependencies and data models to cdk-factory
  - [x] 1.1 Add boto3 and botocore to pyproject.toml dependencies
    - Add `"boto3"` and `"botocore"` to the `dependencies` list in `cdk-factory/pyproject.toml`
    - These are needed for CloudFormation, S3, DynamoDB, Cognito, Route53, and ECR API calls in the base class
    - _Requirements: Design — Dependency Changes_

  - [x] 1.2 Add data model dataclasses to deployment_command.py
    - Add `StackInfo`, `DeletionResult`, `DnsCleanupResult`, and `RetainedResource` dataclasses to `cdk-factory/src/cdk_factory/commands/deployment_command.py` as module-level exports alongside `EnvironmentConfig`
    - Copy them exactly from `Acme-SaaS-IaC/cdk/deploy.py` — no structural changes
    - Add `time` to imports, add `import boto3` and `from botocore.exceptions import ClientError, ProfileNotFound`, add `from cdk_factory.utilities.route53_delegation import Route53Delegation`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.3 Add STAGE_KEYWORDS and DELETION_ORDER class attributes to CdkDeploymentCommand
    - Add `STAGE_KEYWORDS` dict and `DELETION_ORDER` list as class-level attributes on `CdkDeploymentCommand`
    - Default values: `STAGE_KEYWORDS = {"persistent-resources": ["dynamodb", "s3-", "cognito", "route53"], "queues": ["sqs"], "compute": ["lambda", "docker"], "network": ["api-gateway", "cloudfront"]}`
    - Default values: `DELETION_ORDER = ["unknown", "network", "compute", "queues", "persistent-resources"]`
    - _Requirements: 2.1, 2.2_

  - [ ]* 1.4 Write property test for stack classification (Property 1)
    - **Property 1: Stack classification respects active STAGE_KEYWORDS**
    - Generate random STAGE_KEYWORDS dicts and stack name lists, verify `_classify_stacks_by_stage` assigns each stack to the correct stage or "unknown"
    - Use Hypothesis library with minimum 100 iterations
    - Test file: `cdk-factory/tests/unit/test_deployment_command_properties.py`
    - **Validates: Requirements 2.3, 4.3, 4.4**

  - [ ]* 1.5 Write property test for deletion ordering (Property 2)
    - **Property 2: Deletion ordering follows active DELETION_ORDER**
    - Generate random DELETION_ORDER lists and classified stack dicts, verify `_get_deletion_order` returns tuples in the exact DELETION_ORDER sequence
    - Use Hypothesis library with minimum 100 iterations
    - Test file: `cdk-factory/tests/unit/test_deployment_command_properties.py`
    - **Validates: Requirements 2.4, 4.5**

- [x] 2. Checkpoint — Verify data models and class attributes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Add profile selection, session creation, and stack discovery methods
  - [x] 3.1 Add _select_target_profile() to CdkDeploymentCommand
    - Move `_select_target_profile` from `deploy.py` to `deployment_command.py` as a method on `CdkDeploymentCommand`
    - No logic changes — uses `_interactive_select` and `input()` for profile selection
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 3.2 Add _create_target_session() to CdkDeploymentCommand
    - Move `_create_target_session` from `deploy.py` to `deployment_command.py`
    - Handles `ProfileNotFound` with error message referencing `~/.aws/config` and `~/.aws/credentials`
    - _Requirements: 3.4, 3.5_

  - [x] 3.3 Add _discover_target_stacks() to CdkDeploymentCommand
    - Move `_discover_target_stacks` from `deploy.py` to `deployment_command.py`
    - Uses CloudFormation paginator with `StackStatusFilter` for allowed statuses
    - _Requirements: 4.1, 4.2_

  - [x] 3.4 Add _classify_stacks_by_stage() to CdkDeploymentCommand
    - Move `_classify_stacks_by_stage` from `deploy.py` to `deployment_command.py`
    - Change references from module-level `STAGE_KEYWORDS` to `self.STAGE_KEYWORDS` to support subclass overrides
    - _Requirements: 4.3, 4.4_

  - [x] 3.5 Add _get_deletion_order() to CdkDeploymentCommand
    - Move `_get_deletion_order` from `deploy.py` to `deployment_command.py`
    - Change references from module-level `DELETION_ORDER` to `self.DELETION_ORDER` to support subclass overrides
    - _Requirements: 4.5_

  - [x] 3.6 Add _build_stack_prefix() hook method to CdkDeploymentCommand
    - Add new hook method that builds the CloudFormation stack name prefix: `"{WORKLOAD_NAME}-{DEPLOYMENT_NAMESPACE}-"`
    - Subclasses can override for different naming conventions
    - _Requirements: 4.1 (prefix construction)_

- [x] 4. Add stack deletion and failure handling methods
  - [x] 4.1 Add _delete_single_stack() to CdkDeploymentCommand
    - Move `_delete_single_stack` from `deploy.py` to `deployment_command.py`
    - Handles DELETE_IN_PROGRESS from previous runs, "does not exist" as DELETE_COMPLETE
    - _Requirements: 6.1, 6.3, 6.4_

  - [x] 4.2 Add _wait_for_stack_delete() to CdkDeploymentCommand
    - Move `_wait_for_stack_delete` from `deploy.py` to `deployment_command.py`
    - Polls every 10 seconds, returns (status, error_reason) tuple
    - _Requirements: 6.2, 6.10_

  - [x] 4.3 Add _prompt_failure_action() to CdkDeploymentCommand
    - Move `_prompt_failure_action` from `deploy.py` to `deployment_command.py`
    - Presents Wait/Retry, Continue, Exit options; auto-continues when `no_interactive_failures` is set
    - _Requirements: 6.5, 6.6, 6.7, 6.8, 6.9_

  - [x] 4.4 Add _delete_stage_stacks() to CdkDeploymentCommand
    - Move `_delete_stage_stacks` from `deploy.py` to `deployment_command.py`
    - Orchestrates per-stage deletion with retry loop and failure handling
    - _Requirements: 6.1, 6.5, 6.6, 6.7, 6.8_

- [x] 5. Add confirmation, DNS cleanup, retained resources, and summary report methods
  - [x] 5.1 Add _confirm_destruction() to CdkDeploymentCommand
    - Move `_confirm_destruction` from `deploy.py` to `deployment_command.py`
    - Displays warning banner, requires tenant name confirmation, supports `--confirm-destroy` bypass
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.2 Add _prompt_dns_cleanup() and _delete_dns_delegation() to CdkDeploymentCommand
    - Move both DNS methods from `deploy.py` to `deployment_command.py`
    - `_prompt_dns_cleanup` checks for route53 stacks and prompts user
    - `_delete_dns_delegation` uses `Route53Delegation.delete_ns_records` with env vars
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 5.3 Add _discover_retained_resources() to CdkDeploymentCommand
    - Move `_discover_retained_resources` from `deploy.py` to `deployment_command.py`
    - Checks S3, DynamoDB, Cognito, Route53, ECR with error resilience per resource type
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 5.4 Add _display_summary_report() to CdkDeploymentCommand
    - Move `_display_summary_report` from `deploy.py` to `deployment_command.py`
    - Shows ✓/✗ per stack, DNS result, retained resources, partial label, exit code
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 5.5 Write property test for summary report exit code (Property 3)
    - **Property 3: Summary report exit code correctness**
    - Generate random DeletionResult lists and optional DnsCleanupResult, verify exit code is 0 iff all DELETE_COMPLETE and DNS success
    - Use Hypothesis library with minimum 100 iterations
    - Test file: `cdk-factory/tests/unit/test_deployment_command_properties.py`
    - **Validates: Requirements 9.5**

  - [ ]* 5.6 Write property test for summary report indicators (Property 4)
    - **Property 4: Summary report shows correct indicators for each result**
    - Generate random DeletionResult lists, capture `_print` output, verify ✓ for DELETE_COMPLETE and ✗ for non-complete statuses
    - Use Hypothesis library with minimum 100 iterations
    - Test file: `cdk-factory/tests/unit/test_deployment_command_properties.py`
    - **Validates: Requirements 9.1**

- [x] 6. Checkpoint — Verify all migrated methods
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update select_operation(), run(), main(), and add run_target_destroy()
  - [x] 7.1 Update select_operation() in CdkDeploymentCommand with destroy sub-menu
    - Modify the existing `select_operation()` to present a sub-menu when "destroy" is selected: "Pipeline" returns `"destroy"`, "Target Resources" returns `"destroy-target"`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 7.2 Add run_target_destroy() orchestrator to CdkDeploymentCommand
    - Move `run_target_destroy` from `deploy.py` to `deployment_command.py`
    - Orchestrates the full flow: profile → session → discovery → classification → confirmation → deletion → DNS → retained → summary
    - Use `_build_stack_prefix()` hook instead of inline prefix construction
    - _Requirements: 3.1, 4.1, 5.1, 6.1, 7.1, 8.1, 9.1_

  - [x] 7.3 Update run() in CdkDeploymentCommand with destroy-target dispatch
    - Modify the existing `run()` to check for `_destroy_target` flag and dispatch to `run_target_destroy()` when operation is `"destroy-target"`
    - Pass through `_target_profile`, `_confirm_destroy`, `_skip_dns_cleanup`, `_no_interactive_failures`, `_stack_delete_timeout` from instance attributes
    - _Requirements: 10.3, 10.4_

  - [x] 7.4 Update main() in CdkDeploymentCommand with cross-account destroy CLI arguments
    - Add six CLI arguments to the base `main()`: `--destroy-target`, `--target-profile`, `--confirm-destroy`, `--skip-dns-cleanup`, `--stack-delete-timeout`, `--no-interactive-failures`
    - Store parsed values as instance attributes for `run()` to access
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 8. Checkpoint — Verify base class is complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Rewrite NcaSaasDeployment as thin wrapper
  - [x] 9.1 Remove all migrated methods and data models from deploy.py
    - Remove `StackInfo`, `DeletionResult`, `DnsCleanupResult`, `RetainedResource` dataclasses
    - Remove module-level `STAGE_KEYWORDS` and `DELETION_ORDER` constants
    - Remove all destroy-related methods: `run_target_destroy`, `_select_target_profile`, `_create_target_session`, `_discover_target_stacks`, `_classify_stacks_by_stage`, `_get_deletion_order`, `_delete_single_stack`, `_wait_for_stack_delete`, `_prompt_failure_action`, `_delete_stage_stacks`, `_confirm_destruction`, `_prompt_dns_cleanup`, `_delete_dns_delegation`, `_discover_retained_resources`, `_display_summary_report`
    - Remove the `select_operation()` override (base class now handles destroy sub-menu)
    - Remove the `run()` override (base class now handles destroy-target dispatch)
    - Remove the `main()` override (base class now handles cross-account destroy CLI args)
    - _Requirements: 12.5_

  - [x] 9.2 Simplify imports in deploy.py
    - Remove `argparse`, `time`, `boto3`, `botocore`, `Route53Delegation` imports
    - Remove `dataclass` import (no longer defining dataclasses locally)
    - Keep: `json`, `os`, `sys`, `Path`, `Dict`, `List`, `Tuple`
    - Import `CdkDeploymentCommand` and `EnvironmentConfig` from cdk_factory
    - _Requirements: 12.5_

  - [x] 9.3 Verify thin wrapper retains only project-specific overrides
    - Confirm `NcaSaasDeployment` keeps only: `__init__`, `required_vars`, `set_environment_variables`, `validate_required_variables`, `select_environment`, `display_configuration_summary`, `load_env_file`, `STANDARD_ENV_VARS`
    - Confirm all destroy-related methods resolve to `CdkDeploymentCommand` via inheritance
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 10. Final checkpoint — Verify end-to-end
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each logical group
- Property tests validate universal correctness properties from the design document using Hypothesis
- The migration is method-by-method: each method moves with no logic changes except replacing module-level constants with `self.STAGE_KEYWORDS` / `self.DELETION_ORDER`
- The `_build_stack_prefix()` hook is the only net-new method (not in deploy.py today) — it extracts inline prefix construction for subclass customization
