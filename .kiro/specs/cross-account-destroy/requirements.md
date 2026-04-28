# Requirements Document

## Introduction

The cross-account-destroy feature extends the existing Acme SaaS IaC deployment CLI (`deploy.py`) to support destroying CloudFormation stacks deployed in target accounts by the CodePipeline. Currently, the "destroy" operation only removes the pipeline stack in the DevOps account. This feature adds the ability to discover and delete the actual workload stacks (DynamoDB, Lambda, S3, API Gateway, Cognito, Route53, SQS) in the target account, clean up DNS delegation records in the management account, and do so in the correct reverse-dependency order.

## Glossary

- **CLI**: The interactive deployment command-line interface implemented in `deploy.py` (subclass of `CdkDeploymentCommand`)
- **DevOps_Account**: The AWS account (974817967438) that hosts CodePipeline and where `cdk destroy` currently operates
- **Target_Account**: The AWS account (e.g., 959096737760 for dev) where workload CloudFormation stacks are deployed by the pipeline
- **Management_Account**: The AWS account (833510414569) that owns the root DNS hosted zone (e.g., `acme.com`)
- **Deployment_Config**: A `deployment.*.json` file containing tenant-specific parameters including `aws_profile`, `workload_name`, `tenant_name`, and account details
- **Stack_Prefix**: The naming pattern `{WORKLOAD_NAME}-{DEPLOYMENT_NAMESPACE}-` used to identify CloudFormation stacks belonging to a specific tenant deployment (e.g., `acme-saas-development-`)
- **Pipeline_Stack**: The CodePipeline CloudFormation stack in the DevOps account (e.g., `v3-acme-saas-development-pipeline`)
- **Target_Stacks**: The CloudFormation stacks deployed by the pipeline into the Target_Account (persistent-resources, queues, compute, network stages)
- **DNS_Delegation_Record**: The NS record set in the Management_Account's parent hosted zone that delegates a subdomain to the Target_Account's child hosted zone
- **Destroy_Sub_Menu**: The interactive sub-menu presented when the user selects the "destroy" operation, offering Pipeline or Target Resources options
- **AWS_Profile**: The named AWS CLI credential profile used to authenticate API calls to a specific account
- **Reverse_Dependency_Order**: The order in which stacks are deleted — the inverse of the pipeline deployment order: network → compute → queues → persistent-resources
- **Retained_Resources**: AWS resources (S3 buckets, DynamoDB tables, Cognito user pools, Route53 hosted zones, ECR repositories) that survive CloudFormation stack deletion due to `DeletionPolicy: Retain` or `USE_EXISTING: true` configurations and may require manual cleanup

## Requirements

### Requirement 1: Destroy Sub-Menu

**User Story:** As a developer, I want the destroy operation to present a sub-menu so that I can choose between destroying the pipeline stack or the target account resources.

#### Acceptance Criteria

1. WHEN the user selects the "destroy" operation in the CLI, THE Destroy_Sub_Menu SHALL present two options: "Pipeline" and "Target Resources"
2. WHEN the user selects "Pipeline" from the Destroy_Sub_Menu, THE CLI SHALL execute the existing pipeline destroy behavior (calling `run_cdk_destroy` against the DevOps_Account)
3. WHEN the user selects "Target Resources" from the Destroy_Sub_Menu, THE CLI SHALL proceed to the target account profile selection flow (Requirement 2)
4. WHEN the user cancels the Destroy_Sub_Menu (Escape or Ctrl-C), THE CLI SHALL exit with a cancellation message and exit code 1

### Requirement 2: Target Account Profile Selection

**User Story:** As a developer, I want to choose which AWS profile to use for target account operations so that I can handle cases where the DevOps and target accounts use different credentials or the same credentials.

#### Acceptance Criteria

1. WHEN the user selects "Target Resources", THE CLI SHALL display the AWS_Profile from the selected Deployment_Config as the default profile option
2. THE CLI SHALL present two options: use the Deployment_Config profile or enter a custom profile name
3. WHEN the user selects the Deployment_Config profile, THE CLI SHALL use that profile for all Target_Account AWS API calls
4. WHEN the user enters a custom profile name, THE CLI SHALL use the custom profile for all Target_Account AWS API calls
5. IF the selected AWS_Profile is not configured in the local AWS CLI configuration, THEN THE CLI SHALL display a descriptive error message and exit with code 1

### Requirement 3: Target Stack Discovery

**User Story:** As a developer, I want the CLI to automatically discover which CloudFormation stacks belong to my tenant deployment so that I do not have to manually specify stack names.

#### Acceptance Criteria

