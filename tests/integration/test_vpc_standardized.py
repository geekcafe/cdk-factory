"""
Test Standardized VPC Stack Integration

Tests the VPC module with standardized SSM integration to ensure:
- Configuration validation works correctly
- SSM imports/exports function properly
- Template synthesis produces expected CloudFormation
- Token resolution works as expected
- Backward compatibility is maintained
- VPC-specific features work correctly
"""

import pytest
from typing import Dict, Any

from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from tests.framework.ssm_integration_tester import SSMIntegrationTester


class TestVPCStandardized(SSMIntegrationTester):
    
    def test_vpc_complete_ssm_integration(self):
        """Test complete SSM integration for VPC module"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "enable_dns_hostnames": True,
                "enable_dns_support": True,
                "enable_s3_endpoint": True,
                "subnets": {
                    "public": {
                        "enabled": True,
                        "cidr_mask": 24,
                        "map_public_ip": True
                    },
                    "private": {
                        "enabled": True,
                        "cidr_mask": 24
                    },
                    "isolated": {
                        "enabled": False,
                        "cidr_mask": 24
                    }
                },
                "nat_gateways": {
                    "count": 1
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "public_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
                        "private_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/private-subnet-ids",
                        "public_route_table_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-route-table-ids",
                        "private_route_table_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/private-route-table-ids",
                        "nat_gateway_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/nat-gateway-ids",
                        "internet_gateway_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/internet-gateway-id"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(VpcStack, test_config)
        
        assert result["passed"], f"VPC SSM integration failed: {result['errors']}"
        
        # Verify SSM parameters are created
        assert len(result["ssm_parameters"]) >= 5, f"Expected at least 5 SSM parameters, got {len(result['ssm_parameters'])}"
        
        # Verify SSM parameter names
        parameter_names = [param["parameter_name"] for param in result["ssm_parameters"]]
        assert any("vpc/id" in name for name in parameter_names), "VPC ID export not found"
        assert any("vpc/public-subnet-ids" in name for name in parameter_names), "Public subnet IDs export not found"
        assert any("vpc/private-subnet-ids" in name for name in parameter_names), "Private subnet IDs export not found"
        
        # Verify template contains expected resources
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have VPC, Subnets, NAT Gateway, Internet Gateway, Route Tables
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert "AWS::EC2::VPC" in resource_types, "VPC not found"
        assert "AWS::EC2::Subnet" in resource_types, "Subnets not found"
        assert "AWS::EC2::NatGateway" in resource_types, "NAT Gateway not found"
        assert "AWS::EC2::InternetGateway" in resource_types, "Internet Gateway not found"
        assert "AWS::EC2::RouteTable" in resource_types, "Route Tables not found"
        
        # Verify outputs are created
        outputs = template.get("Outputs", {})
        assert len(outputs) >= 5, f"Expected at least 5 outputs, got {len(outputs)}"
    
    def test_vpc_backward_compatibility(self):
        """Test that VPC module maintains backward compatibility"""
        legacy_config = {
            "name": "test-vpc-legacy",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-legacy",
                "cidr": "10.1.0.0/16",
                "max_azs": 2,
                "enable_dns_hostnames": True,
                "enable_dns_support": True,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24}
                }
            }
        }
        
        result = self.test_complete_ssm_integration(VpcStack, legacy_config)
        
        assert result["passed"], f"Backward compatibility test failed: {result['errors']}"
        
        # Should still create valid template even with legacy configuration
        template = result["template"]
        resources = template.get("Resources", {})
        assert len(resources) > 0, "No resources created with legacy configuration"
        
        # Should have VPC
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert "AWS::EC2::VPC" in resource_types, "VPC not found with legacy config"
    
    def test_vpc_with_interface_endpoints(self):
        """Test VPC with interface endpoints enabled"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-endpoints",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "enable_interface_endpoints": True,
                "interface_endpoints": ["ecr.api", "ecr.dkr", "ec2", "ecs"],
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24}
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(VpcStack, test_config)
        
        assert result["passed"], f"VPC with interface endpoints test failed: {result['errors']}"
        
        # Verify interface endpoints are created
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have VPC endpoints
        endpoint_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::VPCEndpoint"]
        assert len(endpoint_resources) >= 4, f"Expected at least 4 interface endpoints, got {len(endpoint_resources)}"
    
    def test_vpc_with_isolated_subnets(self):
        """Test VPC with isolated subnets enabled"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-isolated",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24},
                    "isolated": {"enabled": True, "cidr_mask": 24}
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "isolated_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/isolated-subnet-ids"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(VpcStack, test_config)
        
        assert result["passed"], f"VPC with isolated subnets test failed: {result['errors']}"
        
        # Verify isolated subnets are created
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have isolated subnets
        subnet_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::Subnet"]
        assert len(subnet_resources) >= 6, f"Expected at least 6 subnets (2 public, 2 private, 2 isolated), got {len(subnet_resources)}"
        
        # Verify SSM export for isolated subnets
        parameter_names = [param["parameter_name"] for param in result["ssm_parameters"]]
        assert any("vpc/isolated-subnet-ids" in name for name in parameter_names), "Isolated subnet IDs export not found"
    
    def test_vpc_ssm_path_validation(self):
        """Test SSM path validation for VPC module"""
        valid_config = {
            "name": "test-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "public_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids"
                    }
                }
            }
        }
        
        result = self.test_ssm_path_validation(valid_config)
        
        assert result["validation"]["valid"], f"SSM path validation failed: {result['validation']['errors']}"
        assert result["invalid_count"] == 0, f"Found {result['invalid_count']} invalid paths"
        assert result["valid_count"] > 0, "No valid paths found"
    
    def test_vpc_invalid_cidr_validation(self):
        """Test VPC CIDR validation"""
        invalid_config = {
            "name": "test-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-invalid",
                "cidr": "invalid-cidr-format",  # Invalid CIDR
                "max_azs": 2
            }
        }
        
        validator = self.validator
        result = validator.validate_module_config("vpc_library_module", invalid_config)
        
        assert not result.valid, "Invalid CIDR should fail validation"
        assert len(result.errors) > 0, "Should have validation errors"
        
        # Check for specific validation error
        error_text = " ".join(result.errors).lower()
        assert "cidr" in error_text, "Should validate CIDR format"
    
    def test_vpc_invalid_max_azs_validation(self):
        """Test VPC max AZs validation"""
        invalid_config = {
            "name": "test-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-invalid",
                "cidr": "10.0.0.0/16",
                "max_azs": 7  # Invalid: max 6 AZs
            }
        }
        
        validator = self.validator
        result = validator.validate_module_config("vpc_library_module", invalid_config)
        
        assert not result.valid, "Invalid max_azs should fail validation"
        assert len(result.errors) > 0, "Should have validation errors"
        
        # Check for specific validation error
        error_text = " ".join(result.errors).lower()
        assert "max_azs" in error_text or "az" in error_text, "Should validate max_azs"
    
    def test_vpc_token_resolution(self):
        """Test CDK token resolution with specific context"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        context = {
            "ENVIRONMENT": "production",
            "WORKLOAD_NAME": "my-app",
            "AWS_REGION": "us-east-1"
        }
        
        result = self.test_token_resolution_with_context(VpcStack, test_config, context)
        
        assert result["passed"], f"Token resolution test failed: {result.get('error', 'Unknown error')}"
        
        # Verify token validation
        token_validation = result.get("token_validation", {})
        assert token_validation.get("tokens_found", 0) > 0, "No tokens found in template"
        assert token_validation.get("valid_tokens", 0) > 0, "No valid tokens found"
        assert len(token_validation.get("invalid_tokens", [])) == 0, f"Invalid tokens found: {token_validation.get('invalid_tokens', [])}"
    
    def test_vpc_template_structure(self):
        """Test that generated template has correct structure"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "enable_s3_endpoint": True,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24}
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        template = self.synthesize_stack(VpcStack, test_config)
        
        # Validate template structure
        self.assert_template_valid(
            template,
            expected_resources=8,  # VPC, 4 subnets, NAT Gateway, Internet Gateway, Route Table, S3 Endpoint
            expected_ssm_params=1,  # VPC ID export
            expected_outputs=7  # VPC ID, public/private subnet IDs, route table IDs, NAT Gateway ID, IGW ID
        )
        
        # Verify specific resource properties
        resources = template.get("Resources", {})
        
        # Find VPC
        vpc_resource = None
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::EC2::VPC":
                vpc_resource = resource
                break
        
        assert vpc_resource is not None, "VPC resource not found"
        
        # Verify VPC properties
        properties = vpc_resource.get("Properties", {})
        assert properties.get("CidrBlock") == "10.0.0.0/16", "Incorrect CIDR block"
        assert properties.get("EnableDnsHostnames") == True, "DNS hostnames should be enabled"
        assert properties.get("EnableDnsSupport") == True, "DNS support should be enabled"
    
    def test_vpc_cross_stack_integration(self):
        """Test VPC module in cross-stack SSM integration"""
        producer_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24}
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
                        "public_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/public-subnet-ids",
                        "private_subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/private-subnet-ids"
                    }
                }
            }
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
                        "subnet_ids": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/private-subnet-ids"
                    }
                }
            }
        }
        
        result = self.test_cross_stack_ssm_integration([producer_config], [consumer_config])
        
        assert result["passed"], f"Cross-stack integration test failed: {result['errors']}"
        assert len(result["cross_validation"]["unmatched_imports"]) == 0, "Unmatched imports found"
        assert len(result["cross_validation"]["imports_found"]) > 0, "No imports found"
        assert len(result["cross_validation"]["exports_found"]) > 0, "No exports found"
    
    def test_vpc_with_s3_endpoint(self):
        """Test VPC with S3 gateway endpoint"""
        test_config = {
            "name": "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-s3",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "enable_s3_endpoint": True,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24}
                },
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(VpcStack, test_config)
        
        assert result["passed"], f"VPC with S3 endpoint test failed: {result['errors']}"
        
        # Verify S3 endpoint is created
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have S3 gateway endpoint
        endpoint_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::VPCEndpoint"]
        s3_endpoints = [r for r in endpoint_resources if "s3" in r.get("Properties", {}).get("ServiceName", "").lower()]
        assert len(s3_endpoints) >= 1, f"Expected at least 1 S3 endpoint, got {len(s3_endpoints)}"
    
    def test_vpc_configuration_validation_comprehensive(self):
        """Test comprehensive VPC configuration validation"""
        valid_config = {
            "name": "test-vpc",
            "module": "vpc_library_module",
            "vpc": {
                "name": "test-vpc-valid",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "enable_dns_hostnames": True,
                "enable_dns_support": True,
                "subnets": {
                    "public": {"enabled": True, "cidr_mask": 24},
                    "private": {"enabled": True, "cidr_mask": 24},
                    "isolated": {"enabled": False, "cidr_mask": 24}
                },
                "nat_gateways": {"count": 1},
                "ssm": {
                    "exports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        validator = self.validator
        result = validator.validate_complete_configuration(valid_config)
        
        assert result.valid, f"Valid configuration should pass validation: {result.errors}"
        assert len(result.errors) == 0, f"Should have no validation errors: {result.errors}"


if __name__ == "__main__":
    pytest.main([__file__])
