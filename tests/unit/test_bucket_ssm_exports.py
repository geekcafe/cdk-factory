"""
Unit tests for S3 Bucket Stack SSM export path generation.
Covers namespace mode, legacy mode, and disabled/no-config scenarios.

Updated: SSM config is now at the stack top level, not nested inside bucket.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.buckets.bucket_stack import S3BucketStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestBucketSSMExports:
    """Test S3 Bucket Stack SSM export path generation."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def workload_config(self):
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
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={"name": "test", "environment": "test"},
        )

    def test_bucket_ssm_namespace_bucket_name(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for bucket_name."""
        stack_config = StackConfig(
            {
                "name": "my-bucket-stack",
                "ssm": {
                    "auto_export": True,
                    "namespace": "my-ns",
                },
                "bucket": {
                    "name": "my-test-bucket",
                },
            },
            workload=workload_config.dictionary,
        )
        stack = S3BucketStack(
            app,
            "TestNsBucketName",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/my-ns/s3/my-bucket-stack/bucket_name"},
        )

    def test_bucket_ssm_namespace_bucket_arn(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for bucket_arn."""
        stack_config = StackConfig(
            {
                "name": "my-bucket-stack",
                "ssm": {
                    "auto_export": True,
                    "namespace": "my-ns",
                },
                "bucket": {
                    "name": "my-test-bucket",
                },
            },
            workload=workload_config.dictionary,
        )
        stack = S3BucketStack(
            app,
            "TestNsBucketArn",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/my-ns/s3/my-bucket-stack/bucket_arn"},
        )

    def test_bucket_ssm_legacy_bucket_name(
        self, app, deployment_config, workload_config
    ):
        """Verify legacy SSM path for bucket_name (no namespace, falls back to workload/env)."""
        stack_config = StackConfig(
            {
                "name": "my-bucket-stack",
                "ssm": {
                    "auto_export": True,
                },
                "bucket": {
                    "name": "my-test-bucket",
                },
            },
            workload=workload_config.dictionary,
        )
        stack = S3BucketStack(
            app,
            "TestLegacyBucketName",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/test-workload/test/s3/my-bucket-stack/bucket_name"},
        )

    def test_bucket_ssm_auto_export_disabled(
        self, app, deployment_config, workload_config
    ):
        """Verify zero SSM parameters when auto_export is False."""
        stack_config = StackConfig(
            {
                "name": "my-bucket-stack",
                "ssm": {
                    "auto_export": False,
                },
                "bucket": {
                    "name": "my-test-bucket",
                },
            },
            workload=workload_config.dictionary,
        )
        stack = S3BucketStack(
            app,
            "TestDisabledExport",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.resource_count_is("AWS::SSM::Parameter", 0)

    def test_bucket_ssm_no_config(self, app, deployment_config, workload_config):
        """Verify zero SSM parameters when no SSM block is present."""
        stack_config = StackConfig(
            {
                "name": "my-bucket-stack",
                "bucket": {
                    "name": "my-test-bucket",
                },
            },
            workload=workload_config.dictionary,
        )
        stack = S3BucketStack(
            app,
            "TestNoSsmConfig",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.resource_count_is("AWS::SSM::Parameter", 0)
