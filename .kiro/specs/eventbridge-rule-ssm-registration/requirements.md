# Requirements Document

## Introduction

EventBridge rules created by CDK receive CloudFormation-mangled physical names (e.g., `acme-saas-dev-lambda-warmuporchestrator1eventb-oBsgLBL1cHvc`) because no explicit `rule_name` is provided. Lambda handlers that need to interact with these rules (such as the warm-up schedule config handler) currently rely on a hardcoded environment variable (`WARM_UP_RULE_NAME`) that assumes a predictable name pattern. This mismatch causes "rule not found" errors in the admin UI.

This feature implements SSM Parameter Store self-registration for EventBridge rules, following the same pattern already used for Lambda function discovery. The CDK stack registers the actual rule name and ARN to SSM under predictable paths, and consuming Lambdas discover the real rule name by reading from SSM instead of relying on environment variables.

## Glossary

- **Lambda_Stack**: The CDK stack class in `cdk-factory` that creates Lambda functions, their triggers, and exports metadata to SSM Parameter Store.
- **EventBridge_Rule**: An AWS EventBridge rule created as a trigger for a Lambda function, typically on a schedule (rate or cron).
- **SSM_Parameter_Store**: AWS Systems Manager Parameter Store, used as a registry for resource names and ARNs that cannot be predicted at configuration time.
- **Trigger_Config**: The JSON configuration object within a Lambda resource definition that specifies EventBridge trigger properties including name, resource type, and schedule.
- **Schedule_Config_Handler**: The Lambda handler (`warm_up/schedule_config/app.py`) that retrieves EventBridge rule details for the admin UI.
- **SSM_Discovery_Service**: The existing service class that scans SSM Parameter Store paths recursively to discover registered resource ARNs.
- **Namespace**: The SSM path prefix derived from the stack's `ssm.namespace` configuration (e.g., `acme-saas/dev/lambda/tenants`).

## Requirements

### Requirement 1: Register EventBridge Rule Name to SSM

**User Story:** As a CDK stack deployer, I want EventBridge rule names automatically registered to SSM Parameter Store after creation, so that consuming services can discover the actual rule name without relying on naming conventions.

#### Acceptance Criteria

1. WHEN an EventBridge rule is created as a Lambda trigger AND SSM auto-export is enabled, THE Lambda_Stack SHALL write the rule's physical name to SSM Parameter Store at the path `/{namespace}/event-bridge/{trigger-name}/rule-name`.
2. WHEN an EventBridge rule is created as a Lambda trigger AND SSM auto-export is enabled, THE Lambda_Stack SHALL write the rule's ARN to SSM Parameter Store at the path `/{namespace}/event-bridge/{trigger-name}/rule-arn`.
3. THE Lambda_Stack SHALL derive `{trigger-name}` from the trigger configuration's `name` field with hyphens replacing underscores (e.g., `warm_up_orchestrator_schedule` becomes `warm-up-orchestrator-schedule`).
4. IF SSM auto-export is not enabled for the stack, THEN THE Lambda_Stack SHALL skip EventBridge rule registration without raising an error.
5. IF the trigger configuration does not include a `name` field, THEN THE Lambda_Stack SHALL skip SSM registration for that trigger and log a warning.

### Requirement 2: Discover EventBridge Rule Name from SSM

**User Story:** As a Lambda handler developer, I want to look up the EventBridge rule name from SSM Parameter Store at runtime, so that my handler works regardless of the physical name CloudFormation assigns to the rule.

#### Acceptance Criteria

1. WHEN the Schedule_Config_Handler is invoked, THE Schedule_Config_Handler SHALL read the EventBridge rule name from SSM Parameter Store using a configured SSM path.
2. THE Schedule_Config_Handler SHALL use the `SSM_RULE_SSM_PATH` environment variable to determine the SSM parameter path for the rule name.
3. IF the SSM parameter does not exist or cannot be read, THEN THE Schedule_Config_Handler SHALL return an error with code `RULE_DISCOVERY_ERROR` and a descriptive message.
4. WHEN the rule name is successfully retrieved from SSM, THE Schedule_Config_Handler SHALL use that name to call `events:DescribeRule`.
5. THE Schedule_Config_Handler SHALL fall back to the `WARM_UP_RULE_NAME` environment variable IF `SSM_RULE_SSM_PATH` is not set, preserving backward compatibility.

### Requirement 3: Grant SSM Read Permissions to Consuming Lambdas

**User Story:** As an infrastructure engineer, I want consuming Lambdas to have SSM read permissions for the EventBridge parameter paths, so that runtime discovery succeeds without permission errors.

#### Acceptance Criteria

1. THE Schedule_Config_Handler Lambda configuration SHALL include an SSM `parameter_store` read permission for the EventBridge rule SSM path.
2. THE permission path SHALL follow the pattern `/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/event-bridge/*` to allow discovery of all registered EventBridge rules.

### Requirement 4: Remove Hardcoded Rule Name Assumption

**User Story:** As a platform developer, I want the system to stop assuming predictable EventBridge rule names, so that CloudFormation-generated names do not cause runtime failures.

#### Acceptance Criteria

1. WHEN SSM-based discovery is configured, THE Schedule_Config_Handler SHALL not depend on the `WARM_UP_RULE_NAME` environment variable containing a correct rule name.
2. THE Lambda configuration for Schedule_Config_Handler SHALL replace the hardcoded `WARM_UP_RULE_NAME` value with an `SSM_RULE_SSM_PATH` value pointing to the SSM parameter path where the rule name is registered.
3. THE Schedule_Config_Handler SHALL log the SSM path used for discovery and the resolved rule name for operational visibility.

### Requirement 5: SSM Registration Follows Existing Export Pattern

**User Story:** As a CDK factory maintainer, I want EventBridge SSM registration to follow the same code pattern as Lambda ARN export, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. THE Lambda_Stack SHALL perform EventBridge SSM registration within the same lifecycle phase as Lambda ARN export (during stack synthesis).
2. THE Lambda_Stack SHALL use `aws_cdk.aws_ssm.StringParameter` constructs for EventBridge registration, consistent with the existing Lambda ARN export implementation.
3. THE Lambda_Stack SHALL log a confirmation message for each EventBridge rule registered to SSM, following the same logging pattern as Lambda ARN export (e.g., `✅ Exported EventBridge rule '{trigger-name}' to SSM: {param_path}`).
4. THE Lambda_Stack SHALL use `ssm.ParameterTier.STANDARD` for all EventBridge SSM parameters.
