"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Directory containing .schema.json files
_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Maps config resource key -> schema file base name
_RESOURCE_KEY_TO_SCHEMA = {
    "dynamodb": "dynamodb",
    "bucket": "s3",
    "api_gateway": "api_gateway",
    "sqs": "sqs",
    "cognito": "cognito",
    "route53": "route53",
    "monitoring": "monitoring",
    "state_machine": "state_machine",
    "resources": "lambda",
}


class SchemaRegistry:
    """Loads, caches, and provides JSON schema definitions."""

    _cache: dict[str, dict] = {}

    @classmethod
    def get_schema(cls, schema_name: str) -> Optional[dict]:
        """Return cached schema or load from schemas/ directory.

        Args:
            schema_name: e.g. "common", "dynamodb", "s3"
        Returns:
            Parsed JSON schema dict, or None if no schema file exists.
        """
        if schema_name in cls._cache:
            return cls._cache[schema_name]

        schema_path = _SCHEMAS_DIR / f"{schema_name}.schema.json"
        if not schema_path.exists():
            return None

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            cls._cache[schema_name] = schema
            return schema
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load schema '%s': %s", schema_name, exc)
            return None

    @classmethod
    def get_module_schema(cls, config: dict) -> Optional[Tuple[str, dict]]:
        """Detect the resource key in config and return (key, schema).

        Inspects config for known resource keys (dynamodb, bucket, sqs, etc.)
        and returns the matching schema.

        Returns:
            Tuple of (resource_key, schema_dict) or None if no match.
        """
        for resource_key, schema_name in _RESOURCE_KEY_TO_SCHEMA.items():
            if resource_key in config:
                schema = cls.get_schema(schema_name)
                if schema is not None:
                    return (resource_key, schema)
        return None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the schema cache (useful for testing)."""
        cls._cache.clear()
