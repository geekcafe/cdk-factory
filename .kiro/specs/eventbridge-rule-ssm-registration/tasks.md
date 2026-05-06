# Implementation Plan: EventBridge Rule SSM Registration

## Overview

Implement automatic SSM Parameter Store registration for EventBridge rules created by the CDK Lambda stack, and update the consuming handler to discover rule names from SSM at runtime. Changes span three repositories: `cdk-factory` (rule collection and SSM export), `Acme-Services` (SSM-based rule discovery in handler), and `Acme-SaaS-IaC` (permissions and environment variable configuration).

## Tasks

- [x] 1. Collect EventBridge rules during trigger setup
  - [x] 1.1 Add `exported_eventbridge_rules` instance variable and modify `__set_event_bridge_event()`
    - Add `self.exported_eventbridge_rules: dict = {}` to `LambdaStack.__init__`
    - Modify `__set_event_bridge_event()` to return the created `events.Rule` object
    - After rule creation, normalize the trigger name via `trigger.name.replace("_", "-")`
    - Store the rule in `self.exported_eventbridge_rules[trigger_name]` only when `trigger.name` is non-empty
    - Log a warning when trigger has no `name` field and skip storage
    - _Requirements: 1.3, 1.5, 5.1_

  - [x]* 1.2 Write property test for trigger name normalization
    - **Property 1: Trigger name normalization is underscore-free and idempotent**
    - **Validates: Requirements 1.3**
    - Use `hypothesis` library with `@given` strategy generating strings from `[a-z0-9_-]`
    - Assert output contains no underscores
    - Assert applying normalization twice yields the same result as once
    - Minimum 100 examples via `@settings(max_examples=100)`

- [x] 2. Export EventBridge rules to SSM Parameter Store
  - [x] 2.1 Implement `__export_eventbridge_rules_to_ssm()` method
    - Add new private method to `LambdaStack` mirroring `__export_lambda_arns_to_ssm()` structure
    - Check `ssm_config.get("auto_export", False)` — return early if disabled
    - Get `namespace` from `ssm_config.get("namespace")`
    - Iterate over `self.exported_eventbridge_rules`
    - Create `ssm.StringParameter` at `/{namespace}/event-bridge/{trigger-name}/rule-name` with `rule.rule_name`
    - Create `ssm.StringParameter` at `/{namespace}/event-bridge/{trigger-name}/rule-arn` with `rule.rule_arn`
    - Use `tier=ssm.ParameterTier.STANDARD` for all parameters
    - Log `✅ Exported EventBridge rule '{trigger-name}' to SSM: {param_path}` for each rule
    - _Requirements: 1.1, 1.2, 1.4, 5.1, 5.2, 5.3, 5.4_

  - [x] 2.2 Call `__export_eventbridge_rules_to_ssm()` from `build()`
    - Insert the call after `__export_route_metadata_to_ssm()` in the `build()` method
    - _Requirements: 5.1_

  - [x]* 2.3 Write unit tests for EventBridge SSM export
    - Use CDK assertion tests (`assertions.Template.from_stack()`)
    - Verify synthesized template contains `AWS::SSM::Parameter` resources for rule-name and rule-arn
    - Verify SSM parameter paths follow `/{namespace}/event-bridge/{trigger-name}/rule-name` pattern
    - Verify parameters use `Standard` tier
    - Verify no EventBridge SSM parameters when `auto_export` is `False`
    - Verify skip behavior when trigger has no `name` field
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [x] 3. Checkpoint - Ensure CDK factory tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement SSM-based rule discovery in the schedule config handler
  - [x] 4.1 Add `_read_rule_name_from_ssm()` helper and modify `get_schedule_config()`
    - In `Acme-Services/src/aplos_nca_services/handlers/warm_up/schedule_config/app.py`:
    - Add `_read_rule_name_from_ssm(ssm_path: str) -> str | None` helper function
    - Call `ssm_client.get_parameter(Name=ssm_path)` and return the `Value`
    - Return `None` on `ParameterNotFound` or other `ClientError` exceptions
    - Log the SSM path being queried and the resolved rule name
    - Modify `get_schedule_config()` to check `SSM_RULE_SSM_PATH` env var first
    - If `SSM_RULE_SSM_PATH` is set, call `_read_rule_name_from_ssm()`
    - If SSM read fails, return `ServiceResult.error_result` with code `RULE_DISCOVERY_ERROR`
    - Fall back to `WARM_UP_RULE_NAME` env var if `SSM_RULE_SSM_PATH` is not set
    - If neither env var provides a rule name, return error with `CONFIGURATION_ERROR`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.3_

  - [x]* 4.2 Write unit tests for SSM-based rule discovery
    - Test handler reads from SSM when `SSM_RULE_SSM_PATH` is set
    - Test handler falls back to `WARM_UP_RULE_NAME` when `SSM_RULE_SSM_PATH` is not set
    - Test `RULE_DISCOVERY_ERROR` returned when SSM parameter doesn't exist
    - Test logging includes SSM path and resolved rule name
    - Test `DescribeRule` is called with the SSM-resolved name
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 5. Update IaC configuration for SSM permissions and environment variable
  - [x] 5.1 Add SSM read permission and `SSM_RULE_SSM_PATH` env var to warm-up-schedule-config.json
    - In `Acme-SaaS-IaC/cdk/configs/stacks/lambdas/resources/warm-up/warm-up-schedule-config.json`:
    - Add `parameter_store` read permission with path `/{{WORKLOAD_NAME}}/{{DEPLOYMENT_NAMESPACE}}/event-bridge/*`
    - Add `SSM_RULE_SSM_PATH` environment variable with value `/acme-saas/{{DEPLOYMENT_NAMESPACE}}/lambda/event-bridge/warm-up-orchestrator-schedule/rule-name`
    - Keep existing `WARM_UP_RULE_NAME` environment variable for backward compatibility
    - _Requirements: 3.1, 3.2, 4.2_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property test validates the trigger name normalization correctness property from the design
- The implementation spans three repositories: `cdk-factory`, `Acme-Services`, and `Acme-SaaS-IaC`
