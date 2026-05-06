"""CDK Lambda configuration parser.

Recursively loads Lambda resource JSON files from a CDK config directory,
parses SQS queue definitions, classifies queue types, extracts SQS URL
environment variables, and resolves template placeholders.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueueConfig:
    """Parsed SQS queue configuration from a CDK resource JSON file."""

    queue_name: str
    queue_type: str  # "consumer" | "producer" | "dlq_consumer"
    description: str = ""
    has_dlq: bool = False
    visibility_timeout: int = 30
    delay_seconds: int = 0


@dataclass
class LambdaConfig:
    """Parsed Lambda configuration from a CDK resource JSON file."""

    name: str
    description: str = ""
    handler: str = ""
    timeout: int = 0
    memory_size: int = 128
    source_file: str = ""
    consumer_queues: List[QueueConfig] = field(default_factory=list)
    producer_queues: List[QueueConfig] = field(default_factory=list)
    dlq_consumer_queues: List[QueueConfig] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)
    sqs_url_references: Dict[str, str] = field(default_factory=dict)


def resolve_template_variables(
    value: str,
    env_vars: Dict[str, str],
) -> str:
    """Replace ``{{PLACEHOLDER}}`` patterns with values from env_vars.

    Args:
        value: String potentially containing ``{{PLACEHOLDER}}`` patterns.
        env_vars: Mapping of placeholder names to replacement values.

    Returns:
        String with all matched placeholders replaced.
    """
    if not env_vars:
        return value

    def _replace(match: re.Match) -> str:
        placeholder = match.group(1)
        return env_vars.get(placeholder, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", _replace, value)


def _parse_queue_entry(
    queue_data: Dict[str, Any],
    env_vars: Optional[Dict[str, str]],
) -> QueueConfig:
    """Parse a single SQS queue entry from the ``sqs.queues`` array."""
    raw_name = queue_data.get("queue_name", "")
    queue_name = resolve_template_variables(raw_name, env_vars or {})

    return QueueConfig(
        queue_name=queue_name,
        queue_type=queue_data.get("type", ""),
        description=queue_data.get("description", ""),
        has_dlq=queue_data.get("add_dead_letter_queue", False),
        visibility_timeout=queue_data.get("visibility_timeout_seconds", 30),
        delay_seconds=queue_data.get("delay_seconds", 0),
    )


def _parse_environment_variables(
    env_var_list: List[Dict[str, Any]],
    env_vars: Optional[Dict[str, str]],
) -> tuple:
    """Parse environment_variables array into a dict and extract SQS URL references.

    Returns:
        Tuple of (environment_variables dict, sqs_url_references dict).
    """
    environment_variables: Dict[str, str] = {}
    sqs_url_references: Dict[str, str] = {}

    for entry in env_var_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        value = entry.get("value", "")
        if not name:
            continue

        resolved_value = resolve_template_variables(value, env_vars or {})
        environment_variables[name] = resolved_value

        if name.startswith("SQS_URL_"):
            sqs_url_references[name] = resolved_value

    return environment_variables, sqs_url_references


def _parse_single_config(
    file_path: str,
    data: Dict[str, Any],
    env_vars: Optional[Dict[str, str]],
) -> Optional[LambdaConfig]:
    """Parse a single Lambda resource JSON dict into a LambdaConfig.

    Args:
        file_path: Path to the source JSON file (for diagnostics).
        data: Parsed JSON dictionary.
        env_vars: Template variable values for placeholder resolution.

    Returns:
        LambdaConfig if parsing succeeds, None if the config is invalid.
    """
    name = data.get("name")
    if not name:
        logger.warning("Missing required 'name' field in %s, skipping", file_path)
        return None

    # Extract handler from image_config.command
    handler = ""
    image_config = data.get("image_config", {})
    command = image_config.get("command", [])
    if command:
        handler = command[0]

    # Parse SQS queues
    consumer_queues: List[QueueConfig] = []
    producer_queues: List[QueueConfig] = []
    dlq_consumer_queues: List[QueueConfig] = []

    sqs_section = data.get("sqs", {})
    queues = sqs_section.get("queues", [])
    for queue_data in queues:
        queue_config = _parse_queue_entry(queue_data, env_vars)
        queue_type = queue_config.queue_type
        if queue_type == "consumer":
            consumer_queues.append(queue_config)
        elif queue_type == "producer":
            producer_queues.append(queue_config)
        elif queue_type == "dlq_consumer":
            dlq_consumer_queues.append(queue_config)
        else:
            logger.warning(
                "Unknown queue type '%s' in %s, skipping queue entry",
                queue_type,
                file_path,
            )

    # Parse environment variables
    env_var_raw = data.get("environment_variables", [])

    # environment_variables can be:
    #   1. A list of {"name": "...", "value": "..."} dicts (standard)
    #   2. A dict with "__inherits__" (cdk-factory resolves at synth time)
    # We only parse format 1; format 2 is skipped gracefully.
    if isinstance(env_var_raw, list):
        env_var_list = env_var_raw
    else:
        logger.debug(
            "environment_variables in %s is a %s (likely __inherits__), skipping",
            file_path,
            type(env_var_raw).__name__,
        )
        env_var_list = []

    environment_variables, sqs_url_references = _parse_environment_variables(
        env_var_list, env_vars
    )

    return LambdaConfig(
        name=name,
        description=data.get("description", ""),
        handler=handler,
        timeout=data.get("timeout", 0),
        memory_size=data.get("memory_size", 128),
        source_file=file_path,
        consumer_queues=consumer_queues,
        producer_queues=producer_queues,
        dlq_consumer_queues=dlq_consumer_queues,
        environment_variables=environment_variables,
        sqs_url_references=sqs_url_references,
    )


def parse_lambda_configs(
    config_dir: str,
    env_vars: Optional[Dict[str, str]] = None,
    resource_subdirs: Optional[List[str]] = None,
) -> List[LambdaConfig]:
    """Parse all Lambda resource JSON files under config_dir.

    Recursively walks ``configs/stacks/lambdas/resources/`` under *config_dir*,
    loads each ``.json`` file, extracts Lambda fields, classifies SQS queue
    entries by type, extracts ``SQS_URL_*`` environment variables, and resolves
    template placeholders.

    Args:
        config_dir: Path to CDK config root (e.g. ``"cdk/configs"``).
        env_vars: Template variable values for placeholder resolution
            (e.g. ``{"WORKLOAD_NAME": "acme-saas",
            "DEPLOYMENT_NAMESPACE": "development-dev"}``).
        resource_subdirs: Subdirectories to scan under
            ``stacks/lambdas/resources/``.  Defaults to all subdirectories.

    Returns:
        List of parsed :class:`LambdaConfig` objects.
    """
    resources_root = os.path.join(config_dir, "stacks", "lambdas", "resources")

    if not os.path.isdir(resources_root):
        raise FileNotFoundError(
            f"Config resource directory not found: {resources_root}"
        )

    configs: List[LambdaConfig] = []

    # Determine which subdirectories to scan
    if resource_subdirs is not None:
        scan_dirs = [
            os.path.join(resources_root, subdir) for subdir in resource_subdirs
        ]
    else:
        scan_dirs = [resources_root]

    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            logger.warning("Resource subdirectory not found: %s", scan_dir)
            continue

        for dirpath, _dirnames, filenames in os.walk(scan_dir):
            for filename in sorted(filenames):
                if not filename.endswith(".json"):
                    continue

                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to load %s: %s, skipping", file_path, exc)
                    continue

                if not isinstance(data, dict):
                    logger.warning(
                        "Expected JSON object in %s, got %s, skipping",
                        file_path,
                        type(data).__name__,
                    )
                    continue

                lambda_config = _parse_single_config(file_path, data, env_vars)
                if lambda_config is not None:
                    configs.append(lambda_config)

    return configs
