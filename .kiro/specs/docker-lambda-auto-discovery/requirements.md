# Requirements Document

## Introduction

Replace the fragmented Docker Lambda image update tooling with a unified auto-discovery framework in cdk-factory. Today, two separate tools handle Docker Lambda image updates:

1. **Repo-triggered updates** — `LambdaImageUpdater` in Acme-SaaS-DevOps-CDK reads `docker-images.json` to update Docker Lambdas when a specific ECR repo is built/pushed. Each project must manually list every Docker Lambda's SSM parameter path per deployment. This doesn't scale — when SSM naming conventions change, every project breaks, and adding a new Docker Lambda requires manual config edits across repos.

2. **Post-deployment refresh** — `lambda_boto3_utilities.py` in Acme-SaaS-Application (legacy IaC, reference only) runs as a CDK pipeline post-deployment step. It uses `get_parameters_by_path` on the SSM prefix to discover all Docker Lambda ARNs, then calls `update_function_code` with the same image URI to force a cold-start refresh after IaC deployments.

Additionally, production and higher environments use **locked version tags** (e.g., `"3.3.29"`) per lambda defined in `.docker-locked-versions.json`, while lower environments (dev, beta, integration) use floating tags like `"dev"` or `"latest"`. The current tooling has no unified support for this tag strategy — locked versions are handled by a separate `lock-versions.py` script and pipeline config inheritance (`__inherits__`), disconnected from the update tooling.

The solution adds a discovery manifest SSM parameter that the CDK lambda stack exports during deployment. A new unified CLI utility in cdk-factory replaces both `LambdaImageUpdater` and the legacy `lambda_boto3_utilities.py` pattern, supporting repo-triggered updates, post-deployment refresh, locked version tags, and multi-account/multi-environment targeting from a single tool.

**Implementation targets:**
- **cdk-factory** — Unified CLI utility and lambda stack manifest export
- **acme-SaaS-IaC** — Pipeline integration (post-deployment step using the Unified CLI)
- **Acme-SaaS-DevOps-CDK** — Consumer migration (replace `LambdaImageUpdater` with Unified CLI)

**Reference only (not modified):**
- **Acme-SaaS-Application** — Legacy IaC; `lambda_boto3_utilities.py` is the pattern being replaced, not updated

## Glossary

- **Lambda_Stack**: The cdk-factory stack module (`lambda_stack.py`) that provisions AWS Lambda functions and exports their ARNs to SSM Parameter Store
- **Docker_Lambda**: A Lambda function configured with `docker.file` or `docker.image` in its resource config, deployed from an ECR container image
- **Discovery_Manifest**: A JSON-formatted SSM parameter that maps ECR repo names to lists of Docker Lambda SSM paths within a given namespace
- **SSM_Namespace**: The configurable prefix path in SSM Parameter Store under which a lambda stack exports its parameters (e.g., `acme-saas/beta/lambda/metrics`)
- **ECR_Repo_Name**: The full ECR repository name as specified in a lambda resource config's `ecr.name` field (e.g., `acme-analytics/v3/acme-services`)
- **docker-images.json**: The per-project configuration file that defines which ECR images map to which Lambda deployments
- **Unified_CLI**: The single command-line utility in cdk-factory that handles both repo-triggered updates and post-deployment refresh of Docker Lambda images
- **Locked_Versions_Config**: A JSON file (e.g., `.docker-locked-versions.json`) that maps individual Docker Lambda names to pinned ECR image version tags for production and higher environments
- **Floating_Tag**: A mutable ECR image tag (e.g., `dev`, `beta`, `latest`) used in lower environments that always points to the most recent image push
- **Pinned_Tag**: An immutable semver ECR image tag (e.g., `3.3.29`) assigned to a specific Docker Lambda in the Locked_Versions_Config for production environments
- **Refresh_Mode**: An update mode where the Unified_CLI re-deploys each Docker Lambda with its current image URI (same image, forcing a container cold start) without changing the tag
- **LambdaImageUpdater**: The existing Python tool in Acme-SaaS-DevOps-CDK that reads `docker-images.json` and updates Docker Lambda functions with new ECR image URIs (to be replaced by the Unified_CLI)
- **lambda_boto3_utilities**: The existing Python utility in Acme-SaaS-Application (legacy IaC, reference only — not being modified) that discovers Docker Lambdas via SSM `get_parameters_by_path` and refreshes their images post-deployment. The pattern it implements is being replaced by the Unified_CLI in acme-SaaS-IaC.

