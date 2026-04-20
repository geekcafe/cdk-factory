"""
Unit tests for S3BucketConfig use_existing (canonical pattern only).
"""

from cdk_factory.configurations.resources.s3 import S3BucketConfig


class TestS3BucketConfig:
    """Test S3BucketConfig use_existing property."""

    def test_use_existing_true(self):
        """Verify use_existing='true' returns True."""
        config = S3BucketConfig({"name": "my-bucket", "use_existing": "true"})
        assert config.use_existing is True

    def test_exists_key_ignored(self):
        """Verify deprecated 'exists' key does NOT affect use_existing."""
        config = S3BucketConfig({"name": "my-bucket", "exists": "true"})
        assert config.use_existing is False

    def test_use_existing_false(self):
        """Verify use_existing='false' returns False."""
        config = S3BucketConfig({"name": "my-bucket", "use_existing": "false"})
        assert config.use_existing is False

    def test_neither_field(self):
        """Verify default is False when neither field is present."""
        config = S3BucketConfig({"name": "my-bucket"})
        assert config.use_existing is False
