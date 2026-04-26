# Requirements Document

## Introduction

After the `run_target_destroy` operation completes, the summary report displays "Retained Resources" — AWS resources that survived CloudFormation stack deletion due to `DeletionPolicy: Retain`. Currently this information is purely informational. This feature adds an interactive post-destruction flow that walks the user through each retained resource and optionally deletes it, with resource-type-specific handling for S3 buckets, DynamoDB tables, Cognito user pools, Route53 hosted zones, and ECR repositories.

The cleanup flow integrates into the existing `run_target_destroy` orchestrator in `CdkDeploymentCommand`, after retained resource discovery and before (or as part of) the final summary report.

## Glossary

- **CdkDeploymentCommand**: The base class in `cdk-factory/src/cdk_factory/commands/deployment_command.py` that provides CDK synth/deploy/diff/destroy operations, environment loading, validation, and interactive menus.
- **Retained_Resource**: A `RetainedResource` dataclass representing an AWS resource that survived stack deletion, with `resource_type` and `name` fields.
- **Cleanup_Flow**: The interactive post-destruction sequence that prompts the user to review and optionally delete each retained resource.
- **Cleanup_Result**: A data structure capturing the outcome of a single resource cleanup attempt, including the resource identity, whether deletion was attempted, and whether it succeeded or failed.
- **Cleanup_Summary**: A report displayed after all cleanup operations complete, showing success or failure status for each resource that was selected for deletion.
- **Deletion_Protection**: A DynamoDB table setting that prevents the table from being deleted until the protection is explicitly disabled.
- **Supported_Resource_Type**: A resource type for which automated deletion is implemented (S3 Bucket, DynamoDB Table).
- **Unsupported_Resource_Type**: A resource type for which automated deletion is not implemented (Cognito User Pool, Route53 Hosted Zone, ECR Repository, or any unknown type).

## Requirements

### Requirement 1: Cleanup Prompt After Retained Resource Discovery

**User Story:** As an operator, I want to be prompted to clean up retained resources after the destroy operation discovers them, so that I can remove leftover resources without switching to the AWS console.

#### Acceptance Criteria

1. WHEN the `run_target_destroy` operation discovers one or more Retained_Resource entries, THE CdkDeploymentCommand SHALL prompt the user with "Would you like to clean up retained resources? (y/N)"
2. WHEN the user responds with "y" or "yes" (case-insensitive), THE CdkDeploymentCommand SHALL initiate the Cleanup_Flow
3. WHEN the user responds with "N", an empty response, or any value other than "y" or "yes", THE CdkDeploymentCommand SHALL skip the Cleanup_Flow and proceed to the summary report
4. WHEN the `run_target_destroy` operation discovers zero Retained_Resource entries, THE CdkDeploymentCommand SHALL skip the cleanup prompt entirely
5. WHEN the `run_target_destroy` operation was aborted before retained resource discovery, THE CdkDeploymentCommand SHALL skip the cleanup prompt entirely

### Requirement 2: Per-Resource Interactive Selection

**User Story:** As an operator, I want to review each retained resource individually and choose whether to delete it, so that I have fine-grained control over which resources are removed.

#### Acceptance Criteria

1. WHEN the Cleanup_Flow is initiated, THE CdkDeploymentCommand SHALL iterate through each Retained_Resource one at a time
2. FOR EACH Retained_Resource, THE CdkDeploymentCommand SHALL display the resource type and name, then prompt "Delete {resource_type} '{name}'? (y/N)"
3. WHEN the user responds with "y" or "yes" (case-insensitive) for a resource, THE CdkDeploymentCommand SHALL mark that resource for deletion
4. WHEN the user responds with "N", an empty response, or any value other than "y" or "yes" for a resource, THE CdkDeploymentCommand SHALL skip that resource
5. WHEN all resources have been reviewed and no resources were selected for deletion, THE CdkDeploymentCommand SHALL display "No resources selected for deletion" and skip the confirmation and execution phases

### Requirement 3: Batch Confirmation Before Execution

**User Story:** As an operator, I want to see a summary of all resources selected for deletion and confirm before any deletions execute, so that I have a final safety check.

#### Acceptance Criteria

1. WHEN one or more resources have been selected for deletion, THE CdkDeploymentCommand SHALL display a summary listing each selected resource's type and name
2. AFTER displaying the summary, THE CdkDeploymentCommand SHALL prompt "Proceed with deletion? (y/N)"
3. WHEN the user confirms with "y" or "yes" (case-insensitive), THE CdkDeploymentCommand SHALL execute the deletions
4. WHEN the user responds with "N", an empty response, or any value other than "y" or "yes", THE CdkDeploymentCommand SHALL cancel all deletions and display "Cleanup cancelled"

### Requirement 4: S3 Bucket Deletion

**User Story:** As an operator, I want retained S3 buckets to be emptied and deleted automatically, so that I do not have to manually empty and remove them.

#### Acceptance Criteria

1. WHEN an S3 Bucket is selected for deletion, THE CdkDeploymentCommand SHALL delete all objects in the bucket including all object versions
2. AFTER all objects and versions are removed, THE CdkDeploymentCommand SHALL delete the bucket itself
3. IF an error occurs during S3 bucket emptying or deletion, THEN THE CdkDeploymentCommand SHALL record the failure in the Cleanup_Result and continue processing remaining resources

