# Requirements Document

## Introduction

This feature extracts the cross-account target resource destruction logic and supporting infrastructure from the Acme SaaS IaC project's `NcaSaasDeployment` subclass into the `CdkDeploymentCommand` base class in cdk-factory. The goal is to make cross-account destroy, deployment JSON auto-discovery, interactive failure handling, DNS cleanup, retained resource scanning, and the associated data models available to any project that subclasses `CdkDeploymentCommand`. After extraction, the Acme SaaS IaC `deploy.py` becomes a thin wrapper providing only project-specific configuration (custom env var loading, validation, display).

## Glossary

- **CdkDeploymentCommand**: The base class in `cdk-factory/src/cdk_factory/commands/deployment_command.py` that provides CDK synth/deploy/diff/destroy operations, env loading, validation, and interactive menus.
- **Deployment_JSON**: A `deployment.*.json` file in the `deployments/` directory that describes an environment's parameters, account, region, profile, and workload configuration.
- **Target_Account**: The AWS account where the workload's CloudFormation stacks are deployed (as opposed to the DevOps/pipeline account).
- **Stage**: A logical grouping of CloudFormation stacks (e.g., persistent-resources, queues, compute, network) used to order deployment and deletion.
- **Stage_Keywords**: A configurable mapping of stage names to keyword patterns used to classify stacks by inspecting their names.
- **Deletion_Order**: The sequence in which stage groups are destroyed, reverse of the pipeline deploy order.
- **Route53Delegation**: An existing utility class in cdk-factory that manages cross-account DNS NS record delegation.
- **Retained_Resource**: An AWS resource (S3 bucket, DynamoDB table, Cognito user pool, Route53 hosted zone, ECR repository) that survives CloudFormation stack deletion due to retention policies.
- **Interactive_Failure_Handling**: A user-facing menu presented when a stack deletion or DNS cleanup fails, offering Wait/Retry, Continue, or Exit options.
- **StackInfo**: A data model representing a discovered CloudFormation stack with its name, status, and classified stage.
- **DeletionResult**: A data model capturing the outcome of a single stack deletion attempt.
- **DnsCleanupResult**: A data model capturing the outcome of DNS delegation cleanup.
- **RetainedResource**: A data model representing a resource that survived stack deletion.
- **Thin_Wrapper**: A project-specific subclass of CdkDeploymentCommand that overrides only project-specific behavior (env var loading, validation, display) while inheriting all generic functionality.

## Requirements

### Requirement 1: Data Models for Cross-Account Destroy

**User Story:** As a library consumer, I want the data models for cross-account destruction (StackInfo, DeletionResult, DnsCleanupResult, RetainedResource) available in cdk-factory, so that I can use them without duplicating definitions.

#### Acceptance Criteria

1. THE CdkDeploymentCommand module SHALL export the StackInfo dataclass with fields: name (str), status (str), stage (str)
2. THE CdkDeploymentCommand module SHALL export the DeletionResult dataclass with fields: stack_name (str), stage (str), status (str), error_reason (Optional[str])
3. THE CdkDeploymentCommand module SHALL export the DnsCleanupResult dataclass with fields: attempted (bool), success (bool), zone_name (str), message (str)
4. THE CdkDeploymentCommand module SHALL export the RetainedResource dataclass with fields: resource_type (str), name (str)

### Requirement 2: Configurable Stage Classification

**User Story:** As a library consumer, I want stage keywords and deletion order to be configurable per-project, so that projects with different stage naming conventions can use the cross-account destroy feature.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL provide a default STAGE_KEYWORDS class attribute mapping stage names to keyword lists: persistent-resources → [dynamodb, s3-, cognito, route53], queues → [sqs], compute → [lambda, docker], network → [api-gateway, cloudfront]
2. THE CdkDeploymentCommand SHALL provide a default DELETION_ORDER class attribute: [unknown, network, compute, queues, persistent-resources]
3. WHEN a subclass overrides STAGE_KEYWORDS, THE CdkDeploymentCommand SHALL use the subclass value for stack classification
4. WHEN a subclass overrides DELETION_ORDER, THE CdkDeploymentCommand SHALL use the subclass value for deletion sequencing

### Requirement 3: Target Account Profile Selection and Session Creation

**User Story:** As a developer, I want the base class to handle AWS profile selection and boto3 session creation for the target account, so that I do not need to implement this in every project.

#### Acceptance Criteria