1. WHEN target resource destruction is initiated, THE CLI SHALL query the Target_Account CloudFormation API using the `list_stacks` operation to discover stacks matching the Stack_Prefix pattern
2. THE CLI SHALL filter discovered stacks to include only stacks with status `CREATE_COMPLETE`, `UPDATE_COMPLETE`, `UPDATE_ROLLBACK_COMPLETE`, or `ROLLBACK_COMPLETE`
3. THE CLI SHALL exclude stacks with status `DELETE_COMPLETE` from the discovered results
4. WHEN no matching stacks are found in the Target_Account, THE CLI SHALL display an informational message indicating no stacks were found and exit gracefully with code 0
5. THE CLI SHALL display the list of discovered stacks to the user before proceeding with deletion

### Requirement 4: Reverse Dependency Order Deletion

**User Story:** As a developer, I want stacks to be deleted in reverse dependency order so that dependent resources are removed before the resources they depend on.

#### Acceptance Criteria

1. THE CLI SHALL define the stage ordering as: persistent-resources, queues, compute, network (matching the pipeline deployment order from `config.json`)
2. THE CLI SHALL delete discovered Target_Stacks in Reverse_Dependency_Order: network first, then compute, then queues, then persistent-resources last
3. WHEN a stack name does not match any known stage pattern, THE CLI SHALL assign the stack to a default group that is deleted first (before network)
4. WHEN deleting stacks within the same stage group, THE CLI SHALL delete them in parallel or sequentially (order within a stage is not significant)

### Requirement 5: Stack Deletion Execution

**User Story:** As a developer, I want the CLI to delete CloudFormation stacks using the AWS API so that target account resources are properly cleaned up.

#### Acceptance Criteria

1. THE CLI SHALL use the `delete_stack` CloudFormation API operation to delete each discovered Target_Stack
2. THE CLI SHALL wait for each stack deletion to reach `DELETE_COMPLETE` status before proceeding to the next stage group
3. WHILE a stack deletion is in progress, THE CLI SHALL display progress updates indicating the current stack being deleted and its status
4. THE CLI SHALL implement a configurable timeout (default 30 minutes) for each individual stack deletion wait operation

### Requirement 6: DNS Delegation Cleanup

**User Story:** As a developer, I want the CLI to remove DNS delegation records from the management account so that stale DNS entries do not remain after target resources are destroyed.

#### Acceptance Criteria

1. WHEN target resource destruction includes a Route53 hosted zone stack (persistent-resources stage), THE CLI SHALL prompt the user asking whether to clean up DNS delegation records in the Management_Account
2. WHEN the user confirms DNS cleanup, THE CLI SHALL first check whether the NS record set for the tenant subdomain (e.g., `development.acme.com`) exists in the Management_Account's parent hosted zone before attempting deletion
3. IF the DNS delegation record exists, THEN THE CLI SHALL delete the NS record set from the Management_Account's parent hosted zone
4. THE CLI SHALL use the `MANAGEMENT_ACCOUNT_ROLE_ARN` from `config.json` to assume a cross-account role for Management_Account Route53 operations
5. THE CLI SHALL use the `MGMT_R53_HOSTED_ZONE_ID` from `config.json` to identify the parent hosted zone
6. THE CLI SHALL use the `HOSTED_ZONE_NAME` from the Deployment_Config to identify which NS record set to delete
7. IF the DNS delegation record does not exist in the parent zone, THEN THE CLI SHALL log an informational message indicating the record was already removed and continue without error
8. IF the cross-account role assumption fails, THEN THE CLI SHALL log the error and continue with the remaining destruction steps without failing the overall operation

### Requirement 7: Confirmation Prompt

**User Story:** As a developer, I want the CLI to require explicit confirmation before destroying target resources so that accidental deletions are prevented.

#### Acceptance Criteria

1. WHEN the user has selected "Target Resources" and stacks have been discovered, THE CLI SHALL display a summary of all stacks that will be deleted, grouped by stage
2. THE CLI SHALL prompt the user to type the tenant name (e.g., `development`) to confirm the destruction
3. WHEN the user types the correct tenant name, THE CLI SHALL proceed with stack deletion
4. WHEN the user types an incorrect value or cancels, THE CLI SHALL abort the operation and exit with code 1
5. THE CLI SHALL display a warning message indicating that this operation is irreversible and will delete resources in the Target_Account

### Requirement 8: Destruction Summary Report

**User Story:** As a developer, I want a summary report after the destroy operation completes so that I can verify which resources were successfully removed and which failed.

#### Acceptance Criteria

1. WHEN all stack deletions have been attempted, THE CLI SHALL display a summary report listing each stack and its final status (deleted, failed, timed out)
2. WHEN all stacks are successfully deleted, THE CLI SHALL display a success message and exit with code 0
3. WHEN one or more stack deletions fail, THE CLI SHALL display the failure details and exit with code 1
4. THE CLI SHALL include DNS delegation cleanup status in the summary report when DNS cleanup was attempted

### Requirement 9: Non-Interactive Mode Support

**User Story:** As a developer, I want to run the target resource destruction non-interactively so that it can be used in scripts and CI/CD pipelines.

