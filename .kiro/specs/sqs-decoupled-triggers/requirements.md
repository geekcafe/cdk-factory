# Requirements Document

## Introduction

This feature adds a decoupled SQS integration pattern to the cdk-factory framework. Today, SQS queues are defined inline within Lambda consumer configs and created by a centralized `sqs_stack` that reads queue definitions from Lambda config paths. This works but tightly couples queue lifecycle to Lambda consumers and requires a centralized registry that doesn't scale cleanly.

The new pattern introduces standalone SQS queue config files (under `configs/stacks/sqs/`), allows Lambda consumers to reference queues via the existing `triggers` array with `"resource_type": "sqs"`, and allows Lambda producers to gain send permissions via a structured `permissions` entry. The existing inline pattern (v1) continues to work unchanged.

## Glossary

- **CDK_Factory**: The open-source CDK framework that synthesizes CloudFormation templates from JSON config files
- **Lambda_Stack**: The CDK stack module (`lambda_stack.py`) that provisions Lambda functions and wires triggers and permissions
- **SQS_Stack**: The CDK stack module (`sqs_stack.py`) that provisions SQS queues
- **Standalone_Queue_Config**: A JSON file in `configs/stacks/sqs/` that defines a single SQS queue independently of any Lambda
- **Lambda_Trigger**: An entry in a Lambda config's `triggers` array that binds an event source to the Lambda function
- **Structured_Permission**: A JSON object in a Lambda config's `permissions` array that grants IAM permissions for a specific AWS resource
- **SSM_Parameter**: An AWS Systems Manager Parameter Store entry used to share resource ARNs between stacks without live AWS calls
- **Event_Source_Mapping**: The AWS Lambda resource that connects an SQS queue to a Lambda function as a trigger
- **Dead_Letter_Queue**: An SQS queue that receives messages that fail processing after a configured number of retries
- **CDK_Token**: A placeholder value resolved by CloudFormation at deploy time, avoiding live AWS calls during synthesis
- **Inline_Pattern**: The existing v1 pattern where queue definitions are embedded inside Lambda config files under the `"sqs": {"queues": [...]}` key

## Requirements

### Requirement 1: Standalone Queue Configuration

**User Story:** As a platform engineer, I want to define SQS queues in their own standalone JSON config files, so that queue lifecycle is independent of any specific Lambda consumer.

#### Acceptance Criteria

1. WHEN a standalone queue config file is placed in the `configs/stacks/sqs/` directory, THE SQS_Stack SHALL create the queue with the specified properties (name, type, visibility timeout, message retention period, delay seconds)
2. WHEN the standalone queue config specifies a `dead_letter_queue` object, THE SQS_Stack SHALL create a dead letter queue with the specified name, max receive count, and message retention period
3. WHEN the standalone queue config specifies `ssm_parameters`, THE SQS_Stack SHALL publish the queue URL and ARN to the specified SSM parameter paths
4. THE SQS_Stack SHALL enforce a TLS-only resource policy on each standalone queue it creates
5. THE SQS_Stack SHALL create a CloudWatch alarm on each dead letter queue that fires when messages are visible
6. IF a standalone queue config is missing the required `name` field, THEN THE SQS_Stack SHALL raise a validation error during synthesis

### Requirement 2: SQS Trigger Support in Lambda Triggers Array

**User Story:** As a platform engineer, I want to add `"resource_type": "sqs"` to a Lambda's `triggers` array, so that the Lambda is automatically wired as an SQS consumer without embedding queue definitions inline.

#### Acceptance Criteria

1. WHEN a Lambda config contains a trigger with `"resource_type": "sqs"`, THE Lambda_Stack SHALL create an Event_Source_Mapping between the referenced queue and the Lambda function
2. WHEN the SQS trigger specifies a `queue_name`, THE Lambda_Stack SHALL resolve the queue ARN by constructing it from the queue name, deployment region, and deployment account
3. WHEN the SQS trigger specifies a `queue_ssm_path` instead of `queue_name`, THE Lambda_Stack SHALL resolve the queue ARN from the SSM parameter using a CDK_Token (no live AWS calls)
4. WHEN the SQS trigger specifies `batch_size`, THE Lambda_Stack SHALL configure the Event_Source_Mapping with the specified batch size
5. WHEN the SQS trigger specifies `max_batching_window_seconds`, THE Lambda_Stack SHALL configure the Event_Source_Mapping with the specified batching window duration
6. THE Lambda_Stack SHALL grant `sqs:ReceiveMessage`, `sqs:DeleteMessage`, and `sqs:GetQueueAttributes` permissions to the Lambda execution role for the referenced queue
7. IF the SQS trigger has neither `queue_name` nor `queue_ssm_path`, THEN THE Lambda_Stack SHALL raise a validation error during synthesis

