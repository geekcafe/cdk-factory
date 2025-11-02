"""Unit tests for AcmConfig"""

import unittest

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.acm import AcmConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestAcmConfig(unittest.TestCase):
    """Test cases for AcmConfig"""

    def setUp(self):
        """Set up common test fixtures"""
        self.dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        self.deployment = DeploymentConfig(
            workload=self.dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "prod"},
        )

    def test_domain_name_required(self):
        """Test that domain_name is required"""
        config = AcmConfig({}, self.deployment)
        
        with self.assertRaises(ValueError) as context:
            _ = config.domain_name
        
        self.assertIn("domain_name is required", str(context.exception))

    def test_domain_name_provided(self):
        """Test domain_name when provided"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertEqual(config.domain_name, "example.com")

    def test_name_default(self):
        """Test default certificate name"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertEqual(config.name, "certificate")

    def test_name_custom(self):
        """Test custom certificate name"""
        config = AcmConfig(
            {
                "name": "my-custom-cert",
                "domain_name": "example.com",
            },
            self.deployment
        )
        
        self.assertEqual(config.name, "my-custom-cert")

    def test_subject_alternative_names(self):
        """Test subject_alternative_names property"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "subject_alternative_names": ["*.example.com", "www.example.com"],
            },
            self.deployment
        )
        
        self.assertEqual(
            config.subject_alternative_names,
            ["*.example.com", "www.example.com"]
        )

    def test_alternate_names_backward_compatibility(self):
        """Test backward compatibility with alternate_names"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "alternate_names": ["*.example.com"],
            },
            self.deployment
        )
        
        self.assertEqual(
            config.subject_alternative_names,
            ["*.example.com"]
        )

    def test_subject_alternative_names_priority(self):
        """Test that subject_alternative_names takes priority over alternate_names"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "subject_alternative_names": ["*.example.com"],
                "alternate_names": ["*.alt.example.com"],
            },
            self.deployment
        )
        
        # subject_alternative_names should win
        self.assertEqual(
            config.subject_alternative_names,
            ["*.example.com"]
        )

    def test_subject_alternative_names_default_empty(self):
        """Test default empty list for subject_alternative_names"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertEqual(config.subject_alternative_names, [])

    def test_hosted_zone_id(self):
        """Test hosted_zone_id property"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "hosted_zone_id": "Z1234567890ABC",
            },
            self.deployment
        )
        
        self.assertEqual(config.hosted_zone_id, "Z1234567890ABC")

    def test_hosted_zone_id_none(self):
        """Test hosted_zone_id when not provided"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertIsNone(config.hosted_zone_id)

    def test_hosted_zone_name(self):
        """Test hosted_zone_name property"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "hosted_zone_name": "example.com",
            },
            self.deployment
        )
        
        self.assertEqual(config.hosted_zone_name, "example.com")

    def test_validation_method_default(self):
        """Test default validation method is DNS"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertEqual(config.validation_method, "DNS")

    def test_validation_method_custom(self):
        """Test custom validation method"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "validation_method": "EMAIL",
            },
            self.deployment
        )
        
        self.assertEqual(config.validation_method, "EMAIL")

    def test_certificate_transparency_logging_preference(self):
        """Test certificate transparency logging preference"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "certificate_transparency_logging_preference": "ENABLED",
            },
            self.deployment
        )
        
        self.assertEqual(
            config.certificate_transparency_logging_preference,
            "ENABLED"
        )

    def test_certificate_transparency_logging_preference_none(self):
        """Test certificate transparency logging preference when not set"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertIsNone(config.certificate_transparency_logging_preference)

    def test_ssm_exports_custom(self):
        """Test custom SSM exports"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "ssm": {
                    "exports": {
                        "certificate_arn": "/custom/path/cert/arn"
                    }
                },
            },
            self.deployment
        )
        
        self.assertEqual(
            config.ssm_exports,
            {"certificate_arn": "/custom/path/cert/arn"}
        )

    def test_ssm_exports_default_with_deployment(self):
        """Test default SSM exports when deployment is provided"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        ssm_exports = config.ssm_exports
        
        self.assertIn("certificate_arn", ssm_exports)
        # Check that it contains expected components
        expected_path = "/prod/test-workload/certificate/arn"
        self.assertEqual(ssm_exports["certificate_arn"], expected_path)

    def test_ssm_exports_empty_without_deployment(self):
        """Test SSM exports returns empty dict when no deployment and no config"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            deployment=None
        )
        
        self.assertEqual(config.ssm_exports, {})

    def test_tags_empty_default(self):
        """Test default empty tags"""
        config = AcmConfig(
            {"domain_name": "example.com"},
            self.deployment
        )
        
        self.assertEqual(config.tags, {})

    def test_tags_custom(self):
        """Test custom tags"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
                "tags": {
                    "Environment": "production",
                    "Application": "web-app",
                    "ManagedBy": "CDK-Factory",
                },
            },
            self.deployment
        )
        
        self.assertEqual(
            config.tags,
            {
                "Environment": "production",
                "Application": "web-app",
                "ManagedBy": "CDK-Factory",
            }
        )

    def test_full_configuration(self):
        """Test full configuration with all properties"""
        full_config = {
            "name": "wildcard-cert",
            "domain_name": "example.com",
            "subject_alternative_names": [
                "*.example.com",
                "*.api.example.com",
            ],
            "hosted_zone_id": "Z1234567890ABC",
            "hosted_zone_name": "example.com",
            "validation_method": "DNS",
            "certificate_transparency_logging_preference": "ENABLED",
            "ssm": {
                "exports": {
                    "certificate_arn": "/prod/app/cert/arn"
                }
            },
            "tags": {
                "Environment": "production",
                "ManagedBy": "CDK-Factory",
            },
        }
        
        config = AcmConfig(full_config, self.deployment)
        
        # Verify all properties
        self.assertEqual(config.name, "wildcard-cert")
        self.assertEqual(config.domain_name, "example.com")
        self.assertEqual(
            config.subject_alternative_names,
            ["*.example.com", "*.api.example.com"]
        )
        self.assertEqual(config.hosted_zone_id, "Z1234567890ABC")
        self.assertEqual(config.hosted_zone_name, "example.com")
        self.assertEqual(config.validation_method, "DNS")
        self.assertEqual(
            config.certificate_transparency_logging_preference,
            "ENABLED"
        )
        self.assertEqual(
            config.ssm_exports,
            {"certificate_arn": "/prod/app/cert/arn"}
        )
        self.assertEqual(
            config.tags,
            {
                "Environment": "production",
                "ManagedBy": "CDK-Factory",
            }
        )


if __name__ == "__main__":
    unittest.main()