## Requirements

### Requirement 1: Export Discovery Manifest to SSM

**User Story:** As a DevOps engineer, I want the Lambda_Stack to automatically export a discovery manifest SSM parameter during deployment, so that consumers can discover all Docker Lambdas for a given ECR repo without hardcoded paths.

#### Acceptance Criteria

1. WHEN the Lambda_Stack deploys with `ssm.auto_export` enabled and the stack contains one or more Docker_Lambda resources, THE Lambda_Stack SHALL create an SSM parameter at `/{namespace}/docker-lambdas/manifest` containing a JSON object that maps each ECR_Repo_Name to a list of Lambda SSM path prefixes.
2. THE Discovery_Manifest SHALL use the JSON structure `{"ecr_repo_name": ["/{namespace}/{lambda-name}"], ...}` where each entry maps an ECR_Repo_Name to the list of Docker_Lambda path prefixes that use that ECR repo.
3. WHEN multiple Docker_Lambda resources in the same stack reference the same ECR_Repo_Name, THE Lambda_Stack SHALL group all of those Lambda path prefixes under a single ECR_Repo_Name key in the Discovery_Manifest.
4. WHEN multiple Docker_Lambda resources in the same stack reference different ECR_Repo_Name values, THE Lambda_Stack SHALL include a separate key for each distinct ECR_Repo_Name in the Discovery_Manifest.
5. WHEN the Lambda_Stack deploys with `ssm.auto_export` enabled but contains zero Docker_Lambda resources, THE Lambda_Stack SHALL skip creation of the Discovery_Manifest SSM parameter.
6. IF the `ssm.namespace` configuration is missing when `ssm.auto_export` is true, THEN THE Lambda_Stack SHALL raise a `ValueError` with a message identifying the stack name and the missing configuration.

### Requirement 2: Export ECR Repo Metadata per Docker Lambda

**User Story:** As a DevOps engineer, I want the Lambda_Stack to export the ECR repository name as SSM metadata alongside each Docker Lambda's ARN, so that discovery tooling can filter and group Docker Lambdas by their source ECR repo.

#### Acceptance Criteria

1. WHEN the Lambda_Stack deploys a Docker_Lambda with `ssm.auto_export` enabled, THE Lambda_Stack SHALL create an SSM parameter at `/{namespace}/{lambda-name}/ecr-repo` containing the ECR_Repo_Name value from the lambda resource config.
2. THE Lambda_Stack SHALL create the `ecr-repo` SSM parameter using `STANDARD` tier.
3. WHEN a Docker_Lambda resource config does not specify an `ecr.name` field, THE Lambda_Stack SHALL skip creation of the `ecr-repo` SSM parameter for that Docker_Lambda.
4. FOR ALL Docker_Lambda resources with `ssm.auto_export` enabled and a valid `ecr.name`, THE Lambda_Stack SHALL export an `ecr-repo` parameter whose value matches the `ecr.name` field in the resource config.

### Requirement 3: Discover Docker Lambdas by ECR Repo Name

**User Story:** As a DevOps engineer, I want the Unified_CLI to discover all Docker Lambda ARNs for a given ECR repo by reading the discovery manifest from SSM, so that I no longer need to hardcode individual SSM parameter paths in `docker-images.json`.

#### Acceptance Criteria

1. WHEN a deployment entry in `docker-images.json` contains an `ssm_namespace` field instead of an `ssm_parameter` field, THE Unified_CLI SHALL read the Discovery_Manifest from `/{ssm_namespace}/docker-lambdas/manifest` in the target account and region.
2. WHEN the Discovery_Manifest is retrieved, THE Unified_CLI SHALL parse the JSON content and look up the `repo_name` from the image config to find all matching Docker_Lambda path prefixes.
3. WHEN matching path prefixes are found, THE Unified_CLI SHALL resolve the Lambda ARN from `{path_prefix}/arn` for each discovered Docker_Lambda and update each Lambda function with the new image URI.
4. IF the Discovery_Manifest SSM parameter does not exist at the expected path, THEN THE Unified_CLI SHALL log a descriptive error message including the attempted SSM path and the target account and region.
5. IF the Discovery_Manifest does not contain an entry for the specified ECR_Repo_Name, THEN THE Unified_CLI SHALL log a warning message identifying the ECR_Repo_Name and the namespace, and skip the deployment without failing the overall run.
6. WHEN a deployment entry contains an `ssm_parameter` field (legacy format), THE Unified_CLI SHALL continue to resolve the Lambda ARN directly from that SSM parameter path, preserving backward compatibility.

