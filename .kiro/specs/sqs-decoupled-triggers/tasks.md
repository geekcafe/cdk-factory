# Implementation Plan: SQS Decoupled Triggers

## Overview

Implement the decoupled SQS integration pattern for cdk-factory. This adds standalone queue config files, SQS trigger support in the Lambda triggers array, and structured SQS send permissions. The existing inline pattern remains unchanged. Implementation follows the existing patterns for S3 and EventBridge triggers.

## Tasks

- [x] 1. Add SQS properties to LambdaTriggersConfig
  - [x] 1.1 Add queue_name, queue_ssm_path, batch_size, and max_batching_window_seconds properties to LambdaTriggersConfig
    - File: `src/cdk_factory/configurations/resources/lambda_triggers.py`
    - Add `queue_name` property returning `self.__config.get("queue_name", "")`
    - Add `queue_ssm_path` property returning `self.__config.get("queue_ssm_path", "")`
    - Add `batch_size` property returning `int(self.__config.get("batch_size", 1))` with default 1
    - Add `max_batching_window_seconds` property returning `int(self.__config.get("max_batching_window_seconds", 0))` with default 0
    - Follow the same pattern as existing `bucket_name`, `bucket_ssm_path`, and `events` properties
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 1.2 Write property test for LambdaTriggersConfig SQS properties
    - **Property 1: LambdaTriggersConfig property round-trip**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - File: `tests/properties/test_lambda_triggers_config_props.py`
    - Use Hypothesis to generate random config dicts with SQS keys
    - Assert constructed properties return exact configured values
    - Assert missing keys return defaults ("" for strings, 1 for batch_size, 0 for max_batching_window_seconds)
    - Use `@settings(max_examples=100)`

  - [ ]* 1.3 Write unit tests for LambdaTriggersConfig SQS properties
    - File: `tests/unit/test_lambda_triggers_config.py`
    - Test `queue_name` returns correct value and empty default
    - Test `queue_ssm_path` returns correct value and empty default
    - Test `batch_size` returns configured value and default of 1
    - Test `max_batching_window_seconds` returns configured value and default of 0
    - Test with empty/None config dict
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 2. Implement SQS trigger handler in Lambda Stack
  - [x] 2.1 Add "sqs" case to the trigger routing block in lambda_stack.py
    - File: `src/cdk_factory/stack_library/aws_lambdas/lambda_stack.py`
    - Add `elif trigger.resource_type.lower() == "sqs":` case after the existing "event-bridge" case
    - Call `self.__setup_sqs_trigger(trigger=trigger, lambda_function=lambda_function, function_name=f"{function_config.name}-{trigger_id}")`
    - _Requirements: 2.1_

  - [x] 2.2 Implement __setup_sqs_trigger method in lambda_stack.py
    - File: `src/cdk_factory/stack_library/aws_lambdas/lambda_stack.py`
    - Resolve queue ARN: if `trigger.queue_ssm_path` → use `ssm.StringParameter.value_for_string_parameter()`; elif `trigger.queue_name` → construct ARN as `arn:aws:sqs:{region}:{account}:{queue_name}`; else raise `ValueError`
    - Apply `deployment.build_resource_name()` to queue_name for consistent naming
    - Import queue by ARN using `sqs.Queue.from_queue_arn()`
    - Create `_lambda.EventSourceMapping` with `batch_size` and `max_batching_window` from trigger config
    - Grant `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` via `iam.PolicyStatement` on the Lambda execution role
    - No live AWS calls — all resolution via CDK tokens
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1_

  - [ ]* 2.3 Write property test for queue ARN construction
    - **Property 2: Queue ARN construction**
    - **Validates: Requirements 2.2, 3.2**
    - File: `tests/properties/test_arn_construction_props.py`
    - Use Hypothesis to generate random (queue_name, region, account) tuples
    - Assert constructed ARN matches `arn:aws:sqs:{region}:{account}:{queue_name}`
    - Use `@settings(max_examples=100)`

  - [ ]* 2.4 Write synthesis test for SQS trigger on Lambda
    - File: `tests/unit/test_sqs_trigger_synth.py`
    - Synthesize a Lambda stack with an SQS trigger config (queue_name, batch_size, max_batching_window_seconds)
    - Assert CloudFormation template contains an `AWS::Lambda::EventSourceMapping` resource
    - Assert `BatchSize` matches configured value
    - Assert `MaximumBatchingWindowInSeconds` matches configured value (or absent when 0)
    - Assert IAM policy grants `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement SQS send permission in permission builder
  - [x] 4.1 Add "sqs" case to _get_structured_permission in policy_docs.py
    - File: `src/cdk_factory/constructs/lambdas/policies/policy_docs.py`
    - Add `if "sqs" in permission:` block in `_get_structured_permission()`
    - Extract `action`, `queue_name`, and `queue_ssm_path` from the permission dict
    - Validate at least one queue identifier is present; raise `ValueError` if both are missing
    - Resolve queue ARN: if `queue_ssm_path` → use `StringParameter.value_for_string_parameter()`; else construct from name/region/account
    - Map `"send"` action to `["sqs:SendMessage"]`
    - Return structured permission dict with sid, actions, resources, and nag suppression
    - Raise `ValueError` for unknown SQS actions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.2_

  - [ ]* 4.2 Write property test for SQS send permission
    - **Property 5: SQS send permission grants SendMessage**
    - **Validates: Requirements 3.1**
    - File: `tests/properties/test_permission_builder_props.py`
    - Use Hypothesis to generate random queue names
    - Assert the permission builder returns a policy containing `sqs:SendMessage` targeting the constructed queue ARN
    - Use `@settings(max_examples=100)`

  - [ ]* 4.3 Write unit tests for SQS send permission
    - File: `tests/unit/test_policy_docs_sqs.py`
    - Test `{"sqs": "send", "queue_name": "my-queue"}` produces correct IAM actions and ARN
    - Test `{"sqs": "send", "queue_ssm_path": "/path/to/arn"}` uses CDK token resolution
    - Test missing both queue identifiers raises `ValueError`
    - Test unknown SQS action raises `ValueError`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. Implement standalone queue config loading in SQS Stack
  - [x] 5.1 Add _load_standalone_queue_configs and _resolve_template_variables methods to SQS Stack
    - File: `src/cdk_factory/stack_library/simple_queue_service/sqs_stack.py`
    - Add `_load_standalone_queue_configs(self, config_dir: str) -> list[dict]` — loads all JSON files from directory, sorted alphabetically
    - Add `_resolve_template_variables(self, config: dict) -> dict` — replaces `{{WORKLOAD_NAME}}` and `{{DEPLOYMENT_NAMESPACE}}` with deployment values
    - Handle non-existent directory gracefully (return empty list)
    - _Requirements: 1.1, 6.4_

  - [x] 5.2 Extend _build method to load standalone queue configs
    - File: `src/cdk_factory/stack_library/simple_queue_service/sqs_stack.py`
    - Read `queue_config_dir` from `stack_config.dictionary`
    - Call `_load_standalone_queue_configs` and `_resolve_template_variables`
    - Wrap each config as `SQSConfig` and validate `name` is present (raise `ValueError` if missing)
    - Append to `self.sqs_config.queues` for processing in the existing queue creation loop
    - Ensure standalone configs support: name, type (standard/fifo), visibility_timeout_seconds, message_retention_period_days, delay_seconds, dead_letter_queue object, ssm_parameters
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1, 6.2, 6.3_

  - [ ]* 5.3 Write property test for missing name validation
    - **Property 8: Missing name validation**
    - **Validates: Requirements 1.6**
    - File: `tests/properties/test_sqs_validation_props.py`
    - Use Hypothesis to generate config dicts without a `name` field (or with empty string)
    - Assert `ValueError` is raised during standalone config processing
    - Use `@settings(max_examples=100)`

  - [ ]* 5.4 Write property test for template variable resolution
    - **Property 10: Template variable resolution**
    - **Validates: Requirements 6.4**
    - File: `tests/properties/test_template_resolution_props.py`
    - Use Hypothesis to generate random workload/namespace strings
    - Assert all `{{WORKLOAD_NAME}}` and `{{DEPLOYMENT_NAMESPACE}}` placeholders are replaced
    - Assert no unresolved `{{...}}` patterns remain in output
    - Use `@settings(max_examples=100)`

  - [ ]* 5.5 Write synthesis test for standalone queue config
    - File: `tests/unit/test_sqs_standalone_synth.py`
    - Synthesize SQS_Stack with a standalone queue config (including DLQ and SSM parameters)
    - Assert CloudFormation template contains `AWS::SQS::Queue` with correct properties
    - Assert DLQ is created when `dead_letter_queue` is specified
    - Assert CloudWatch alarm on the DLQ
    - Assert SSM parameters published for queue ARN and URL
    - Assert TLS policy on both main queue and DLQ
    - Assert FIFO queue has `.fifo` suffix
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 6.2_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Backward compatibility and integration verification
  - [x] 7.1 Write regression test for existing inline SQS pattern
    - File: `tests/unit/test_sqs_backward_compat.py`
    - Synthesize Lambda stack with existing inline `sqs.queues` consumer config and verify EventSourceMapping is created
    - Synthesize Lambda stack with inline producer config and verify permissions are granted
    - Synthesize SQS stack with `lambda_config_paths` and verify queues are discovered and created
    - Verify both inline and new trigger patterns on the same Lambda produce valid CF without conflict
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 7.2 Write synthesis test for combined inline + trigger patterns
    - File: `tests/unit/test_sqs_combined_patterns.py`
    - Synthesize a Lambda with both `sqs.queues` inline config AND a `triggers` array SQS entry
    - Assert both EventSourceMappings are present
    - Assert no duplicate or conflicting IAM policies
    - _Requirements: 4.3_

- [x] 8. Update JSON schema for standalone queue config
  - [x] 8.1 Create or update sqs.schema.json for standalone queue format
    - File: `src/cdk_factory/schemas/sqs.schema.json`
    - Define JSON schema for standalone queue config fields: name (required), description, type (enum: standard, fifo), visibility_timeout_seconds, message_retention_period_days, delay_seconds, dead_letter_queue (object with name, max_receive_count, message_retention_period_days), ssm_parameters (object with namespace)
    - Support template variable patterns in string fields
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- This is a Python CDK project — all code uses Python, tests use pytest + Hypothesis
- Virtual env activation: `source /Users/eric.wilson/Projects/geek-cafe/cdk-factory/.venv/bin/activate`
- Test runner: `python -m pytest tests/ -x -q`
- No live AWS calls during synthesis — use CDK tokens (`StringParameter.value_for_string_parameter()`)
- Follow existing patterns in lambda_stack.py for S3 and EventBridge triggers

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1", "8.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "5.2"] },
    { "id": 2, "tasks": ["2.2", "4.1", "5.3", "5.4"] },
    { "id": 3, "tasks": ["2.3", "2.4", "4.2", "4.3", "5.5"] },
    { "id": 4, "tasks": ["7.1"] },
    { "id": 5, "tasks": ["7.2"] }
  ]
}
```
