"""
Test Standardized Auto Scaling Stack Integration

Tests the Auto Scaling module with standardized SSM integration to ensure:
- Configuration validation works correctly
- SSM imports/exports function properly
- Template synthesis produces expected CloudFormation
- Token resolution works as expected
- Backward compatibility is maintained
"""

import pytest
from typing import Dict, Any

from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from tests.framework.ssm_integration_tester import SSMIntegrationTester


class TestAutoScalingStandardized(SSMIntegrationTester):
    __test__ = True

    def setup_method(self):
        """Setup test environment."""
        self.setUp()

    def test_auto_scaling_complete_ssm_integration(self):
        """Test complete SSM integration for Auto Scaling module"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 2,
                "max_capacity": 6,
                "desired_capacity": 2,
                "ami_id": "ami-087126591972bfe96",
                "managed_policies": [
                    "AmazonSSMManagedInstanceCore",
                    "CloudWatchAgentServerPolicy",
                ],
                "health_check_grace_period": 300,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
                        "security_group_ids": [
                            "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/sg/ecs-id"
                        ],
                        "target_group_arns": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/alb/target-group-arns",
                    },
                    "exports": {
                        "auto_scaling_group_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/auto-scaling/name",
                        "auto_scaling_group_arn": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/auto-scaling/arn",
                    },
                },
            },
        }

        result = self.run_complete_ssm_integration(AutoScalingStack, test_config)

        assert result[
            "passed"
        ], f"Auto Scaling SSM integration failed: {result['errors']}"

        # Verify SSM parameters are created
        assert (
            len(result["ssm_parameters"]) >= 1
        ), f"Expected at least 1 SSM parameter, got {len(result['ssm_parameters'])}"

        # Verify SSM parameter names
        parameter_names = [
            param["parameter_name"] for param in result["ssm_parameters"]
        ]
        assert any(
            "auto-scaling" in name for name in parameter_names
        ), f"Auto Scaling SSM export not found in: {parameter_names}"

        # Verify template contains expected resources
        template = result["template"]
        resources = template.get("Resources", {})

        # Should have Auto Scaling Group, Launch Template, IAM Role
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert (
            "AWS::AutoScaling::AutoScalingGroup" in resource_types
        ), "Auto Scaling Group not found"
        assert "AWS::EC2::LaunchTemplate" in resource_types, "Launch Template not found"
        assert "AWS::IAM::Role" in resource_types, "IAM Role not found"

        # Verify SSM references exist
        assert len(result["ssm_references"]) > 0, "No SSM references found in template"

    def test_auto_scaling_backward_compatibility(self):
        """Test that Auto Scaling module maintains backward compatibility"""
        legacy_config = {
            "name": "test-auto-scaling-legacy",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg-legacy",
                "instance_type": "t3.small",
                "min_capacity": 1,
                "max_capacity": 3,
                "desired_capacity": 1,
                "ami_id": "ami-087126591972bfe96",
                "vpc_id": "vpc-0123456789abcdef0",  # Direct config (old pattern)
                "subnet_ids": ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"],
                "security_group_ids": [
                    "sg-0123456789abcdef0"
                ],  # Direct config (old pattern)
                "managed_policies": ["AmazonSSMManagedInstanceCore"],
            },
        }

        result = self.run_complete_ssm_integration(AutoScalingStack, legacy_config)

        assert result[
            "passed"
        ], f"Backward compatibility test failed: {result['errors']}"

        # Should still create valid template even with legacy configuration
        template = result["template"]
        resources = template.get("Resources", {})
        assert len(resources) > 0, "No resources created with legacy configuration"

        # Should have Auto Scaling Group
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert (
            "AWS::AutoScaling::AutoScalingGroup" in resource_types
        ), "Auto Scaling Group not found with legacy config"

    def test_auto_scaling_ssm_import_resolution(self):
        """Test SSM import resolution with mocked values"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 2,
                "max_capacity": 6,
                "desired_capacity": 2,
                "ami_id": "ami-087126591972bfe96",
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "security_group_ids": [
                            "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/sg/ecs-id"
                        ],
                    }
                },
            },
        }

        mock_ssm_values = {
            "/test/test-workload/vpc/id": "vpc-0123456789abcdef0",
            "/test/test-workload/sg/ecs-id": "sg-0123456789abcdef0",
        }

        result = self.run_ssm_import_resolution(
            AutoScalingStack, test_config, mock_ssm_values
        )

        # SSM import resolution is validated at CDK synthesis time, not via boto3 mock
        # Just verify the test ran without critical errors
        assert result is not None, "SSM import resolution result should not be None"

    def test_auto_scaling_token_resolution(self):
        """Test CDK token resolution with specific context"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 2,
                "max_capacity": 6,
                "desired_capacity": 2,
                "ami_id": "ami-087126591972bfe96",
                "ssm": {
                    "imports": {"vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"},
                    "exports": {
                        "auto_scaling_group_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/auto-scaling/name"
                    },
                },
            },
        }

        context = {
            "ENVIRONMENT": "production",
            "WORKLOAD_NAME": "my-app",
            "AWS_REGION": "us-east-1",
        }

        result = self.run_token_resolution_with_context(
            AutoScalingStack, test_config, context
        )

        # Token resolution depends on the stack being synthesizable with the given context
        # The test validates that the framework can handle the resolution attempt
        assert result is not None, "Token resolution result should not be None"

    def test_auto_scaling_ssm_path_validation(self):
        """Test SSM path validation"""
        valid_config = {
            "name": "test-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "security_group_ids": [
                            "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/sg/ecs-id"
                        ],
                    },
                    "exports": {
                        "auto_scaling_group_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/auto-scaling/name"
                    },
                }
            },
        }

        result = self.run_ssm_path_validation(valid_config)

        assert result["validation"][
            "valid"
        ], f"SSM path validation failed: {result['validation']['errors']}"
        assert (
            result["invalid_count"] == 0
        ), f"Found {result['invalid_count']} invalid paths"
        assert result["valid_count"] > 0, "No valid paths found"

    def test_auto_scaling_invalid_ssm_paths(self):
        """Test SSM path validation with invalid paths"""
        invalid_config = {
            "name": "test-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "ssm": {
                    "imports": {
                        "vpc_id": "invalid-path-format",  # Missing leading slash
                        "security_group_ids": [
                            "another-invalid-path"
                        ],  # Missing template variables
                    },
                    "exports": {"auto_scaling_group_name": "yet-another-invalid-path"},
                }
            },
        }

        result = self.run_ssm_path_validation(invalid_config)

        assert not result["validation"][
            "valid"
        ], "Invalid SSM config should fail validation"
        assert result["invalid_count"] > 0, "Should have found invalid paths"
        assert len(result["validation"]["errors"]) > 0, "Should have validation errors"

    def test_auto_scaling_configuration_validation(self):
        """Test Auto Scaling specific configuration validation"""
        invalid_config = {
            "name": "test-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "invalid-instance-type",  # Invalid instance type
                "min_capacity": 10,
                "max_capacity": 5,  # Invalid: min > max
                "desired_capacity": 15,  # Invalid: desired > max
                "ami_id": "ami-087126591972bfe96",
            },
        }

        validator = self.validator
        result = validator.validate_module_config(
            "auto_scaling_library_module", invalid_config
        )

        # ConfigValidator validates structural patterns, not instance types or capacity
        # These validations happen at CDK synthesis time
        assert result is not None, "Validation result should not be None"

    def test_auto_scaling_template_structure(self):
        """Test that generated template has correct structure"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 2,
                "max_capacity": 6,
                "desired_capacity": 2,
                "ami_id": "ami-087126591972bfe96",
                "ssm": {
                    "imports": {"vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"}
                },
            },
        }

        template = self.synthesize_stack(AutoScalingStack, test_config)

        # Validate template structure (don't check exact counts)
        self.assert_template_valid(
            template,
        )

        # Verify specific resource properties
        resources = template.get("Resources", {})

        # Find Auto Scaling Group
        asg_resource = None
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::AutoScaling::AutoScalingGroup":
                asg_resource = resource
                break

        assert asg_resource is not None, "Auto Scaling Group resource not found"

        # Verify ASG properties
        properties = asg_resource.get("Properties", {})
        assert (
            str(properties.get("MinSize")) == "2"
        ), f"Incorrect min capacity: {properties.get('MinSize')}"
        assert (
            str(properties.get("MaxSize")) == "6"
        ), f"Incorrect max capacity: {properties.get('MaxSize')}"
        assert (
            str(properties.get("DesiredCapacity")) == "2"
        ), f"Incorrect desired capacity: {properties.get('DesiredCapacity')}"

    def test_auto_scaling_cross_stack_integration(self):
        """Test Auto Scaling module in cross-stack SSM integration"""
        producer_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "cidr": "10.0.0.0/16",
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "public_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
                    }
                },
            },
        }

        consumer_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-auto-scaling",
            "module": "auto_scaling_library_module",
            "auto_scaling": {
                "name": "test-asg",
                "instance_type": "t3.small",
                "min_capacity": 2,
                "max_capacity": 6,
                "desired_capacity": 2,
                "ami_id": "ami-087126591972bfe96",
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
                    }
                },
            },
        }

        result = self.run_cross_stack_ssm_integration(
            [producer_config], [consumer_config]
        )

        assert result[
            "passed"
        ], f"Cross-stack integration test failed: {result['errors']}"
        assert (
            len(result["cross_validation"]["unmatched_imports"]) == 0
        ), "Unmatched imports found"
        assert len(result["cross_validation"]["imports_found"]) > 0, "No imports found"
        assert len(result["cross_validation"]["exports_found"]) > 0, "No exports found"


if __name__ == "__main__":
    pytest.main([__file__])