#### Acceptance Criteria

1. THE CLI SHALL accept a `--destroy-target` command-line flag that selects "Target Resources" destruction without the Destroy_Sub_Menu
2. THE CLI SHALL accept a `--target-profile` command-line argument to specify the AWS_Profile for the Target_Account without interactive prompting
3. THE CLI SHALL accept a `--confirm-destroy` command-line flag that bypasses the confirmation prompt (Requirement 7)
4. THE CLI SHALL accept a `--skip-dns-cleanup` command-line flag that skips the DNS delegation cleanup prompt
5. WHEN `--destroy-target` is used without `--confirm-destroy`, THE CLI SHALL still require the confirmation prompt for safety
6. THE CLI SHALL accept a `--no-interactive-failures` command-line flag that disables the interactive failure prompt (Requirement 10) and falls back to logging failures and continuing, suitable for CI/CD pipelines

### Requirement 10: Interactive Failure Handling

**User Story:** As a developer, I want the CLI to prompt me when a stack deletion or DNS cleanup fails so that I can choose to fix the issue and retry, skip the failed operation, or abort the entire destroy process.

#### Acceptance Criteria

1. WHEN a stack deletion reaches `DELETE_FAILED` status, THE CLI SHALL display the failure reason and present an interactive prompt with three options: "Wait/Retry", "Continue", and "Exit"
2. WHEN a stack deletion exceeds the configured timeout, THE CLI SHALL display a timeout warning and present the same three-option interactive prompt
3. WHEN the user selects "Wait/Retry", THE CLI SHALL pause execution so the user can manually resolve the issue (e.g., empty an S3 bucket, remove a dependency), then retry the `delete_stack` operation for the failed stack
4. WHEN the user selects "Continue", THE CLI SHALL skip the failed stack, record it as failed in the results, and proceed to the next stack or stage
5. WHEN the user selects "Exit", THE CLI SHALL stop the entire destroy operation immediately, display a partial summary report of what was completed, and exit with code 1
6. WHEN DNS delegation cleanup fails (e.g., role assumption failure or API error), THE CLI SHALL present the same three-option interactive prompt (Wait/Retry, Continue, Exit)
7. WHEN the `--no-interactive-failures` flag is set, THE CLI SHALL skip the interactive prompt and automatically select "Continue" for all failures (log and continue behavior)

### Requirement 11: Idempotent Re-Run / Resume

**User Story:** As a developer, I want to be able to re-run the destroy command after a partial failure so that it cleanly picks up where it left off without errors from already-completed operations.

#### Acceptance Criteria

1. WHEN the destroy command is re-run after a partial failure, THE stack discovery (Requirement 3) SHALL naturally exclude already-deleted stacks because `list_stacks` filters by active statuses only (`CREATE_COMPLETE`, `UPDATE_COMPLETE`, `UPDATE_ROLLBACK_COMPLETE`, `ROLLBACK_COMPLETE`)
2. WHEN the destroy command is re-run, THE confirmation prompt (Requirement 7) SHALL display only the remaining active stacks, not previously deleted ones
3. WHEN DNS delegation cleanup is attempted and the NS record has already been removed (by a previous run), THE CLI SHALL detect that the record does not exist and log an informational message indicating it was already cleaned up, without treating it as an error
4. WHEN a stack is in `DELETE_IN_PROGRESS` status from a previous run, THE CLI SHALL wait for it to complete rather than issuing a new `delete_stack` call
5. ALL custom actions performed by the CLI (i.e., actions beyond what CloudFormation handles natively) SHALL be idempotent — safe to execute multiple times with the same result

### Requirement 12: Retained Resources Report

**User Story:** As a developer, I want to see a list of resources that were not destroyed during the process so that I know what remains in the target account and may need manual cleanup.

#### Acceptance Criteria

1. WHEN all stack deletions have completed (regardless of success or failure), THE CLI SHALL query the Target_Account for resources that match the workload/tenant naming pattern but were not removed by CloudFormation stack deletion
2. THE CLI SHALL check for the following retained resource types: S3 buckets, DynamoDB tables, Cognito user pools, Route53 hosted zones, and ECR repositories
3. THE CLI SHALL use the Stack_Prefix naming pattern (e.g., `acme-saas-development-*`) and the known resource names from the Deployment_Config (e.g., `DYNAMODB_APP_TABLE_NAME`, `S3_WORKLOAD_BUCKET_NAME`) to identify matching resources
4. WHEN retained resources are found, THE CLI SHALL display a "Retained Resources" section in the summary report listing each resource with its type and name
5. WHEN no retained resources are found, THE CLI SHALL display a message indicating no retained resources were detected
6. THE retained resources check SHALL be informational only — the CLI SHALL NOT attempt to delete any retained resources
7. THE CLI SHALL handle API errors during retained resource discovery gracefully, logging a warning and continuing without failing the overall operation