### Requirement 4: Simplify docker-images.json Configuration

**User Story:** As a DevOps engineer, I want to specify only the ECR repo name, account, region, and tag in `docker-images.json` without listing individual SSM parameter paths, so that adding new Docker Lambdas requires zero config changes in consuming projects.

#### Acceptance Criteria

1. THE Unified_CLI SHALL accept deployment entries in `docker-images.json` that contain `ssm_namespace` (a string specifying the SSM namespace prefix) as an alternative to `ssm_parameter`.
2. WHEN a deployment entry contains `ssm_namespace`, THE Unified_CLI SHALL treat the combination of `account`, `region`, `ssm_namespace`, and `tag` as a complete deployment specification.
3. WHEN a deployment entry contains both `ssm_parameter` and `ssm_namespace`, THE Unified_CLI SHALL use `ssm_namespace` (auto-discovery mode) and log an informational message that `ssm_parameter` is being ignored.
4. THE Unified_CLI SHALL validate that each deployment entry contains either `ssm_parameter` or `ssm_namespace`, and IF neither is present, THEN THE Unified_CLI SHALL report a validation error identifying the image and deployment index.

### Requirement 5: Support Multiple Namespace Discovery per Deployment

**User Story:** As a DevOps engineer, I want to specify multiple SSM namespaces for a single ECR repo deployment, so that I can update Docker Lambdas across multiple lambda stacks that share the same ECR image.

#### Acceptance Criteria

1. THE Unified_CLI SHALL accept `ssm_namespaces` (plural) as an array of namespace strings in a deployment entry, as an alternative to the singular `ssm_namespace`.
2. WHEN a deployment entry contains `ssm_namespaces`, THE Unified_CLI SHALL query the Discovery_Manifest in each namespace and aggregate all discovered Docker_Lambda path prefixes before performing updates.
3. WHEN a deployment entry contains the singular `ssm_namespace`, THE Unified_CLI SHALL treat the value as a single-element list and follow the same discovery logic as `ssm_namespaces`.
4. IF any single namespace in `ssm_namespaces` fails to resolve its Discovery_Manifest, THEN THE Unified_CLI SHALL log a warning for that namespace and continue processing the remaining namespaces.

### Requirement 6: Dry Run Support for Auto-Discovery

**User Story:** As a DevOps engineer, I want the dry-run mode to show all discovered Docker Lambdas and their resolved ARNs without making changes, so that I can verify the auto-discovery results before performing actual updates.

#### Acceptance Criteria

1. WHEN the Unified_CLI runs in dry-run mode with auto-discovery enabled, THE Unified_CLI SHALL display each discovered Docker_Lambda path prefix, the resolved Lambda ARN, and the new image URI that would be applied.
2. WHEN the Unified_CLI runs in dry-run mode with auto-discovery enabled, THE Unified_CLI SHALL display the total count of Docker Lambdas discovered per ECR_Repo_Name per namespace.
3. WHEN the Unified_CLI runs in dry-run mode, THE Unified_CLI SHALL perform SSM reads to discover and resolve Lambda ARNs but SHALL NOT call the Lambda `update_function_code` API.

### Requirement 7: Discovery Manifest Content Accuracy

**User Story:** As a DevOps engineer, I want the discovery manifest to accurately reflect the current set of Docker Lambdas in a stack, so that the auto-discovery mechanism returns correct and complete results.

#### Acceptance Criteria

