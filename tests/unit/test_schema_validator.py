"""Unit tests for SchemaValidator."""

import pytest

from cdk_factory.configurations.schema_registry import SchemaRegistry
from cdk_factory.configurations.schema_validator import SchemaValidator


@pytest.fixture(autouse=True)
def clear_cache():
    SchemaRegistry.clear_cache()
    yield
    SchemaRegistry.clear_cache()


class TestValidConfigs:
    """Valid configs should return empty error list."""

    def test_minimal_valid_config(self):
        config = {"name": "my-stack", "module": "dynamodb_stack"}
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_valid_dynamodb_config(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "enabled": True,
            "dynamodb": {
                "name": "my-table",
                "gsi_count": 5,
                "use_existing": False,
            },
        }
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_valid_s3_config(self):
        config = {
            "name": "my-stack",
            "module": "s3_stack",
            "bucket": {
                "name": "my-bucket",
                "versioned": True,
                "encryption": "s3_managed",
            },
        }
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_valid_lambda_config(self):
        config = {
            "name": "my-stack",
            "module": "lambda_stack",
            "resources": [
                {
                    "name": "my-function",
                    "handler": "index.handler",
                    "runtime": "python3.12",
                    "memory_size": 256,
                    "timeout": 30,
                }
            ],
        }
        errors = SchemaValidator.validate(config)
        assert errors == []


class TestMissingRequiredFields:
    """Missing required fields should produce errors with field path."""

    def test_missing_name(self):
        config = {"module": "dynamodb_stack"}
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("name" in e for e in errors)

    def test_missing_module(self):
        config = {"name": "my-stack"}
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("module" in e for e in errors)

    def test_missing_dynamodb_name(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {"gsi_count": 5},
        }
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("name" in e for e in errors)

    def test_missing_lambda_resource_name(self):
        config = {
            "name": "my-stack",
            "module": "lambda_stack",
            "resources": [{"handler": "index.handler"}],
        }
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("name" in e for e in errors)


class TestWrongTypes:
    """Wrong types should produce errors with expected type."""

    def test_gsi_count_string(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {"name": "table", "gsi_count": "abc"},
        }
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("integer" in e for e in errors)

    def test_enabled_string(self):
        config = {"name": "my-stack", "module": "test", "enabled": "yes"}
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("boolean" in e for e in errors)

    def test_depends_on_string(self):
        config = {"name": "my-stack", "module": "test", "depends_on": "other-stack"}
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("array" in e for e in errors)


class TestPlaceholders:
    """Placeholder tokens should pass validation."""

    def test_placeholder_in_string_field(self):
        config = {
            "name": "{{WORKLOAD_NAME}}-my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {"name": "{{TABLE_NAME}}"},
        }
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_placeholder_in_boolean_field(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {
                "name": "table",
                "use_existing": "{{USE_EXISTING}}",
            },
        }
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_placeholder_in_integer_field(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {
                "name": "table",
                "gsi_count": "{{GSI_COUNT}}",
            },
        }
        errors = SchemaValidator.validate(config)
        assert errors == []

    def test_placeholder_in_top_level_boolean(self):
        config = {
            "name": "my-stack",
            "module": "test",
            "enabled": "{{ENABLED}}",
        }
        errors = SchemaValidator.validate(config)
        assert errors == []


class TestMultipleErrors:
    """Multiple errors should all be collected in a single pass."""

    def test_collects_all_errors(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "enabled": "not-a-bool",
            "depends_on": "not-an-array",
            "dynamodb": {"name": "table", "gsi_count": "abc"},
        }
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 3


class TestErrorFormat:
    """Error messages should include JSON path and description."""

    def test_error_contains_path(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {"name": "table", "gsi_count": "abc"},
        }
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("dynamodb" in e and "gsi_count" in e for e in errors)

    def test_error_contains_description(self):
        config = {"module": "test"}
        errors = SchemaValidator.validate(config)
        assert len(errors) >= 1
        assert any("required" in e.lower() or "type" in e.lower() for e in errors)


class TestIdempotence:
    """Validating the same config twice should produce identical results."""

    def test_same_results_twice(self):
        config = {
            "name": "my-stack",
            "module": "dynamodb_stack",
            "dynamodb": {"name": "table", "gsi_count": "abc"},
        }
        errors1 = SchemaValidator.validate(config)
        errors2 = SchemaValidator.validate(config)
        assert errors1 == errors2
