"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import List


class ConfigValidator:
    """Validates stack config dicts against canonical patterns.

    Runs validation on a raw stack config dict before any stack module
    processes it. Raises ValueError with prescriptive messages for
    deprecated or invalid patterns.
    """

    RESOURCE_KEYS_WITH_SSM: List[str] = [
        "dynamodb",
        "bucket",
        "cognito",
        "route53",
        "sqs",
        "api_gateway",
        "state_machine",
        "monitoring",
        "resources",
    ]

    @staticmethod
    def validate(stack_config: dict) -> None:
        """Run all validations on a stack config dict."""
        ConfigValidator._validate_name_present(stack_config)
        ConfigValidator._validate_no_nested_ssm(stack_config)
        ConfigValidator._validate_no_ssm_enabled(stack_config)
        ConfigValidator._validate_no_deprecated_exists(stack_config)
        ConfigValidator._validate_single_dependency_key(stack_config)
        ConfigValidator._validate_use_existing_has_name(stack_config)
        ConfigValidator._validate_no_stack_name_key(stack_config)

        # Schema validation
        from cdk_factory.configurations.schema_validator import SchemaValidator

        errors = SchemaValidator.validate(stack_config)
        if errors:
            raise ValueError(
                f"Schema validation failed for stack "
                f"'{stack_config.get('name', 'unknown')}':\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    @staticmethod
    def _validate_name_present(config: dict) -> None:
        """Validate that the 'name' field is present and non-empty."""
        name = config.get("name")
        if not name or not str(name).strip():
            raise ValueError(
                "'name' is required in every stack config. "
                "It must be the fully-qualified CloudFormation stack name. "
                "See MIGRATION.md."
            )

    @staticmethod
    def _validate_no_nested_ssm(config: dict) -> None:
        """Reject ssm blocks nested inside resource config keys."""
        for resource_key in ConfigValidator.RESOURCE_KEYS_WITH_SSM:
            resource = config.get(resource_key)
            if isinstance(resource, dict) and "ssm" in resource:
                raise ValueError(
                    f"SSM config must be at the stack top level. "
                    f"Move '{resource_key}.ssm' to a top-level 'ssm' block. "
                    f"See MIGRATION.md."
                )

    @staticmethod
    def _validate_no_ssm_enabled(config: dict) -> None:
        """Reject ssm.enabled — must use ssm.auto_export."""
        ssm = config.get("ssm")
        if isinstance(ssm, dict) and "enabled" in ssm:
            raise ValueError(
                "'ssm.enabled' is removed. "
                "Use 'ssm.auto_export: true' instead. "
                "See MIGRATION.md."
            )

    @staticmethod
    def _validate_no_deprecated_exists(config: dict) -> None:
        """Reject bucket.exists — must use bucket.use_existing."""
        bucket = config.get("bucket")
        if isinstance(bucket, dict) and "exists" in bucket:
            raise ValueError(
                "'bucket.exists' is removed. "
                "Use 'bucket.use_existing' instead. "
                "See MIGRATION.md."
            )

    @staticmethod
    def _validate_single_dependency_key(config: dict) -> None:
        """Reject configs with both depends_on and dependencies."""
        if "depends_on" in config and "dependencies" in config:
            raise ValueError(
                "Stack config contains both 'depends_on' and 'dependencies'. "
                "Use 'depends_on' only. "
                "See MIGRATION.md."
            )

    @staticmethod
    def _validate_use_existing_has_name(config: dict) -> None:
        """When use_existing is true, name must be present."""
        for resource_key in ConfigValidator.RESOURCE_KEYS_WITH_SSM:
            resource = config.get(resource_key)
            if not isinstance(resource, dict):
                continue
            use_existing = resource.get("use_existing")
            if str(use_existing).lower() == "true" or use_existing is True:
                if not resource.get("name"):
                    raise ValueError(
                        f"'{resource_key}' has 'use_existing: true' but no 'name' field. "
                        f"Provide the resource name. "
                        f"See MIGRATION.md."
                    )

    @staticmethod
    def _validate_no_stack_name_key(config: dict) -> None:
        """Reject stack_name key — name IS the actual stack name."""
        if "stack_name" in config:
            raise ValueError(
                "'stack_name' is not a valid key. "
                "Use 'name' for the actual stack name (construct ID / CloudFormation stack name) "
                "and 'description' for a human-readable label. "
                "See MIGRATION.md."
            )