1. FOR ALL Docker_Lambda resources in a Lambda_Stack with `ssm.auto_export` enabled, THE Discovery_Manifest SHALL contain a path prefix entry for every Docker_Lambda in the stack.
2. FOR ALL entries in the Discovery_Manifest, each path prefix SHALL correspond to a Docker_Lambda that has a valid `/arn` SSM parameter exported by the same stack.
3. WHEN a Docker_Lambda is removed from a stack config and the stack is redeployed, THE Lambda_Stack SHALL produce an updated Discovery_Manifest that excludes the removed Docker_Lambda path prefix.
4. THE Discovery_Manifest SSM parameter SHALL use `STANDARD` tier to remain within free-tier SSM limits.

### Requirement 8: Locked Version Tag Support

**User Story:** As a DevOps engineer, I want the Unified_CLI to support pinned version tags per Docker Lambda for production environments, so that higher environments use exact, auditable image versions while lower environments continue using floating tags.

#### Acceptance Criteria

1. THE Unified_CLI SHALL accept a `--locked-versions` CLI argument specifying the path to a Locked_Versions_Config JSON file.
2. WHEN `--locked-versions` is provided, THE Unified_CLI SHALL read the Locked_Versions_Config and match each discovered Docker_Lambda name against the `name` field in the config entries.
3. WHEN a matching entry is found in the Locked_Versions_Config, THE Unified_CLI SHALL use the `tag` value from that entry as the image tag for that specific Docker_Lambda, overriding the deployment-level `tag` value.
4. WHEN a matching entry is found in the Locked_Versions_Config but the `tag` value is empty, THE Unified_CLI SHALL skip that Docker_Lambda and log an informational message indicating the lambda is excluded from Docker image updates.
5. WHEN no matching entry is found in the Locked_Versions_Config for a discovered Docker_Lambda, THE Unified_CLI SHALL fall back to the deployment-level `tag` value.
6. WHEN `--locked-versions` is not provided, THE Unified_CLI SHALL use the deployment-level `tag` value for all discovered Docker Lambdas.
7. WHEN the Unified_CLI runs in dry-run mode with `--locked-versions`, THE Unified_CLI SHALL display the resolved tag source (locked config vs deployment-level) for each Docker_Lambda.

### Requirement 9: Post-Deployment Refresh Mode

**User Story:** As a DevOps engineer, I want the Unified_CLI to support a refresh mode that re-deploys all Docker Lambdas with their current image URI (forcing a cold start), so that post-IaC-deployment image refresh can use the same tool as repo-triggered updates.

#### Acceptance Criteria

1. THE Unified_CLI SHALL accept a `--refresh` CLI flag that enables Refresh_Mode.
2. WHEN Refresh_Mode is enabled, THE Unified_CLI SHALL discover Docker Lambdas using the same SSM auto-discovery mechanism (Discovery_Manifest or `get_parameters_by_path` on the namespace).
3. WHEN Refresh_Mode is enabled, THE Unified_CLI SHALL retrieve the current image URI for each discovered Docker_Lambda by calling the Lambda `get_function` API, then call `update_function_code` with that same image URI.
4. WHEN Refresh_Mode is enabled and `--locked-versions` is also provided, THE Unified_CLI SHALL use the locked version tag to build the image URI instead of reading the current image URI from the Lambda function.
5. WHEN Refresh_Mode is enabled, THE Unified_CLI SHALL tag each updated Lambda function with a `LastImageRefresh` timestamp and a `RefreshedBy` tag value of `deployment-pipeline`.
6. IF the current image URI cannot be retrieved for a Docker_Lambda in Refresh_Mode, THEN THE Unified_CLI SHALL log an error for that Lambda and continue processing the remaining Docker Lambdas.

### Requirement 10: Unified CLI as a cdk-factory Utility

**User Story:** As a DevOps engineer, I want the unified Docker Lambda update tool to live in cdk-factory as a reusable utility, so that all consuming projects (acme-Services, Acme-SaaS-DevOps-CDK, Acme-SaaS-Application, acme-SaaS-IaC) can use a single implementation.

#### Acceptance Criteria