1. WHEN no target_profile argument is provided, THE CdkDeploymentCommand SHALL present an interactive menu with the deployment config's aws_profile as the default option and a "Enter custom profile" option
2. WHEN the user selects "Enter custom profile", THE CdkDeploymentCommand SHALL prompt for a profile name via text input
3. WHEN a target_profile argument is provided, THE CdkDeploymentCommand SHALL skip the interactive prompt and use the provided value
4. THE CdkDeploymentCommand SHALL create a boto3 Session using the selected profile name
5. IF the AWS profile does not exist, THEN THE CdkDeploymentCommand SHALL display an error message referencing ~/.aws/config and ~/.aws/credentials and exit with code 1

### Requirement 4: Stack Discovery and Classification

**User Story:** As a developer, I want the base class to discover and classify CloudFormation stacks in the target account by stage, so that stacks can be deleted in the correct dependency order.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL discover CloudFormation stacks matching a prefix of "{workload_name}-{deployment_namespace}-" using the target account session
2. THE CdkDeploymentCommand SHALL filter stacks to only those with status CREATE_COMPLETE, UPDATE_COMPLETE, UPDATE_ROLLBACK_COMPLETE, or ROLLBACK_COMPLETE
3. THE CdkDeploymentCommand SHALL classify each discovered stack into a stage group by matching the stack name suffix against STAGE_KEYWORDS
4. WHEN a stack name does not match any keyword, THE CdkDeploymentCommand SHALL classify the stack as "unknown"
5. THE CdkDeploymentCommand SHALL order stage groups for deletion according to DELETION_ORDER
6. WHEN no stacks are found matching the prefix, THE CdkDeploymentCommand SHALL display a message and exit with code 0

### Requirement 5: Destruction Confirmation Flow

**User Story:** As a developer, I want the base class to require explicit confirmation before destroying target resources, so that accidental destruction is prevented.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL display a warning banner indicating the operation is irreversible, the target account, and the list of stacks grouped by stage
2. THE CdkDeploymentCommand SHALL prompt the user to type the tenant name to confirm destruction
3. WHEN the typed confirmation does not match the tenant name, THE CdkDeploymentCommand SHALL abort and exit with code 1
4. WHEN the --confirm-destroy flag is set, THE CdkDeploymentCommand SHALL skip the confirmation prompt

### Requirement 6: Stage-by-Stage Stack Deletion with Failure Handling

**User Story:** As a developer, I want the base class to delete stacks stage-by-stage with interactive failure handling, so that I can fix issues mid-destruction without losing progress.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL delete stacks one at a time within each stage group, in the order defined by DELETION_ORDER
2. THE CdkDeploymentCommand SHALL poll stack status every 10 seconds until DELETE_COMPLETE, DELETE_FAILED, or timeout
3. WHEN a stack is already in DELETE_IN_PROGRESS state, THE CdkDeploymentCommand SHALL wait for the existing deletion to complete rather than initiating a new delete request
4. IF a stack no longer exists during deletion, THEN THE CdkDeploymentCommand SHALL treat the stack as DELETE_COMPLETE
5. WHEN a stack deletion fails or times out, THE CdkDeploymentCommand SHALL present an interactive menu with three options: Wait/Retry, Continue, Exit
6. WHEN the user selects Wait/Retry, THE CdkDeploymentCommand SHALL pause until the user presses Enter, then retry the deletion
7. WHEN the user selects Continue, THE CdkDeploymentCommand SHALL record the failure and proceed to the next stack
8. WHEN the user selects Exit, THE CdkDeploymentCommand SHALL stop all further deletions and proceed to the summary report
9. WHEN --no-interactive-failures is set, THE CdkDeploymentCommand SHALL auto-continue on failures without prompting
10. THE CdkDeploymentCommand SHALL accept a configurable per-stack deletion timeout via --stack-delete-timeout (default 1800 seconds)

### Requirement 7: DNS Delegation Cleanup

**User Story:** As a developer, I want the base class to optionally clean up DNS delegation records in the management account after destroying target resources, so that stale NS records do not remain.

#### Acceptance Criteria

1. WHEN persistent-resources stacks include a route53 stack, THE CdkDeploymentCommand SHALL prompt the user to confirm DNS delegation cleanup
2. WHEN the user confirms, THE CdkDeploymentCommand SHALL call Route53Delegation.delete_ns_records using HOSTED_ZONE_NAME, MANAGEMENT_ACCOUNT_ROLE_ARN, and MGMT_R53_HOSTED_ZONE_ID from environment variables
3. IF DNS cleanup fails, THEN THE CdkDeploymentCommand SHALL present the same interactive failure menu (Wait/Retry, Continue, Exit)
4. WHEN --skip-dns-cleanup is set, THE CdkDeploymentCommand SHALL skip the DNS cleanup prompt entirely