### Requirement 5: DynamoDB Table Deletion

**User Story:** As an operator, I want retained DynamoDB tables to be deleted with automatic handling of deletion protection, so that I do not have to manually disable protection and delete each table.

#### Acceptance Criteria

1. WHEN a DynamoDB Table is selected for deletion, THE CdkDeploymentCommand SHALL check whether deletion protection is enabled on the table
2. WHEN deletion protection is enabled, THE CdkDeploymentCommand SHALL prompt "Deletion protection is enabled on '{table_name}'. Disable and delete? (y/N)"
3. WHEN the user confirms disabling deletion protection, THE CdkDeploymentCommand SHALL disable deletion protection and then delete the table
4. WHEN the user declines disabling deletion protection, THE CdkDeploymentCommand SHALL skip the table and record it as skipped in the Cleanup_Result
5. WHEN deletion protection is not enabled, THE CdkDeploymentCommand SHALL delete the table directly
6. IF an error occurs during DynamoDB table deletion or protection disabling, THEN THE CdkDeploymentCommand SHALL record the failure in the Cleanup_Result and continue processing remaining resources

### Requirement 6: Unsupported Resource Type Handling

**User Story:** As an operator, I want clear feedback when a resource type cannot be automatically deleted, so that I know which resources require manual cleanup.

#### Acceptance Criteria

1. WHEN a Cognito User Pool is selected for deletion, THE CdkDeploymentCommand SHALL display "Automated deletion of Cognito User Pools is not currently supported. Please delete manually or open a GitHub issue."
2. WHEN a Route53 Hosted Zone is selected for deletion, THE CdkDeploymentCommand SHALL display "Automated deletion of Route53 Hosted Zones is not currently supported. Please delete manually or open a GitHub issue."
3. WHEN an ECR Repository is selected for deletion, THE CdkDeploymentCommand SHALL display "Automated deletion of ECR Repositories is not currently supported. Please delete manually or open a GitHub issue."
4. WHEN a resource with an unrecognized resource type is selected for deletion, THE CdkDeploymentCommand SHALL display "Automated deletion of {resource_type} is not currently supported. Please delete manually or open a GitHub issue/contribution."
5. THE CdkDeploymentCommand SHALL record unsupported resource types as "UNSUPPORTED" in the Cleanup_Result

### Requirement 7: Cleanup Summary Report

**User Story:** As an operator, I want to see a summary of cleanup results after all deletions complete, so that I know which resources were successfully deleted and which failed.

#### Acceptance Criteria

1. AFTER all cleanup operations complete, THE CdkDeploymentCommand SHALL display a cleanup summary report
2. FOR EACH resource that was successfully deleted, THE CdkDeploymentCommand SHALL display a success indicator with the resource type and name
3. FOR EACH resource that failed to delete, THE CdkDeploymentCommand SHALL display a failure indicator with the resource type, name, and error reason
4. FOR EACH resource that was skipped (user declined or unsupported), THE CdkDeploymentCommand SHALL display a skipped indicator with the resource type and name
5. THE CdkDeploymentCommand SHALL display the cleanup summary before the final destruction summary report exit

### Requirement 8: Graceful Error Handling

**User Story:** As an operator, I want individual resource deletion failures to not crash the cleanup process, so that remaining resources can still be processed.

#### Acceptance Criteria

1. IF an error occurs during deletion of a single resource, THEN THE CdkDeploymentCommand SHALL log the error, record the failure in the Cleanup_Result, and continue processing the next resource
2. THE CdkDeploymentCommand SHALL not raise unhandled exceptions from individual resource deletion attempts
3. WHEN all cleanup operations complete (including any failures), THE CdkDeploymentCommand SHALL proceed to display the Cleanup_Summary and then the final destruction summary report

### Requirement 9: Cleanup Result Data Model

**User Story:** As a developer extending the cleanup flow, I want a structured data model for cleanup results, so that results can be programmatically inspected and reported.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL represent each cleanup outcome as a Cleanup_Result containing: resource_type (str), resource_name (str), status (str: "DELETED", "FAILED", "SKIPPED", "UNSUPPORTED"), and error_reason (optional str)
2. THE CdkDeploymentCommand SHALL use the Cleanup_Result data model consistently across all resource type handlers
3. THE Cleanup_Result data model SHALL be defined as a dataclass in the deployment_command module alongside the existing RetainedResource dataclass

### Requirement 10: Integration with run_target_destroy Orchestrator

**User Story:** As a developer, I want the cleanup flow to integrate cleanly into the existing destroy orchestrator, so that the feature does not disrupt the existing flow or require changes to the summary report contract.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL execute the Cleanup_Flow after retained resource discovery (step 9 of `run_target_destroy`) and before the final summary report (step 10)
2. THE CdkDeploymentCommand SHALL pass cleanup results to the summary report so that the report can include cleanup status
3. WHEN the `--no-interactive-failures` flag is set, THE CdkDeploymentCommand SHALL skip the cleanup prompt and not initiate the Cleanup_Flow (cleanup requires interactive input)
4. THE CdkDeploymentCommand SHALL use the existing boto3 session from `run_target_destroy` for all cleanup AWS API calls
