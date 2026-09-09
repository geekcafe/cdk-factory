"""
Unit tests for cross-stack OAC grants on the CloudFrontDistributionConstruct.

Verifies that `cloudfront.grant_read_to_distribution_arns` adds a bucket policy
statement granting the CloudFront service principal s3:GetObject with an
AWS:SourceArn condition, so a distribution defined in another stack can read
this (owned) bucket via OAC.
"""

import aws_cdk as cdk
import pytest
from aws_cdk import App, Stack
from aws_cdk import aws_s3 as s3
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.cloudfront.cloudfront_distribution_construct import (
    CloudFrontDistributionConstruct,
)


def _build_template(grant_arns):
    app = App()
    stack = Stack(
        app,
        "TestGrantStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    bucket = s3.Bucket(stack, "CdnBucket")

    cloudfront_dict = {"comment": "test cdn"}
    if grant_arns is not None:
        cloudfront_dict["grant_read_to_distribution_arns"] = grant_arns

    stack_config = StackConfig(
        {"name": "test-cdn", "cloudfront": cloudfront_dict},
        workload={"workload": {"name": "test", "devops": {"name": "test"}}},
    )

    CloudFrontDistributionConstruct(
        stack,
        "CDN",
        source_bucket=bucket,
        aliases=None,
        restrict_to_known_hosts=False,
        stack_config=stack_config,
    )

    return Template.from_stack(stack)


class TestCloudFrontGrantRead:
    def test_grant_read_to_literal_distribution_arn(self):
        """A literal distribution ARN produces a CloudFront-principal GetObject grant."""
        arn = "arn:aws:cloudfront::123456789012:distribution/E2EEJ9M0E5PJ12"
        template = _build_template([arn])

        template.has_resource_properties(
            "AWS::S3::BucketPolicy",
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Action": "s3:GetObject",
                                        "Principal": {
                                            "Service": "cloudfront.amazonaws.com"
                                        },
                                        "Condition": {
                                            "StringEquals": {"AWS:SourceArn": arn}
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_no_grant_when_not_configured(self):
        """Without the config key, no extra CloudFront-principal grant is added."""
        template = _build_template(None)
        # The bucket policy should not contain a static SourceArn to an external
        # distribution ARN (OAC for the owned distribution uses a CFn ref, not a literal).
        policies = template.find_resources("AWS::S3::BucketPolicy")
        rendered = str(policies)
        assert "E2EEJ9M0E5PJ12" not in rendered

    def test_invalid_type_raises(self):
        """A non-list value raises a clear ValueError."""
        with pytest.raises(ValueError, match="must be a list"):
            _build_template("arn:aws:cloudfront::123456789012:distribution/ABC")


def _build_template_account(grant_value):
    """Build a template using the account-scoped grant flag."""
    app = App()
    stack = Stack(
        app,
        "TestGrantAccountStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    bucket = s3.Bucket(stack, "CdnBucket")

    stack_config = StackConfig(
        {
            "name": "test-cdn",
            "cloudfront": {
                "comment": "test cdn",
                "grant_read_to_account": grant_value,
            },
        },
        workload={"workload": {"name": "test", "devops": {"name": "test"}}},
    )

    CloudFrontDistributionConstruct(
        stack,
        "CDN",
        source_bucket=bucket,
        aliases=None,
        restrict_to_known_hosts=False,
        stack_config=stack_config,
    )

    return Template.from_stack(stack)


class TestCloudFrontGrantReadToAccount:
    def test_account_scoped_grant_uses_current_account(self):
        """grant_read_to_account=true grants CloudFront in the current account via SourceAccount."""
        template = _build_template_account(True)

        template.has_resource_properties(
            "AWS::S3::BucketPolicy",
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Action": "s3:GetObject",
                                        "Principal": {
                                            "Service": "cloudfront.amazonaws.com"
                                        },
                                        "Condition": {
                                            "StringEquals": {
                                                "AWS:SourceAccount": "123456789012"
                                            }
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_account_scoped_grant_accepts_explicit_account_id(self):
        """A string account id scopes the grant to that specific account."""
        template = _build_template_account("999988887777")

        template.has_resource_properties(
            "AWS::S3::BucketPolicy",
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Condition": {
                                            "StringEquals": {
                                                "AWS:SourceAccount": "999988887777"
                                            }
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )
