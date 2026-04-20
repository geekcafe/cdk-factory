"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import copy
import re
from typing import Any, List

from jsonschema import Draft7Validator

from cdk_factory.configurations.schema_registry import SchemaRegistry

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_][A-Z0-9_]*\}\}")


class SchemaValidator:
    """Validates config dicts against JSON schemas with placeholder awareness."""

    @staticmethod
    def validate(config: dict) -> List[str]:
        """Validate a stack config dict against common + module schemas.

        Returns:
            List of error message strings. Empty list means valid.
        """
        errors: List[str] = []

        # --- common schema ---
        common_schema = SchemaRegistry.get_schema("common")
        if common_schema is not None:
            preprocessed = SchemaValidator._preprocess_for_placeholders(
                copy.deepcopy(config), common_schema.get("properties")
            )
            validator = Draft7Validator(common_schema)
            for error in validator.iter_errors(preprocessed):
                errors.append(SchemaValidator._format_error(error))

        # --- module schema ---
        result = SchemaRegistry.get_module_schema(config)
        if result is not None:
            resource_key, module_schema = result
            resource_block = config.get(resource_key)
            if resource_block is not None:
                # For 'resources' (lambda), validate each item in the array
                if resource_key == "resources" and isinstance(resource_block, list):
                    for idx, item in enumerate(resource_block):
                        preprocessed_item = (
                            SchemaValidator._preprocess_for_placeholders(
                                copy.deepcopy(item), module_schema.get("properties")
                            )
                        )
                        validator = Draft7Validator(module_schema)
                        for error in validator.iter_errors(preprocessed_item):
                            errors.append(
                                SchemaValidator._format_error(
                                    error, prefix=f"resources[{idx}]"
                                )
                            )
                elif isinstance(resource_block, dict):
                    preprocessed_block = SchemaValidator._preprocess_for_placeholders(
                        copy.deepcopy(resource_block), module_schema.get("properties")
                    )
                    validator = Draft7Validator(module_schema)
                    for error in validator.iter_errors(preprocessed_block):
                        errors.append(
                            SchemaValidator._format_error(error, prefix=resource_key)
                        )

        return errors

    @staticmethod
    def _preprocess_for_placeholders(
        value: Any, schema_properties: dict | None = None
    ) -> Any:
        """Replace {{PLACEHOLDER}} tokens with type-appropriate sentinels.

        - String fields: leave as-is (placeholder is a valid string)
        - Boolean fields: replace with True
        - Integer fields: replace with 0
        - Nested dicts/arrays: recurse
        """
        if isinstance(value, dict):
            for key, val in value.items():
                prop_schema = None
                if schema_properties and key in schema_properties:
                    prop_schema = schema_properties[key]
                value[key] = SchemaValidator._preprocess_for_placeholders(
                    val, prop_schema
                )
            return value

        if isinstance(value, list):
            items_schema = None
            if schema_properties and isinstance(schema_properties, dict):
                items_def = schema_properties.get("items")
                if isinstance(items_def, dict):
                    items_schema = items_def.get("properties")
            return [
                SchemaValidator._preprocess_for_placeholders(item, items_schema)
                for item in value
            ]

        if isinstance(value, str) and PLACEHOLDER_RE.fullmatch(value):
            # Determine expected type from schema property definition
            if schema_properties and isinstance(schema_properties, dict):
                prop_type = schema_properties.get("type")
                types = prop_type if isinstance(prop_type, list) else [prop_type]
                if "integer" in types and "string" not in types:
                    return 0
                if "boolean" in types and "string" not in types:
                    return True
            # Default: leave as string (valid for string and union types)
            return value

        return value

    @staticmethod
    def _format_error(error, prefix: str = "") -> str:
        """Format a jsonschema.ValidationError into a readable string.

        Includes: JSON path, error message, expected type/values.
        """
        path_parts = list(error.absolute_path)
        if prefix:
            path_str = ".".join([prefix] + [str(p) for p in path_parts])
        else:
            path_str = ".".join(str(p) for p in path_parts)

        if path_str:
            return f"{path_str}: {error.message}"
        return error.message
