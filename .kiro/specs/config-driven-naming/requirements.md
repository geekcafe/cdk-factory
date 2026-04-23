# Requirements Document

## Introduction

cdk-factory is an open-source CDK library intended to work for any organization, project, or naming convention. Currently, several stacks and utilities contain hardcoded SSM path construction patterns that silently fall back to `deployment.workload_name` / `deployment.environment` when the stack's own `ssm.namespace` or `ssm.imports.namespace` config is missing. This creates org-specific assumptions baked into library code and can produce wrong SSM paths without any error signal.

This feature audits and fixes all hardcoded naming patterns so that every SSM path, resource name, and cross-stack reference is derived exclusively from the stack's JSON config — and missing config values produce a clear, immediate error instead of a silent wrong default.

## Glossary

- **CDK_Factory**: The open-source CDK library that builds AWS CloudFormation stacks from JSON configuration files
- **SSM_Path**: An AWS Systems Manager Parameter Store path used to store and retrieve resource references (e.g., `/my-namespace/lambda/my-func/arn`)
- **SSM_Namespace**: A config-driven prefix string defined in `ssm.namespace` that forms the root of all SSM paths for a stack's exports
- **SSM_Imports_Namespace**: A config-driven prefix string defined in `ssm.imports.namespace` that forms the root of all SSM paths a stack imports from other stacks
- **Stack_Config**: The JSON configuration object for a single stack, containing `name`, `module`, `ssm`, and resource-specific blocks
- **Deployment_Config**: The deployment-level configuration containing `workload_name`, `environment`, and other deployment metadata
- **Fallback_Pattern**: Code that silently constructs an SSM path from `deployment.workload_name` and `deployment.environment` when the stack's SSM config is missing
- **Config_Validator**: A validation component that checks configuration completeness before stack synthesis begins
- **Hardcoded_Path**: An SSM path or resource name pattern assembled in Python code rather than derived from the stack's JSON config

## Requirements

### Requirement 1: Eliminate Fallback Patterns in Lambda Stack SSM Export

**User Story:** As a library consumer, I want the Lambda stack's SSM export to derive paths exclusively from `ssm.namespace` config, so that I don't get silently wrong SSM paths when namespace is missing.

#### Acceptance Criteria

1. WHEN `ssm.auto_export` is true and `ssm.namespace` is defined, THE CDK_Factory Lambda stack SHALL construct SSM export paths using the configured SSM_Namespace as the prefix
2. WHEN `ssm.auto_export` is true and `ssm.namespace` is not defined, THE CDK_Factory Lambda stack SHALL raise a configuration error identifying the missing `ssm.namespace` field and the stack name
3. THE CDK_Factory Lambda stack SHALL NOT fall back to `deployment.workload_name` or `deployment.environment` to construct SSM export paths

### Requirement 2: Eliminate Fallback Patterns in Lambda Stack Route Metadata Export

**User Story:** As a library consumer, I want the Lambda stack's route metadata SSM export to use the same config-driven namespace as Lambda ARN exports, so that path construction is consistent and config-driven.

#### Acceptance Criteria

1. WHEN `ssm.auto_export` is true and `ssm.namespace` is defined, THE CDK_Factory Lambda stack SHALL construct route metadata SSM paths using the configured SSM_Namespace as the prefix
2. WHEN `ssm.auto_export` is true and `ssm.namespace` is not defined, THE CDK_Factory Lambda stack SHALL raise a configuration error identifying the missing `ssm.namespace` field
3. THE CDK_Factory Lambda stack SHALL NOT fall back to `ssm.workload`, `ssm.organization`, or Deployment_Config properties to construct route metadata SSM paths

### Requirement 3: Eliminate Fallback Patterns in API Gateway Lambda Discovery

**User Story:** As a library consumer, I want the API Gateway stack's Lambda ARN discovery to derive SSM paths exclusively from `ssm.imports.namespace`, so that cross-stack references are fully config-driven.

#### Acceptance Criteria

1. WHEN a route specifies `lambda_name` and `ssm.imports.namespace` is defined, THE CDK_Factory API Gateway stack SHALL construct the Lambda ARN SSM path using the configured SSM_Imports_Namespace
2. WHEN a route specifies `lambda_name` and `ssm.imports.namespace` is not defined, THE CDK_Factory API Gateway stack SHALL raise a configuration error identifying the missing `ssm.imports.namespace` field and the route's `lambda_name`
3. THE CDK_Factory API Gateway stack SHALL NOT fall back to `ssm.imports.workload`, `ssm.imports.organization`, or Deployment_Config properties to construct Lambda discovery SSM paths

### Requirement 4: Eliminate Fallback Patterns in API Gateway Integration Utility

**User Story:** As a library consumer, I want the API Gateway integration utility's Cognito SSM path resolution to be fully config-driven, so that it does not silently construct wrong paths from deployment properties.

