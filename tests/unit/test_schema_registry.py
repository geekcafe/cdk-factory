"""Unit tests for SchemaRegistry."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from cdk_factory.configurations.schema_registry import SchemaRegistry, _SCHEMAS_DIR


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the schema cache before each test."""
    SchemaRegistry.clear_cache()
    yield
    SchemaRegistry.clear_cache()


class TestGetSchema:
    """Tests for SchemaRegistry.get_schema()."""

    def test_returns_common_schema(self):
        schema = SchemaRegistry.get_schema("common")
        assert schema is not None
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "module" in schema["properties"]

    @pytest.mark.parametrize(
        "schema_name",
        [
            "dynamodb",
            "s3",
            "lambda",
            "api_gateway",
            "sqs",
            "cognito",
            "route53",
            "monitoring",
            "state_machine",
        ],
    )
    def test_returns_module_schemas(self, schema_name):
        schema = SchemaRegistry.get_schema(schema_name)
        assert schema is not None
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_missing_schema_returns_none(self):
        result = SchemaRegistry.get_schema("nonexistent_module")
        assert result is None

    def test_caches_loaded_schema(self):
        schema1 = SchemaRegistry.get_schema("common")
        schema2 = SchemaRegistry.get_schema("common")
        assert schema1 is schema2  # same object reference

    def test_clear_cache_resets(self):
        SchemaRegistry.get_schema("common")
        assert "common" in SchemaRegistry._cache
        SchemaRegistry.clear_cache()
        assert "common" not in SchemaRegistry._cache

    def test_malformed_json_returns_none(self, tmp_path):
        bad_file = tmp_path / "bad.schema.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        with patch("cdk_factory.configurations.schema_registry._SCHEMAS_DIR", tmp_path):
            SchemaRegistry.clear_cache()
            result = SchemaRegistry.get_schema("bad")
            assert result is None


class TestGetModuleSchema:
    """Tests for SchemaRegistry.get_module_schema()."""

    @pytest.mark.parametrize(
        "config_key,expected_schema_name",
        [
            ("dynamodb", "dynamodb"),
            ("bucket", "s3"),
            ("api_gateway", "api_gateway"),
            ("sqs", "sqs"),
            ("cognito", "cognito"),
            ("route53", "route53"),
            ("monitoring", "monitoring"),
            ("state_machine", "state_machine"),
            ("resources", "lambda"),
        ],
    )
    def test_detects_resource_key(self, config_key, expected_schema_name):
        config = {"name": "test", "module": "test_module", config_key: {}}
        result = SchemaRegistry.get_module_schema(config)
        assert result is not None
        key, schema = result
        assert key == config_key
        assert schema["title"] is not None

    def test_no_resource_key_returns_none(self):
        config = {"name": "test", "module": "test_module"}
        result = SchemaRegistry.get_module_schema(config)
        assert result is None
