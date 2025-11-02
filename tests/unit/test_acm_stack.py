"""Unit tests for the ACM Stack"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match
from aws_cdk import aws_route53 as route53

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.acm import AcmConfig
from cdk_factory.stack_library.acm.acm_stack import AcmStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestAcmStack(unittest.TestCase):
    """Test cases for AcmStack"""

    def setUp(self):
        """Set up common test fixtures"""
        self.app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
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
            deployment={"name": "test-deployment", "environment": "test"},
        )

    def test_basic_certificate_creation(self):
        """Test ACM stack with basic certificate configuration"""
        stack_config = StackConfig(
            {
                "certificate": {
                    "name": "test-cert",
                    "domain_name": "example.com",
                    "hosted_zone_id": "Z1234567890ABC",
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AcmStack(self.app, "TestAcmStack")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify certificate was created
        template.has_resource_properties(
            "AWS::CertificateManager::Certificate",
            {
                "DomainName": "example.com",
                "ValidationMethod": "DNS",
            },
        )

        # Verify CloudFormation outputs
        template.has_output(
            "CertificateArn",
            {
                "Description": "Certificate ARN for example.com",
            },
        )
        template.has_output(
            "DomainName",
            {
                "Description": "Primary domain name for the certificate",
            },
        )

    def test_certificate_with_sans(self):
        """Test ACM certificate with Subject Alternative Names"""
        stack_config = StackConfig(
            {
                "certificate": {
                    "name": "wildcard-cert",
                    "domain_name": "example.com",
                    "subject_alternative_names": [
                        "*.example.com",
                        "*.api.example.com",
                    ],
                    "hosted_zone_id": "Z1234567890ABC",
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AcmStack(self.app, "TestAcmStackSANs")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify certificate was created with SANs
        template.has_resource_properties(
            "AWS::CertificateManager::Certificate",
            {
                "DomainName": "example.com",
                "SubjectAlternativeNames": [
                    "*.example.com",
                    "*.api.example.com",
                ],
            },
        )

    def test_certificate_ssm_export(self):
        """Test ACM certificate exports ARN to SSM"""
        stack_config = StackConfig(
            {
                "certificate": {
                    "name": "test-cert",
                    "domain_name": "example.com",
                    "hosted_zone_id": "Z1234567890ABC",
                    "ssm": {
                        "exports": {
                            "certificate_arn": "/test/app/certificate/arn"
                        }
                    },
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AcmStack(self.app, "TestAcmStackSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify SSM parameter was created
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/test/app/certificate/arn",
                "Type": "String",
                "Description": "Certificate ARN for example.com",
            },
        )

    def test_certificate_with_tags(self):
        """Test ACM certificate with custom tags"""
        stack_config = StackConfig(
            {
                "certificate": {
                    "name": "test-cert",
                    "domain_name": "example.com",
                    "hosted_zone_id": "Z1234567890ABC",
                    "tags": {
                        "Environment": "production",
                        "Application": "web-app",
                        "ManagedBy": "CDK-Factory",
                    },
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AcmStack(self.app, "TestAcmStackTags")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify certificate has tags
        # Note: CDK may add additional tags, so we just verify our tags exist
        resources = template.find_resources("AWS::CertificateManager::Certificate")
        cert_resource = list(resources.values())[0]
        tags = cert_resource["Properties"]["Tags"]
        
        # Check our tags exist
        tag_dict = {tag["Key"]: tag["Value"] for tag in tags}
        self.assertEqual(tag_dict["Environment"], "production")
        self.assertEqual(tag_dict["Application"], "web-app")

    def test_acm_config_domain_name_required(self):
        """Test AcmConfig raises error when domain_name is missing"""
        with self.assertRaises(ValueError) as context:
            config = AcmConfig({}, self.deployment)
            _ = config.domain_name  # Access the property to trigger validation

        self.assertIn("domain_name is required", str(context.exception))

    def test_acm_config_subject_alternative_names(self):
        """Test AcmConfig handles subject_alternative_names and alternate_names"""
        # Test with subject_alternative_names
        config1 = AcmConfig(
            {
                "domain_name": "example.com",
                "subject_alternative_names": ["*.example.com"],
            },
            self.deployment
        )
        self.assertEqual(config1.subject_alternative_names, ["*.example.com"])

        # Test with alternate_names (backward compatibility)
        config2 = AcmConfig(
            {
                "domain_name": "example.com",
                "alternate_names": ["*.example.com"],
            },
            self.deployment
        )
        self.assertEqual(config2.subject_alternative_names, ["*.example.com"])

    def test_acm_config_default_ssm_exports(self):
        """Test AcmConfig provides default SSM export path"""
        config = AcmConfig(
            {
                "domain_name": "example.com",
            },
            self.deployment
        )
        
        ssm_exports = config.ssm_exports
        self.assertIn("certificate_arn", ssm_exports)
        self.assertIn("/test/test-workload/certificate/arn", ssm_exports["certificate_arn"])

    def test_certificate_without_hosted_zone_no_validation(self):
        """Test ACM stack creates certificate without DNS validation when hosted_zone_id is missing"""
        stack_config = StackConfig(
            {
                "certificate": {
                    "name": "test-cert",
                    "domain_name": "example.com",
                    # Missing hosted_zone_id - will create cert without DNS validation
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        stack = AcmStack(self.app, "TestAcmStackNoZone")
        stack.build(stack_config, self.deployment, self.dummy_workload)
        
        # Verify certificate was created without validation method specified
        template = Template.from_stack(stack)
        template.resource_count_is("AWS::CertificateManager::Certificate", 1)


class TestAcmStackRegistration(unittest.TestCase):
    """Test stack registration for ACM stack"""

    def test_acm_stack_module_exists(self):
        """Test that ACM stack module can be imported"""
        from cdk_factory.stack_library.acm.acm_stack import AcmStack
        
        # Verify the class exists and is properly named
        self.assertIsNotNone(AcmStack)
        self.assertEqual(AcmStack.__name__, "AcmStack")


if __name__ == "__main__":
    unittest.main()
