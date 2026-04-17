"""
Lambda Group Loader — loads individual Lambda JSON files from a directory
and groups them by their declared 'stack' field.

Feature: iac-migration-parity
"""

import json
from pathlib import Path
from typing import Dict, List

from aws_lambda_powertools import Logger

logger = Logger(service="LambdaGroupLoader")

MAX_LAMBDAS_PER_STACK = 40


def load_and_group_lambda_configs(
    config_dir: str | Path,
) -> Dict[str, List[dict]]:
    """Load individual Lambda JSON files from a directory and group by 'stack' field.

    Args:
        config_dir: Path to directory containing individual Lambda JSON files.

    Returns:
        Dict mapping stack names to lists of Lambda resource configs
        (with 'stack' field stripped from each config). Keys are sorted.

    Raises:
        ValueError: If any Lambda config is missing the 'stack' field.
    """
    config_dir = Path(config_dir)
    groups: Dict[str, List[dict]] = {}

    for json_file in sorted(config_dir.glob("*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        stack_name = config.get("stack")
        if not stack_name:
            raise ValueError(
                f"Lambda config '{json_file.name}' is missing a 'stack' field. "
                "Every individual Lambda config must declare which stack it belongs to."
            )

        # Remove the 'stack' field — it's metadata for grouping, not a Lambda resource property
        resource = {k: v for k, v in config.items() if k != "stack"}
        groups.setdefault(stack_name, []).append(resource)

    # Warn about oversized groups
    for stack_name, configs in groups.items():
        if len(configs) > MAX_LAMBDAS_PER_STACK:
            logger.warning(
                f"Stack '{stack_name}' has {len(configs)} lambdas "
                f"(max recommended: {MAX_LAMBDAS_PER_STACK}). "
                "Consider splitting into smaller groups."
            )

    return dict(sorted(groups.items()))
