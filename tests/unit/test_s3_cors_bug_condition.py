"""
Bug Condition Exploration Tests — S3 CORS Configuration Silently Ignored

These tests demonstrate that the current S3BucketConfig class has no cors_rules
property and S3BucketConstruct does not pass CORS configuration to the s3.Bucket
constructor. When a consumer specifies cors_rules in their JSON config, it is
silently ignored — resulting in no CORS on the bucket and 403 on browser preflight.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App, aws_s3 as s3
from aws_cdk.assertions import Template

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.buckets.bucket_stack import S3BucketStack
from cdk_factory.workload.workload_factory import WorkloadConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workload_config() -> WorkloadConfig:
    return WorkloadConfig(
        {
            "workload": {
                "name": "test-workload",
                "devops": {"name": "test-devops"},
            }
        }
    )


def _make_deployment_config(workload: WorkloadConfig) -> DeploymentConfig:
    return DeploymentConfig(
        workload=workload.dictionary,
        deployment={"name": "test", "environment": "test"},
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

HTTP_METHODS = ["GET", "PUT", "POST", "DELETE", "HEAD"]

method_subsets_st = st.lists(
    st.sampled_from(HTTP_METHODS), min_size=1, max_size=5, unique=True
)

origin_st = st.lists(
    st.sampled_from(
        ["*", "https://example.com", "https://app.test.com", "http://localhost:3000"]
    ),
    min_size=1,
    max_size=3,
    unique=True,
)

header_st = st.lists(
    st.sampled_from(["*", "Content-Type", "Authorization", "X-Custom-Header"]),
    min_size=1,
    max_size=3,
    unique=True,
)

max_age_st = st.one_of(st.none(), st.integers(min_value=0, max_value=86400))


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestS3CorsBugCondition:
    """
    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**

    Property 1: Bug Condition — CORS Config Silently Ignored

    For any S3 bucket config with cors_rules specified, S3BucketConfig.cors_rules
    must return a non-empty list of s3.CorsRule objects. On unfixed code, this
    property will fail because the cors_rules property does not exist.
    """

    def test_config_property_missing(self):
        """Config property missing: S3BucketConfig ignores cors_rules.

        Create S3BucketConfig with cors_rules and assert config.cors_rules
        returns a non-empty list of s3.CorsRule objects.
        Will fail with AttributeError on unfixed code — confirms config ignores CORS.

        **Validates: Requirements 1.3, 2.3**
        """
        config = S3BucketConfig(
            {
                "name": "test-bucket",
                "cors_rules": [
                    {
                        "allowed_methods": ["GET", "PUT", "POST"],
                        "allowed_origins": ["*"],
                        "allowed_headers": ["*"],
                        "max_age": 3600,
                    }
                ],
            }
        )

        # This will raise AttributeError on unfixed code
        cors_rules = config.cors_rules
        assert isinstance(cors_rules, list)
        assert len(cors_rules) > 0
        assert isinstance(cors_rules[0], s3.CorsRule)

    def test_construct_synthesis_missing_cors(self):
        """Construct synthesis missing CORS: template has no CorsConfiguration.

        Synthesize an S3BucketStack with a config containing cors_rules and
        assert the CloudFormation template contains a CorsConfiguration property
        on the AWS::S3::Bucket resource. Will be absent on unfixed code.

        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
        """
        app = App()
        workload = _make_workload_config()
        deployment = _make_deployment_config(workload)

        stack_config = StackConfig(
            {
                "bucket": {
                    "name": "test-cors-bucket",
                    "cors_rules": [
                        {
                            "allowed_methods": ["GET", "PUT", "POST"],
                            "allowed_origins": ["*"],
                            "allowed_headers": ["*"],
                            "max_age": 3600,
                        }
                    ],
                }
            },
            workload=workload.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestCorsBucket",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment, workload)
        template = Template.from_stack(stack)

        # Check the template JSON directly for CorsConfiguration
        template_json = template.to_json()
        s3_buckets = {
            k: v
            for k, v in template_json["Resources"].items()
            if v["Type"] == "AWS::S3::Bucket"
        }
        has_cors = any(
            "CorsConfiguration" in bucket.get("Properties", {})
            for bucket in s3_buckets.values()
        )
        assert has_cors, (
            "Bug confirmed: No S3 bucket in the synthesized template has a "
            "CorsConfiguration property, even though cors_rules was specified in config."
        )

    @given(
        methods=method_subsets_st,
        origins=origin_st,
        headers=header_st,
        max_age=max_age_st,
    )
    @settings(max_examples=50)
    def test_property_cors_config_returns_matching_rules(
        self, methods, origins, headers, max_age
    ):
        """Property-based: For any valid CORS config, S3BucketConfig.cors_rules
        must return matching s3.CorsRule entries.

        Will fail on unfixed code because cors_rules property does not exist.

        **Validates: Requirements 1.3, 2.3**
        """
        rule_dict = {
            "allowed_methods": methods,
            "allowed_origins": origins,
            "allowed_headers": headers,
        }
        if max_age is not None:
            rule_dict["max_age"] = max_age

        config = S3BucketConfig(
            {
                "name": "test-bucket",
                "cors_rules": [rule_dict],
            }
        )

        # This will raise AttributeError on unfixed code
        cors_rules = config.cors_rules
        assert isinstance(cors_rules, list)
        assert len(cors_rules) == 1
        assert isinstance(cors_rules[0], s3.CorsRule)
