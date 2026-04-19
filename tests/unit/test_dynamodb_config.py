"""
Unit tests for DynamoDBConfig TTL attribute property.
"""

from unittest.mock import MagicMock

from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig


class TestDynamoDBConfig:
    """Test DynamoDBConfig TTL attribute property."""

    def test_ttl_attribute_set(self):
        """Verify ttl_attribute returns configured value."""
        deployment = MagicMock()
        config = DynamoDBConfig(
            config={"name": "my-table", "ttl_attribute": "expires_at"},
            deployment=deployment,
        )
        assert config.ttl_attribute == "expires_at"

    def test_ttl_attribute_none(self):
        """Verify ttl_attribute returns None when absent."""
        deployment = MagicMock()
        config = DynamoDBConfig(
            config={"name": "my-table"},
            deployment=deployment,
        )
        assert config.ttl_attribute is None
