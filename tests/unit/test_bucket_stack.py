"""
Unit tests for the S3 Bucket Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.buckets.bucket_stack import S3BucketStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestS3BucketStack:
    """Test S3 Bucket stack with real CDK synthesis"""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing"""
        return App()

    @pytest.fixture
    def workload_config(self):
        """Create a basic workload config"""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                }
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={"name": "test", "environment": "test"},
        )

    def test_minimal_s3_bucket(self, app, deployment_config, workload_config):
        """Test S3 Bucket stack with minimal configuration"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "my-test-bucket",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestMinimalS3Bucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify S3 Bucket exists
        template.has_resource("AWS::S3::Bucket", {})

        # Verify bucket has encryption by default
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketEncryption": Match.object_like(
                    {
                        "ServerSideEncryptionConfiguration": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "ServerSideEncryptionByDefault": {
                                            "SSEAlgorithm": "AES256"
                                        }
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

        assert stack.bucket_config.name == "my-test-bucket"

    def test_s3_bucket_with_versioning(self, app, deployment_config, workload_config):
        """Test S3 Bucket with versioning enabled"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "versioned-bucket",
                    "versioned": "true",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestVersionedBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify versioning is enabled
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "VersioningConfiguration": {"Status": "Enabled"}
            },
        )

    def test_s3_bucket_with_ssl_enforcement(
        self, app, deployment_config, workload_config
    ):
        """Test S3 Bucket with SSL enforcement"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "ssl-bucket",
                    "enforce_ssl": "true",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestSSLBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify bucket policy exists for SSL enforcement
        template.has_resource("AWS::S3::BucketPolicy", {})

    def test_s3_bucket_with_access_control(
        self, app, deployment_config, workload_config
    ):
        """Test S3 Bucket with access control"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "acl-bucket",
                    "access_control": "private",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestACLBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify bucket has private access control
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "AccessControl": "Private",
            },
        )

    def test_s3_bucket_with_block_public_access(
        self, app, deployment_config, workload_config
    ):
        """Test S3 Bucket with public access blocked"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "blocked-bucket",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestBlockedBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify public access is blocked by default
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "PublicAccessBlockConfiguration": Match.object_like(
                    {
                        "BlockPublicAcls": True,
                        "BlockPublicPolicy": True,
                        "IgnorePublicAcls": True,
                        "RestrictPublicBuckets": True,
                    }
                )
            },
        )

    def test_s3_bucket_requires_name(self, app, deployment_config, workload_config):
        """Test that S3 Bucket requires a name"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "public_read_access": "true",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestNoNameBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

        # Build should raise ValueError for missing name
        with pytest.raises(ValueError, match="Bucket name is not defined"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_s3_bucket_requires_config(self, app, deployment_config, workload_config):
        """Test that S3 Bucket requires configuration"""
        stack_config = StackConfig(
            {
                "bucket": {}
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestEmptyConfigBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

        # Build should raise ValueError for empty config
        with pytest.raises(ValueError, match="S3 Bucket Configuration cannot be empty"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_s3_bucket_with_auto_delete_objects(
        self, app, deployment_config, workload_config
    ):
        """Test S3 Bucket with auto-delete objects on stack deletion"""
        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "auto-delete-bucket",
                    "auto_delete_objects": "true",
                    "removal_policy": "destroy",
                }
            },
            workload=workload_config.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestAutoDeleteBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify bucket exists
        template.has_resource("AWS::S3::Bucket", {})

        # Check deletion policy in template
        template_dict = template.to_json()
        s3_buckets = [
            r
            for r in template_dict["Resources"].values()
            if r["Type"] == "AWS::S3::Bucket"
        ]
        assert len(s3_buckets) >= 1
        # Auto-delete buckets should have Delete policy
        assert any(
            b.get("DeletionPolicy") == "Delete" or b.get("UpdateReplacePolicy") == "Delete"
            for b in s3_buckets
        )