#### Acceptance Criteria

1. WHEN `ssm_path` is set to `"auto"` and `ssm.imports.namespace` is defined in the stack config, THE CDK_Factory API Gateway integration utility SHALL construct the Cognito user pool ARN SSM path using the configured SSM_Imports_Namespace
2. WHEN `ssm_path` is set to `"auto"` and `ssm.imports.namespace` is not defined, THE CDK_Factory API Gateway integration utility SHALL raise a configuration error identifying the missing `ssm.imports.namespace` field
3. THE CDK_Factory API Gateway integration utility SHALL NOT fall back to `deployment.workload_name` or `deployment.environment` to construct Cognito SSM paths

### Requirement 5: Eliminate Fallback Patterns in RUM Stack

**User Story:** As a library consumer, I want the RUM stack's Cognito identity pool SSM import to be config-driven, so that it does not silently construct paths from deployment properties.

#### Acceptance Criteria

1. WHEN the RUM stack needs to import a Cognito identity pool ID and `ssm.namespace` is defined, THE CDK_Factory RUM stack SHALL construct the SSM import path using the configured SSM_Namespace
2. WHEN the RUM stack needs to import a Cognito identity pool ID and `ssm.namespace` is not defined, THE CDK_Factory RUM stack SHALL raise a configuration error identifying the missing `ssm.namespace` field
3. THE CDK_Factory RUM stack SHALL NOT fall back to `deployment.workload_name` or `deployment.environment` to construct Cognito SSM import paths

### Requirement 6: Eliminate Hardcoded SSM Path in CloudFront IP Gate

**User Story:** As a library consumer, I want the CloudFront distribution construct's IP gate Lambda@Edge SSM path to be config-driven, so that it does not assume a `/{environment}/{workload_name}/lambda-edge/version-arn` path structure.

#### Acceptance Criteria

1. WHEN IP gating is enabled and `ip_gate_function_ssm_path` is explicitly provided in the CloudFront config, THE CDK_Factory CloudFront construct SHALL use the provided SSM path
2. WHEN IP gating is enabled and `ip_gate_function_ssm_path` is not provided, THE CDK_Factory CloudFront construct SHALL raise a configuration error stating that `ip_gate_function_ssm_path` is required when IP gating is enabled
3. THE CDK_Factory CloudFront construct SHALL NOT auto-derive a default SSM path from `environment` and `workload_name`

### Requirement 7: Eliminate Hardcoded SSM Path in ACM Config

**User Story:** As a library consumer, I want the ACM config's SSM export paths to be explicitly defined in config, so that the library does not silently generate default export paths from deployment properties.

#### Acceptance Criteria

1. WHEN SSM exports are explicitly defined in the ACM stack config, THE CDK_Factory ACM config SHALL use the configured export paths
2. WHEN SSM exports are not defined and `ssm.auto_export` is enabled, THE CDK_Factory ACM config SHALL require `ssm.namespace` to be defined and use it to construct export paths
3. THE CDK_Factory ACM config SHALL NOT auto-generate default SSM export paths from `deployment.workload.environment` and `deployment.workload.name`

### Requirement 8: Eliminate Hardcoded SSM Path in ECR Config

**User Story:** As a library consumer, I want the ECR config's `ecr_ssm_path` auto-derivation to use the stack's SSM namespace rather than `deployment.workload_name` and `deployment.environment`.

#### Acceptance Criteria

1. WHEN `ecr_ssm_path` is explicitly provided in the ECR config, THE CDK_Factory ECR config SHALL use the provided path
2. WHEN `ecr_ref` is provided and `ssm.imports.namespace` or `ssm.namespace` is defined, THE CDK_Factory ECR config SHALL derive the SSM path using the configured namespace
3. WHEN `ecr_ref` is provided and no SSM namespace is available, THE CDK_Factory ECR config SHALL raise a configuration error identifying the missing namespace
4. THE CDK_Factory ECR config SHALL NOT fall back to `deployment.workload_name` and `deployment.environment` to auto-derive `ecr_ssm_path`

### Requirement 9: Eliminate Hardcoded Secret Name in RDS Config

**User Story:** As a library consumer, I want the RDS config's default secret name to be config-driven, so that it does not assume a `/{environment}/{workload_name}/rds/credentials` pattern.

#### Acceptance Criteria

1. WHEN `secret_name` is explicitly provided in the RDS config, THE CDK_Factory RDS config SHALL use the provided secret name
2. WHEN `secret_name` is not provided, THE CDK_Factory RDS config SHALL raise a configuration error stating that `secret_name` is required
3. THE CDK_Factory RDS config SHALL NOT auto-generate a default secret name from `deployment.environment` and `deployment.workload_name`