### Requirement 8: Retained Resources Discovery

**User Story:** As a developer, I want the base class to scan for resources that survived stack deletion, so that I know what requires manual cleanup.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL check for retained S3 buckets by matching known bucket names from deployment parameters and prefix-scanning with "{workload_name}-{tenant_name}-"
2. THE CdkDeploymentCommand SHALL check for retained DynamoDB tables by matching known table names from deployment parameters and prefix-scanning
3. THE CdkDeploymentCommand SHALL check for retained Cognito user pools by prefix-scanning pool names
4. THE CdkDeploymentCommand SHALL check for retained Route53 hosted zones by matching the HOSTED_ZONE_NAME parameter
5. THE CdkDeploymentCommand SHALL check for retained ECR repositories by prefix-scanning repository names
6. IF a resource check fails due to permissions or API errors, THEN THE CdkDeploymentCommand SHALL log a warning and continue checking other resource types

### Requirement 9: Summary Report

**User Story:** As a developer, I want the base class to display a summary report after destruction, so that I can see the outcome of each stack deletion, DNS cleanup, and retained resources at a glance.

#### Acceptance Criteria

1. THE CdkDeploymentCommand SHALL display each stack's deletion result with a success (✓) or failure (✗) indicator, stack name, and status
2. THE CdkDeploymentCommand SHALL display the DNS delegation cleanup result when attempted
3. THE CdkDeploymentCommand SHALL display retained resources with resource type and name, along with a manual cleanup warning
4. WHEN the operation was aborted by the user, THE CdkDeploymentCommand SHALL label the report as partial and include a re-run hint
5. THE CdkDeploymentCommand SHALL return exit code 0 when all stacks deleted and DNS cleanup succeeded, and exit code 1 when any failure occurred

### Requirement 10: Destroy Sub-Menu and Operation Dispatch

**User Story:** As a developer, I want the base class to present a destroy sub-menu (Pipeline vs Target Resources) and dispatch to the correct destroy flow, so that subclasses get this behavior automatically.

#### Acceptance Criteria

1. WHEN the user selects "destroy" from the operation menu, THE CdkDeploymentCommand SHALL present a sub-menu with "Pipeline" and "Target Resources" options
2. WHEN the user selects "Pipeline", THE CdkDeploymentCommand SHALL execute the existing CDK destroy flow (cdk destroy --all --force)
3. WHEN the user selects "Target Resources", THE CdkDeploymentCommand SHALL execute the cross-account target destroy flow
4. WHEN the --destroy-target CLI flag is set, THE CdkDeploymentCommand SHALL skip the sub-menu and go directly to target resource destruction

### Requirement 11: CLI Arguments for Cross-Account Destroy

**User Story:** As a developer, I want the base class main() method to accept CLI arguments for cross-account destroy, so that the feature can be used non-interactively in CI/CD pipelines.

#### Acceptance Criteria

1. THE CdkDeploymentCommand.main() SHALL accept --destroy-target (boolean flag) to skip the destroy sub-menu
2. THE CdkDeploymentCommand.main() SHALL accept --target-profile (string) to specify the AWS profile for the target account
3. THE CdkDeploymentCommand.main() SHALL accept --confirm-destroy (boolean flag) to skip the confirmation prompt
4. THE CdkDeploymentCommand.main() SHALL accept --skip-dns-cleanup (boolean flag) to skip DNS cleanup
5. THE CdkDeploymentCommand.main() SHALL accept --stack-delete-timeout (integer, default 1800) to set per-stack deletion timeout
6. THE CdkDeploymentCommand.main() SHALL accept --no-interactive-failures (boolean flag) to auto-continue on failures

### Requirement 12: Thin Wrapper Subclass Pattern

**User Story:** As a library consumer, I want the Acme SaaS IaC deploy.py to become a thin wrapper after extraction, so that it demonstrates the intended subclass pattern for other projects.

#### Acceptance Criteria

1. THE Thin_Wrapper subclass SHALL override set_environment_variables to load env vars from Deployment_JSON parameters, standard fields, code repository config, and management account config
2. THE Thin_Wrapper subclass SHALL override validate_required_variables to add project-specific checks (e.g., TODO placeholder detection)
3. THE Thin_Wrapper subclass SHALL override display_configuration_summary to show project-specific fields
4. THE Thin_Wrapper subclass SHALL override select_environment to display deployment descriptions alongside names
5. THE Thin_Wrapper subclass SHALL inherit all cross-account destroy functionality from CdkDeploymentCommand without overriding any destroy-related methods
6. THE Thin_Wrapper subclass SHALL define project-specific required_vars that extend or replace the base class defaults