### Requirement 3: SQS Send Permission via Structured Permissions

**User Story:** As a platform engineer, I want to add `{"sqs": "send", "queue_name": "..."}` to a Lambda's `permissions` array, so that the Lambda gains send-message permissions without embedding producer config inline.

#### Acceptance Criteria

1. WHEN a Lambda config contains a permission with `"sqs": "send"`, THE CDK_Factory SHALL grant `sqs:SendMessage` permission to the Lambda execution role for the specified queue
2. WHEN the SQS permission specifies a `queue_name`, THE CDK_Factory SHALL construct the queue ARN from the queue name, deployment region, and deployment account
3. WHEN the SQS permission specifies a `queue_ssm_path` instead of `queue_name`, THE CDK_Factory SHALL resolve the queue ARN from the SSM parameter using a CDK_Token
4. IF the SQS send permission has neither `queue_name` nor `queue_ssm_path`, THEN THE CDK_Factory SHALL raise a validation error during synthesis

### Requirement 4: Backward Compatibility

**User Story:** As a platform engineer using the existing inline SQS pattern, I want my current configs to continue working unchanged, so that I can adopt the new pattern gradually.

#### Acceptance Criteria

1. THE Lambda_Stack SHALL continue to process the existing `"sqs": {"queues": [...]}` inline pattern for consumer, producer, and dlq_consumer types
2. THE SQS_Stack SHALL continue to support the `lambda_config_paths` resolution pattern for discovering inline queue definitions
3. WHEN both the inline pattern and the new trigger pattern are present on the same Lambda config, THE Lambda_Stack SHALL process both independently without conflict
4. THE CDK_Factory SHALL not require changes to existing consumer project config files that use the inline pattern

### Requirement 5: LambdaTriggersConfig SQS Properties

**User Story:** As a framework maintainer, I want the `LambdaTriggersConfig` class to expose SQS-specific properties, so that trigger configuration is type-safe and consistent with other trigger types.

#### Acceptance Criteria

1. THE LambdaTriggersConfig SHALL expose a `queue_name` property that returns the configured queue name string
2. THE LambdaTriggersConfig SHALL expose a `queue_ssm_path` property that returns the SSM parameter path for queue ARN resolution
3. THE LambdaTriggersConfig SHALL expose a `batch_size` property that returns the configured batch size with a default of 1
4. THE LambdaTriggersConfig SHALL expose a `max_batching_window_seconds` property that returns the configured batching window with a default of 0

### Requirement 6: Standalone Queue Config Schema

**User Story:** As a platform engineer, I want a documented JSON schema for standalone queue configs, so that I can create valid configs without guessing field names.

#### Acceptance Criteria

1. THE CDK_Factory SHALL accept standalone queue configs with the following fields: `name` (required), `description`, `type` (standard or fifo), `visibility_timeout`, `message_retention_period`, `delay_seconds`, `dead_letter_queue`, and `ssm_parameters`
2. WHEN the `type` field is set to `fifo`, THE SQS_Stack SHALL create the queue as a FIFO queue with `.fifo` suffix appended to the name
3. WHEN the `dead_letter_queue` object specifies `name`, `max_receive_count`, and `message_retention_period`, THE SQS_Stack SHALL use those values for DLQ creation
4. THE CDK_Factory SHALL support template variables (e.g., `{{WORKLOAD_NAME}}`, `{{DEPLOYMENT_NAMESPACE}}`) in standalone queue config string fields

### Requirement 7: No Live AWS Calls During Synthesis

**User Story:** As a developer running `cdk synth`, I want all resource references to resolve via CDK tokens, so that synthesis works without AWS credentials or network access.

#### Acceptance Criteria

1. WHEN the SQS trigger uses `queue_ssm_path`, THE Lambda_Stack SHALL resolve the ARN using `StringParameter.value_for_string_parameter()` which produces a CloudFormation dynamic reference
2. WHEN the SQS send permission uses `queue_ssm_path`, THE CDK_Factory SHALL resolve the ARN using `StringParameter.value_for_string_parameter()`
3. THE CDK_Factory SHALL not make any boto3 calls or use `value_from_lookup` for SQS resource resolution
