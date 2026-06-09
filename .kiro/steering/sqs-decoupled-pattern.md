# SQS Decoupled Pattern (Preferred)

## Priority: HIGH

## Rule

For new SQS integrations, use the decoupled pattern where queues are defined in standalone config files and Lambdas reference them via `triggers` (consumers) or `permissions` (producers). Do NOT use the legacy inline `"sqs": {"queues": [...]}` pattern for new work.

## Why

The legacy inline pattern tightly couples queue lifecycle to Lambda consumer configs and requires a centralized `sqs-consumer-queues.json` registry with `lambda_config_paths`. The decoupled pattern:

- Separates queue lifecycle from Lambda lifecycle
- Eliminates the need for a centralized registry
- Follows the same `triggers` array convention as S3 and EventBridge triggers
- Makes producer permissions explicit in the `permissions` array
- Scales cleanly across Lambda groups without cross-references

## Standalone Queue Definition

Define queues in their own JSON file under `configs/stacks/sqs/`:

```json
{
  "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-my-queue",
  "description": "Purpose of this queue",
  "type": "standard",
  "visibility_timeout_seconds": 120,
  "message_retention_period_days": 4,
  "delay_seconds": 0,
  "dead_letter_queue": {
    "name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-my-queue-dlq",
    "max_receive_count": 3,
    "message_retention_period_days": 14
  },
  "ssm_parameters": {
    "namespace": "my-app/{{DEPLOYMENT_NAMESPACE}}/sqs"
  }
}
```

## Lambda Consumer (via triggers)

```json
{
  "name": "my-consumer-lambda",
  "triggers": [
    {
      "resource_type": "sqs",
      "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-my-queue",
      "batch_size": 1,
      "max_batching_window_seconds": 0
    }
  ]
}
```

This creates an EventSourceMapping and grants `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`.

## Lambda Producer (via permissions)

```json
{
  "name": "my-producer-lambda",
  "permissions": [
    {"sqs": "send", "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-my-queue"}
  ]
}
```

This grants `sqs:SendMessage` on the queue.

## SSM-Based Resolution (Cross-Stack)

When the queue is in a different stack and the name isn't deterministic, use SSM:

```json
{
  "triggers": [
    {
      "resource_type": "sqs",
      "queue_ssm_path": "/my-app/dev/sqs/my-queue/arn",
      "batch_size": 1
    }
  ]
}
```

## Legacy Pattern (Do Not Use for New Work)

The old pattern embeds queue definitions inside Lambda configs:

```json
{
  "sqs": {
    "queues": [
      {"type": "consumer", "queue_name": "...", "visibility_timeout_seconds": 60, ...},
      {"type": "producer", "queue_name": "...", ...}
    ]
  }
}
```

This still works but should not be used for new queues. Existing inline definitions will be migrated gradually.

## When This Applies

- Any new SQS queue being added to a project
- Any new Lambda that needs to consume from or produce to SQS
- Refactoring existing SQS integrations (opportunistic migration)

## Exception

Existing inline SQS configs do not need to be migrated immediately. They continue to work unchanged. Migrate them when you're already modifying that Lambda config for other reasons.
