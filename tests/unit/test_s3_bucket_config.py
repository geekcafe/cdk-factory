"""
Unit tests for S3BucketConfig use_existing backward compatibility.
"""

from cdk_factory.configurations.resources.s3 import S3BucketConfig


class TestS3BucketConfig:
    """Test S3BucketConfig use_existing property."""

    def test_use_existing_true(self):
        """Verify use_existing='true' returns True."""
        config = S3BucketConfig({"name": "my-bucket", "use_existing": "true"})
        assert config.use_existing is True

    def test_exists_fallback(self):
        """Verify deprecated 'exists' field is used as fallback."""
        config = S3BucketConfig({"name": "my-bucket", "exists": "true"})
        assert config.use_existing is True

    def test_use_existing_precedence(self):
        """Verify use_existing takes precedence over exists."""
        config = S3BucketConfig(
            {"name": "my-bucket", "use_existing": "false", "exists": "true"}
        )
        assert config.use_existing is False

    def test_neither_field(self):
        """Verify default is False when neither field is present."""
        config = S3BucketConfig({"name": "my-bucket"})
        assert config.use_existing is False