1. THE Unified_CLI SHALL be implemented as a Python module in the cdk-factory package under `cdk_factory.utilities`.
2. THE Unified_CLI SHALL be executable as a standalone CLI command via `python -m cdk_factory.utilities.docker_lambda_updater`.
3. THE Unified_CLI SHALL accept the following CLI arguments: `--config` (path to docker-images.json), `--ssm-namespace` (direct namespace for post-deployment mode), `--refresh` (enable Refresh_Mode), `--locked-versions` (path to Locked_Versions_Config), `--dry-run` (preview mode), `--image-name` (filter to a specific ECR repo), `--cross-account-role` (IAM role name for cross-account access), `--account` (target AWS account ID), and `--region` (target AWS region).
4. WHEN `--ssm-namespace` is provided without `--config`, THE Unified_CLI SHALL operate in direct namespace mode, discovering and updating all Docker Lambdas under the specified namespace in the specified account and region.
5. WHEN `--config` is provided, THE Unified_CLI SHALL operate in config-driven mode, reading deployment entries from the docker-images.json file.
6. IF neither `--config` nor `--ssm-namespace` is provided, THEN THE Unified_CLI SHALL report a usage error and exit with a non-zero exit code.

### Requirement 11: Multi-Account and Multi-Environment Targeting

**User Story:** As a DevOps engineer, I want a single docker-images.json config to target multiple accounts and environments with different tag strategies per environment, so that one config file drives updates across dev, beta, and production.

#### Acceptance Criteria

1. THE Unified_CLI SHALL process all deployment entries in a docker-images.json `lambda_deployments` array sequentially, where each entry specifies its own `account`, `region`, and `tag` or `ssm_namespace`.
2. WHEN a deployment entry includes a `locked_versions` field (path to a Locked_Versions_Config file), THE Unified_CLI SHALL apply locked version tags for that specific deployment entry, allowing per-environment tag strategies within a single config file.
3. WHEN a deployment entry includes a `role_name` field, THE Unified_CLI SHALL use that IAM role name for cross-account access to that specific deployment target.
4. THE Unified_CLI SHALL assume cross-account IAM roles independently per deployment entry, supporting updates to Docker Lambdas across different AWS accounts in a single run.
5. IF a deployment entry fails (account unreachable, role assumption fails), THEN THE Unified_CLI SHALL log the error for that deployment entry and continue processing the remaining entries.

### Requirement 12: Pipeline Post-Deployment Integration

**User Story:** As a DevOps engineer, I want the Unified_CLI to be callable as a CDK pipeline post-deployment shell step, so that it can replace the existing `lambda_boto3_utilities.py` script in Acme-SaaS-Application pipeline stages.

#### Acceptance Criteria

1. THE Unified_CLI SHALL support execution via environment variables as an alternative to CLI arguments, accepting `SSM_DOCKER_LAMBDAS_PATH` (namespace), `AWS_ACCOUNT_NUMBER`, `AWS_REGION`, and `CROSS_ACCOUNT_ROLE_ARN` for pipeline integration.
2. WHEN environment variables are set and no CLI arguments are provided, THE Unified_CLI SHALL use the environment variable values and operate in direct namespace Refresh_Mode.
3. WHEN both environment variables and CLI arguments are provided, THE Unified_CLI SHALL give precedence to CLI arguments.
4. THE Unified_CLI SHALL exit with code 0 on success and a non-zero exit code on failure, enabling CDK pipeline shell steps to detect failures.
5. THE Unified_CLI SHALL write a summary to stdout including the count of Docker Lambdas discovered, updated successfully, and failed, enabling pipeline log review.

### Requirement 13: Migration Documentation

**User Story:** As a DevOps engineer, I want migration documentation that describes how to adopt the new unified framework, so that other workspaces outside this repo can replace their existing Docker Lambda update tooling.

#### Acceptance Criteria

1. WHEN the Unified_CLI implementation is complete, THE cdk-factory project SHALL include a migration guide document in the repository.
2. THE migration guide SHALL describe the steps to replace `LambdaImageUpdater` usage in Acme-SaaS-DevOps-CDK with the Unified_CLI.
3. THE migration guide SHALL describe how to wire the Unified_CLI into an acme-SaaS-IaC CDK pipeline as a post-deployment shell step, replacing the legacy `lambda_boto3_utilities.py` pattern from Acme-SaaS-Application.
4. THE migration guide SHALL describe how to update `docker-images.json` from the legacy `ssm_parameter` format to the `ssm_namespace` auto-discovery format.
5. THE migration guide SHALL describe how to configure locked version tags for production environments using the `--locked-versions` flag.
6. THE migration guide SHALL describe the pattern clearly enough that it can be applied to other workspaces outside this repo via a prompt-based find/replace approach.
