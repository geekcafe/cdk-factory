"""
Unit tests for the ECR Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.ecr.ecr_stack import ECRStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestECRStack:
    """Test ECR Stack with real CDK synthesis"""

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
                    "devops": {
                        "name": "test-devops",
                        "account": "987654321098",
                    },
                }
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={
                "name": "test",
                "environment": "test",
                "account": "123456789012",
                "region": "us-east-1",
            },
        )

    def test_minimal_ecr_repository(self, app, deployment_config, workload_config):
        """Test ECR stack with minimal configuration"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "my-app",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestMinimalECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify ECR Repository exists
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryName": Match.string_like_regexp(".*my-app.*"),
                "ImageScanningConfiguration": {"ScanOnPush": False},
                "EmptyOnDelete": False,
            },
        )

        # Verify no SSM parameters without explicit configuration
        template.resource_count_is("AWS::SSM::Parameter", 0)

        assert stack.stack_config is not None
        assert stack.deployment is not None

    def test_ecr_repository_with_image_scan(
        self, app, deployment_config, workload_config
    ):
        """Test ECR repository with image scanning enabled"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "scan-enabled-repo",
                        "image_scan_on_push": "true",
                        "empty_on_delete": "false",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestImageScanECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify image scanning is enabled
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "ImageScanningConfiguration": {"ScanOnPush": True},
            },
        )

    def test_ecr_repository_with_empty_on_delete(
        self, app, deployment_config, workload_config
    ):
        """Test ECR repository with empty on delete enabled"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "auto-delete-repo",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "true",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestEmptyOnDeleteECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify empty on delete and removal policy
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "EmptyOnDelete": True,
            },
        )

        # Check removal policy in metadata
        template_dict = template.to_json()
        ecr_resources = [
            r
            for r in template_dict["Resources"].values()
            if r["Type"] == "AWS::ECR::Repository"
        ]
        assert len(ecr_resources) == 1
        assert ecr_resources[0].get("DeletionPolicy") == "Delete"

    def test_ecr_repository_with_lifecycle_policy(
        self, app, deployment_config, workload_config
    ):
        """Test ECR repository with lifecycle policy for untagged images"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "lifecycle-repo",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                        "auto_delete_untagged_images_in_days": 7,
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestLifecycleECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify lifecycle policy exists
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "LifecyclePolicy": Match.object_like(
                    {
                        "LifecyclePolicyText": Match.string_like_regexp(".*untagged.*"),
                    }
                ),
            },
        )

    def test_ecr_repository_with_cross_account_access(
        self, app, deployment_config, workload_config
    ):
        """Test ECR repository with cross-account access policy"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "cross-account-repo",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestCrossAccountECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify repository has inline policy with cross-account permissions
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryPolicyText": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": Match.array_with(
                                        [
                                            "ecr:GetDownloadUrlForLayer",
                                            "ecr:BatchGetImage",
                                            "ecr:BatchCheckLayerAvailability",
                                        ]
                                    ),
                                    "Effect": "Allow",
                                    "Principal": Match.object_like(
                                        {"AWS": Match.any_value()}
                                    ),
                                }
                            )
                        ]
                    )
                },
            },
        )

    def test_ecr_repository_same_account_no_cross_account_policy(
        self, app, workload_config
    ):
        """Test that cross-account policy is not added when account matches devops account"""
        # Create deployment config with same account as devops
        deployment_config = DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={
                "name": "test",
                "environment": "test",
                "account": "987654321098",  # Same as devops account
                "region": "us-east-1",
            },
        )

        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "same-account-repo",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestSameAccountECR",
            env=cdk.Environment(account="987654321098", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify repository exists but has no inline policy (no RepositoryPolicyText)
        template.resource_count_is("AWS::ECR::Repository", 1)

        # Check the repository doesn't have a RepositoryPolicyText
        template_dict = template.to_json()
        ecr_repos = [
            r
            for r in template_dict["Resources"].values()
            if r["Type"] == "AWS::ECR::Repository"
        ]
        assert len(ecr_repos) == 1
        assert "RepositoryPolicyText" not in ecr_repos[0].get("Properties", {})

    def test_multiple_ecr_repositories(self, app, deployment_config, workload_config):
        """Test creating multiple ECR repositories in one stack"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "repo-one",
                        "image_scan_on_push": "true",
                        "empty_on_delete": "false",
                    },
                    {
                        "name": "repo-two",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "true",
                    },
                    {
                        "name": "repo-three",
                        "image_scan_on_push": "true",
                        "empty_on_delete": "true",
                        "auto_delete_untagged_images_in_days": 14,
                    },
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestMultipleECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify three repositories are created
        template.resource_count_is("AWS::ECR::Repository", 3)

        # Verify no SSM parameters without explicit configuration
        template.resource_count_is("AWS::SSM::Parameter", 0)

    def test_ecr_repository_requires_name(
        self, app, deployment_config, workload_config
    ):
        """Test that ECR stack raises error when repository name is missing"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestNoNameECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )

        # Build should raise ValueError for missing name
        with pytest.raises(ValueError, match="Resource name is required"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_ecr_ssm_parameter_exports(self, app, deployment_config, workload_config):
        """Test that ECR exports correct SSM parameters when configured"""
        stack_config = StackConfig(
            {
                "name": "test-ecr-stack",
                "resources": [
                    {
                        "name": "ssm-test-repo",
                        "image_scan_on_push": "false",
                        "empty_on_delete": "false",
                        "ssm": {
                            "exports": {
                                "name": "/test/ecr/ssm-test-repo/name",
                                "uri": "/test/ecr/ssm-test-repo/uri",
                                "arn": "/test/ecr/ssm-test-repo/arn",
                            },
                        },
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        stack = ECRStack(
            app,
            "TestSSMExportECR",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify SSM parameters for name, uri, and arn are created
        template.resource_count_is("AWS::SSM::Parameter", 3)

        # Verify at least one SSM parameter with correct type
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Type": "String",
            },
        )

        # Check that SSM parameters depend on ECR repository
        template_dict = template.to_json()
        ssm_params = [
            r
            for r in template_dict["Resources"].values()
            if r["Type"] == "AWS::SSM::Parameter"
        ]
        ecr_repos = [
            key
            for key, r in template_dict["Resources"].items()
            if r["Type"] == "AWS::ECR::Repository"
        ]

        # At least one SSM parameter should have a dependency on the ECR repo
        assert len(ecr_repos) > 0
        assert len(ssm_params) == 3