### Requirement 10: Eliminate Fallback Patterns in Enhanced SSM Config

**User Story:** As a library consumer, I want the Enhanced SSM Config's `workload` property to require explicit configuration rather than falling back to `"default"`.

#### Acceptance Criteria

1. WHEN `ssm.workload` or `ssm.organization` is defined in the config, THE CDK_Factory Enhanced SSM Config SHALL use the configured value
2. WHEN neither `ssm.workload` nor `ssm.organization` is defined, THE CDK_Factory Enhanced SSM Config SHALL raise a configuration error identifying the missing field
3. THE CDK_Factory Enhanced SSM Config SHALL NOT fall back to the string `"default"` as a workload name

### Requirement 11: Eliminate Fallback Defaults in Template Variable Resolution

**User Story:** As a library consumer, I want the SSM mixin's template variable resolution to fail explicitly when `WORKLOAD_NAME` or `ENVIRONMENT` cannot be determined, so that I don't get SSM paths containing `"test"` or `"test-workload"`.

#### Acceptance Criteria

1. WHEN resolving template variables and the workload config provides `ENVIRONMENT` and `WORKLOAD_NAME`, THE CDK_Factory StandardizedSsmMixin SHALL use those values
2. WHEN resolving template variables and neither workload config nor deployment config provides `ENVIRONMENT` or `WORKLOAD_NAME`, THE CDK_Factory StandardizedSsmMixin SHALL raise a configuration error identifying the missing variable
3. THE CDK_Factory StandardizedSsmMixin SHALL NOT fall back to hardcoded defaults such as `"test"`, `"test-workload"`, or `"us-east-1"` for `ENVIRONMENT` and `WORKLOAD_NAME`

### Requirement 12: Eliminate Hardcoded Environment Allowlist in SSM Path Validation

**User Story:** As a library consumer, I want SSM path validation to accept any environment name, so that the library does not warn on valid custom environment names.

#### Acceptance Criteria

1. THE CDK_Factory SSM path validator SHALL validate that SSM paths start with `/` and have the minimum required number of segments
2. THE CDK_Factory SSM path validator SHALL NOT emit warnings based on a hardcoded allowlist of environment names (e.g., `dev`, `staging`, `prod`, `test`, `alpha`, `beta`, `sandbox`)
3. THE CDK_Factory SSM path validator SHALL accept any valid string as an environment segment

### Requirement 13: Eliminate Hardcoded Template Variable Requirement in SSM Validator

**User Story:** As a library consumer, I want the SSM validator to not require `{{ENVIRONMENT}}` or `{{WORKLOAD_NAME}}` template variables in every SSM path, since paths may use `ssm.namespace` which is already resolved.

#### Acceptance Criteria

1. THE CDK_Factory SsmStandardValidator SHALL validate SSM path structure (leading `/`, minimum segments) without requiring specific template variables
2. THE CDK_Factory SsmStandardValidator SHALL NOT emit errors when an SSM path does not contain `{{ENVIRONMENT}}` or `{{WORKLOAD_NAME}}` template variables
3. WHEN an SSM path uses a resolved namespace (e.g., `/my-app/dev/lambda/func/arn`), THE CDK_Factory SsmStandardValidator SHALL accept the path as valid

### Requirement 14: Config Validation at Synthesis Time

**User Story:** As a library consumer, I want missing SSM namespace configuration to be caught early during CDK synthesis, so that I get a clear error message before any CloudFormation resources are created.

#### Acceptance Criteria

1. WHEN a stack requires SSM namespace configuration and the config is missing, THE CDK_Factory Config_Validator SHALL raise the error during the stack's `build()` method before creating any CDK constructs
2. THE CDK_Factory Config_Validator SHALL include the stack name, the missing config field path (e.g., `ssm.namespace`), and a corrective action in the error message
3. IF a required SSM config value is missing, THEN THE CDK_Factory SHALL terminate synthesis for that stack with a non-zero exit code

### Requirement 15: Eliminate Hardcoded SSM Path in Deployment Config

**User Story:** As a library consumer, I want the `DeploymentConfig.get_ssm_parameter_name` method to be config-driven rather than hardcoding a `/{environment}/{workload_name}/...` pattern, so that consumers who use this method get paths consistent with their SSM namespace config.

#### Acceptance Criteria

1. WHEN `get_ssm_parameter_name` is called and an SSM namespace is available from the stack or workload config, THE CDK_Factory DeploymentConfig SHALL use the configured namespace to construct the path
2. WHEN `get_ssm_parameter_name` is called and no SSM namespace is available, THE CDK_Factory DeploymentConfig SHALL raise a configuration error identifying the missing namespace
3. THE CDK_Factory DeploymentConfig SHALL NOT hardcode a `/{environment}/{workload_name}/{resource_type}/{resource_name}` pattern as the default SSM path structure
