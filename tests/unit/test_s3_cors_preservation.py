"""
Preservation Property Tests — S3 Buckets Without CORS Config Unchanged

These tests verify that buckets WITHOUT cors_rules in their config continue
to behave identically after the CORS fix is applied. They establish the
baseline on UNFIXED code and must continue to pass after the fix.

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.buckets.bucket_stack import S3BucketStack
from cdk_factory.workload.workload_factory import WorkloadConfig


# ---------------------------------------------------------------------------
# Helpers (same pattern as bug condition test)
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


def _synthesize_bucket_template(bucket_config: dict, stack_id: str) -> dict:
    """Synthesize an S3BucketStack and return the template JSON."""
    app = App()
    workload = _make_workload_config()
    deployment = _make_deployment_config(workload)

    stack_config = StackConfig(
        {"bucket": bucket_config},
        workload=workload.dictionary,
    )

    stack = S3BucketStack(
        app,
        stack_id,
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    stack.build(stack_config, deployment, workload)
    template = Template.from_stack(stack)
    return template.to_json()


def _get_s3_buckets(template_json: dict) -> dict:
    """Extract all AWS::S3::Bucket resources from a template."""
    return {
        k: v
        for k, v in template_json["Resources"].items()
        if v["Type"] == "AWS::S3::Bucket"
    }


def _any_bucket_has_cors(template_json: dict) -> bool:
    """Check if any S3 bucket in the template has CorsConfiguration."""
    s3_buckets = _get_s3_buckets(template_json)
    return any(
        "CorsConfiguration" in bucket.get("Properties", {})
        for bucket in s3_buckets.values()
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

versioned_st = st.sampled_from(["true", "false"])
encryption_st = st.sampled_from(["s3_managed", "kms_managed"])
enforce_ssl_st = st.sampled_from(["true", "false"])
block_public_access_st = st.sampled_from(["block_all", "block_acls"])
removal_policy_st = st.sampled_from(["retain", "destroy"])
access_control_st = st.sampled_from(["private", "public_read"])


# ---------------------------------------------------------------------------
# Preservation Tests
# ---------------------------------------------------------------------------


class TestS3CorsPreservation:
    """
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

    Property 2: Preservation — Buckets Without CORS Config Unchanged

    For any S3 bucket config WITHOUT cors_rules, the synthesized CloudFormation
    template must NOT contain a CorsConfiguration property, and all other bucket
    properties must remain unchanged.
    """

    def test_no_cors_rules_key(self):
        """No cors_rules key: template has no CorsConfiguration.

        Synthesize S3BucketStack with config {"name": "test-bucket"} (no cors_rules)
        and verify the template has no CorsConfiguration property.

        **Validates: Requirements 3.1**
        """
        template_json = _synthesize_bucket_template(
            {"name": "test-bucket"}, "TestNoCorsKey"
        )
        assert not _any_bucket_has_cors(
            template_json
        ), "Bucket without cors_rules key should not have CorsConfiguration"

    def test_empty_cors_rules(self):
        """Empty cors_rules: template has no CorsConfiguration.

        Synthesize with {"name": "test-bucket", "cors_rules": []} (empty list)
        and verify the template has no CorsConfiguration property.

        **Validates: Requirements 3.1**
        """
        template_json = _synthesize_bucket_template(
            {"name": "test-bucket", "cors_rules": []}, "TestEmptyCorsRules"
        )
        assert not _any_bucket_has_cors(
            template_json
        ), "Bucket with empty cors_rules should not have CorsConfiguration"

    def test_other_properties_preserved(self):
        """Other properties preserved: encryption, versioning, SSL unchanged.

        Synthesize with versioned, encryption, enforce_ssl and verify those
        properties appear correctly in the template.

        **Validates: Requirements 3.3, 3.4**
        """
        template_json = _synthesize_bucket_template(
            {
                "name": "test-bucket",
                "versioned": "true",
                "encryption": "s3_managed",
                "enforce_ssl": "true",
            },
            "TestOtherPropsPreserved",
        )

        s3_buckets = _get_s3_buckets(template_json)
        assert len(s3_buckets) >= 1, "Expected at least one S3 bucket"

        # Verify no CORS
        assert not _any_bucket_has_cors(
            template_json
        ), "Bucket without cors_rules should not have CorsConfiguration"

        # Verify versioning is enabled
        bucket = next(iter(s3_buckets.values()))
        props = bucket.get("Properties", {})
        assert (
            props.get("VersioningConfiguration", {}).get("Status") == "Enabled"
        ), "Versioning should be enabled"

        # Verify encryption is present
        assert "BucketEncryption" in props, "Encryption should be configured"

    def test_use_existing_preserved(self):
        """use_existing preserved: bucket is imported, no CORS modification.

        S3BucketConfig with use_existing=true should import the bucket
        without attempting CORS configuration.

        **Validates: Requirements 3.2**
        """
        config = S3BucketConfig({"name": "test-bucket", "use_existing": "true"})
        assert config.use_existing is True

        # Synthesize and verify the stack builds without error
        # use_existing buckets are imported, not created — no CorsConfiguration possible
        app = App()
        workload = _make_workload_config()
        deployment = _make_deployment_config(workload)

        stack_config = StackConfig(
            {"bucket": {"name": "test-bucket", "use_existing": "true"}},
            workload=workload.dictionary,
        )

        stack = S3BucketStack(
            app,
            "TestUseExistingPreserved",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment, workload)
        template = Template.from_stack(stack)
        template_json = template.to_json()

        # Imported buckets don't create AWS::S3::Bucket resources — verify no
        # S3 bucket resources exist at all, or if they do, none have CORS
        resources = template_json.get("Resources", {})
        s3_buckets = {
            k: v for k, v in resources.items() if v.get("Type") == "AWS::S3::Bucket"
        }
        has_cors = any(
            "CorsConfiguration" in bucket.get("Properties", {})
            for bucket in s3_buckets.values()
        )
        assert not has_cors, "Imported bucket should not have CorsConfiguration"

    @given(
        versioned=versioned_st,
        encryption=encryption_st,
        enforce_ssl=enforce_ssl_st,
        block_public_access=block_public_access_st,
        removal_policy=removal_policy_st,
        access_control=access_control_st,
    )
    @settings(max_examples=30)
    def test_property_no_cors_for_any_config_without_cors_rules(
        self,
        versioned,
        encryption,
        enforce_ssl,
        block_public_access,
        removal_policy,
        access_control,
    ):
        """Property-based: For any bucket config WITHOUT cors_rules, the
        synthesized CloudFormation template must NOT contain CorsConfiguration.

        Generates random combinations of versioned, encryption, enforce_ssl,
        block_public_access, removal_policy, and access_control — all without
        cors_rules — and verifies no CorsConfiguration appears.

        **Validates: Requirements 3.1, 3.3, 3.4**
        """
        bucket_config = {
            "name": "test-bucket",
            "versioned": versioned,
            "encryption": encryption,
            "enforce_ssl": enforce_ssl,
            "block_public_access": block_public_access,
            "removal_policy": removal_policy,
            "access_control": access_control,
        }

        # Use a unique stack ID — CDK requires /^[A-Za-z][A-Za-z0-9-]*$/
        raw_id = (
            f"TestPBT-{versioned}-{encryption}-{enforce_ssl}"
            f"-{block_public_access}-{removal_policy}-{access_control}"
        )
        stack_id = raw_id.replace("_", "-")

        template_json = _synthesize_bucket_template(bucket_config, stack_id)

        # Core assertion: no CorsConfiguration
        assert not _any_bucket_has_cors(template_json), (
            f"Bucket config without cors_rules should not have CorsConfiguration. "
            f"Config: {bucket_config}"
        )

        # Verify the bucket was actually created with expected properties
        s3_buckets = _get_s3_buckets(template_json)
        assert len(s3_buckets) >= 1, "Expected at least one S3 bucket resource"
