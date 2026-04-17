"""
SQS Validation Functions for CDK-Factory

Standalone validation functions for SQS queue configurations.
These are used at synth time to catch configuration errors early.
"""

from typing import List, Dict, Any


def find_orphaned_producer_queues(
    lambda_stack_configs: List[dict],
) -> List[str]:
    """Find producer queue names that have no matching consumer definition.

    Scans all Lambda stack config dicts, collects all producer queue_names
    and all consumer queue_names, and returns producer names with no
    matching consumer.

    Args:
        lambda_stack_configs: List of Lambda stack config dicts, each with
            a 'resources' array containing SQS queue definitions.

    Returns:
        List of producer queue_names that have no matching consumer definition.
    """
    producer_names: set = set()
    consumer_names: set = set()

    for config in lambda_stack_configs:
        for resource in config.get("resources", []):
            for queue in resource.get("sqs", {}).get("queues", []):
                queue_name = queue.get("queue_name", "")
                if not queue_name:
                    continue
                queue_type = queue.get("type", "")
                if queue_type == "producer":
                    producer_names.add(queue_name)
                elif queue_type == "consumer":
                    consumer_names.add(queue_name)

    return sorted(producer_names - consumer_names)


def validate_consumer_queue_fields(
    consumer_queue_configs: List[dict],
) -> List[str]:
    """Validate that consumer queue configs have required fields.

    Each consumer queue must have visibility_timeout_seconds > 0 and
    message_retention_period_days > 0.

    Args:
        consumer_queue_configs: List of consumer queue config dicts.

    Returns:
        List of descriptive error strings for invalid configs.

    Raises:
        ValueError: If any consumer queue is missing required fields.
    """
    errors: List[str] = []

    for queue in consumer_queue_configs:
        queue_name = queue.get("queue_name", "<unknown>")
        vt = queue.get("visibility_timeout_seconds")
        mr = queue.get("message_retention_period_days")

        if vt is None or int(vt) <= 0:
            errors.append(
                f"Consumer queue '{queue_name}' is missing or has "
                f"invalid 'visibility_timeout_seconds' (must be > 0)"
            )
        if mr is None or int(mr) <= 0:
            errors.append(
                f"Consumer queue '{queue_name}' is missing or has "
                f"invalid 'message_retention_period_days' (must be > 0)"
            )

    if errors:
        raise ValueError("; ".join(errors))

    return errors


def validate_sqs_decoupled_mode(
    lambda_stack_config: dict,
) -> None:
    """Validate that a Lambda stack config with consumer queues has sqs_decoupled_mode: true.

    Args:
        lambda_stack_config: A Lambda stack config dict with 'resources' and
            optionally 'sqs_decoupled_mode'.

    Raises:
        ValueError: If the config has consumer queues but sqs_decoupled_mode
            is missing or not true.
    """
    has_consumer = False
    for resource in lambda_stack_config.get("resources", []):
        for queue in resource.get("sqs", {}).get("queues", []):
            if queue.get("type") == "consumer":
                has_consumer = True
                break
        if has_consumer:
            break

    if has_consumer:
        decoupled = lambda_stack_config.get("sqs_decoupled_mode")
        if decoupled is not True and str(decoupled).lower() != "true":
            stack_name = lambda_stack_config.get("name", "<unknown>")
            raise ValueError(
                f"Lambda stack config '{stack_name}' has consumer queues but "
                f"'sqs_decoupled_mode' is not set to true. "
                f"Stacks with consumer queues must use sqs_decoupled_mode: true "
                f"so queues are created by the SQS stack instead of inline."
            )
