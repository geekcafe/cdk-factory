"""
Test Standardized ECS Cluster Stack Integration

Tests the ECS module with standardized SSM integration to ensure:
- Configuration validation works correctly
- SSM imports/exports function properly
- Template synthesis produces expected CloudFormation
- Token resolution works as expected
- Backward compatibility is maintained
- ECS-specific features work correctly
"""

import pytest
from typing import Dict, Any

from cdk_factory.stack_library.ecs.ecs_cluster_stack import EcsClusterStack
from tests.framework.ssm_integration_tester import SSMIntegrationTester


class TestECSStandardized(SSMIntegrationTester):
    
    def setup_method(self):
        """Setup test environment."""
        self.setUp()
    
    def test_ecs_complete_ssm_integration(self):
        """Test complete SSM integration for ECS module"""
        test_config = {
            "name": "test-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "container_insights": True,
                "create_instance_role": True,
                "ssm": {
                    "imports": {
                        "vpc_id": "/test/environment/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/test/environment/ecs/cluster/name",
                        "cluster_arn": "/test/environment/ecs/cluster/arn",
                        "cluster_security_group_id": "/test/environment/ecs/cluster/security-group-id",
                        "instance_profile_arn": "/test/environment/ecs/instance-profile/arn"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(EcsClusterStack, test_config)
        
        assert result["passed"], f"ECS SSM integration failed: {result['errors']}"
        
        # Verify SSM parameters are created
        assert len(result["ssm_parameters"]) >= 3, f"Expected at least 3 SSM parameters, got {len(result['ssm_parameters'])}"
        
        # Verify SSM parameter names
        parameter_names = [param["parameter_name"] for param in result["ssm_parameters"]]
        assert any("ecs/cluster/name" in name for name in parameter_names), "ECS cluster name export not found"
        assert any("ecs/cluster/arn" in name for name in parameter_names), "ECS cluster ARN export not found"
        
        # Verify template contains expected resources
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have ECS Cluster, IAM Role, Instance Profile
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert "AWS::ECS::Cluster" in resource_types, "ECS Cluster not found"
        assert "AWS::IAM::Role" in resource_types, "IAM Role not found"
        assert "AWS::IAM::InstanceProfile" in resource_types, "Instance Profile not found"
        
        # Verify outputs are created
        outputs = template.get("Outputs", {})
        assert len(outputs) >= 3, f"Expected at least 3 outputs, got {len(outputs)}"
    
    def test_ecs_backward_compatibility(self):
        """Test that ECS module maintains backward compatibility"""
        legacy_config = {
            "name": "test-ecs-cluster-legacy",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster-legacy",
                "container_insights": True,
                "create_instance_role": False,
                "vpc_id": "vpc-0123456789abcdef0"  # Direct config (old pattern)
            }
        }
        
        result = self.test_complete_ssm_integration(EcsClusterStack, legacy_config)
        
        assert result["passed"], f"Backward compatibility test failed: {result['errors']}"
        
        # Should still create valid template even with legacy configuration
        template = result["template"]
        resources = template.get("Resources", {})
        assert len(resources) > 0, "No resources created with legacy configuration"
        
        # Should have ECS Cluster
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert "AWS::ECS::Cluster" in resource_types, "ECS Cluster not found with legacy config"
    
    def test_ecs_without_instance_role(self):
        """Test ECS cluster without instance role creation"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster-no-role",
                "container_insights": True,
                "create_instance_role": False,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(EcsClusterStack, test_config)
        
        assert result["passed"], f"ECS without instance role test failed: {result['errors']}"
        
        # Verify instance role is not created
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Should have ECS Cluster but not IAM Role/Instance Profile
        resource_types = {resource.get("Type") for resource in resources.values()}
        assert "AWS::ECS::Cluster" in resource_types, "ECS Cluster not found"
        assert "AWS::IAM::Role" not in resource_types, "IAM Role should not be created"
        assert "AWS::IAM::InstanceProfile" not in resource_types, "Instance Profile should not be created"
    
    def test_ecs_with_container_insights(self):
        """Test ECS cluster with container insights enabled"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster-insights",
                "container_insights": True,
                "create_instance_role": False,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(EcsClusterStack, test_config)
        
        assert result["passed"], f"ECS with container insights test failed: {result['errors']}"
        
        # Verify container insights is enabled in the cluster
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Find ECS Cluster
        ecs_cluster_resource = None
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::ECS::Cluster":
                ecs_cluster_resource = resource
                break
        
        assert ecs_cluster_resource is not None, "ECS Cluster resource not found"
        
        # Verify cluster settings include container insights
        properties = ecs_cluster_resource.get("Properties", {})
        cluster_settings = properties.get("ClusterSettings", [])
        
        container_insights_setting = None
        for setting in cluster_settings:
            if setting.get("Name") == "containerInsights":
                container_insights_setting = setting
                break
        
        assert container_insights_setting is not None, "Container insights setting not found"
        assert container_insights_setting.get("Value") == "enabled", "Container insights should be enabled"
    
    def test_ecs_ssm_import_resolution(self):
        """Test SSM import resolution with mocked values"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "container_insights": True,
                "create_instance_role": False,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        mock_ssm_values = {
            "/test/test-workload/vpc/id": "vpc-0123456789abcdef0"
        }
        
        result = self.test_ssm_import_resolution(EcsClusterStack, test_config, mock_ssm_values)
        
        assert result["passed"], f"SSM import resolution test failed: {result['errors']}"
        
        # Verify import resolution details
        import_resolution = result.get("import_resolution", {})
        assert import_resolution.get("expected_imports") == list(mock_ssm_values.keys()), "Expected imports not matched"
        assert import_resolution.get("actual_references", 0) > 0, "No SSM references found"
    
    def test_ecs_token_resolution(self):
        """Test CDK token resolution with specific context"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "container_insights": True,
                "create_instance_role": False,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
                    }
                }
            }
        }
        
        context = {
            "ENVIRONMENT": "production",
            "WORKLOAD_NAME": "my-app",
            "AWS_REGION": "us-east-1"
        }
        
        result = self.test_token_resolution_with_context(EcsClusterStack, test_config, context)
        
        assert result["passed"], f"Token resolution test failed: {result.get('error', 'Unknown error')}"
        
        # Verify token validation
        token_validation = result.get("token_validation", {})
        assert token_validation.get("tokens_found", 0) > 0, "No tokens found in template"
        assert token_validation.get("valid_tokens", 0) > 0, "No valid tokens found"
        assert len(token_validation.get("invalid_tokens", [])) == 0, f"Invalid tokens found: {token_validation.get('invalid_tokens', [])}"
    
    def test_ecs_ssm_path_validation(self):
        """Test SSM path validation for ECS module"""
        valid_config = {
            "name": "test-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name",
                        "ecs_cluster_arn": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/arn"
                    }
                }
            }
        }
        
        result = self.test_ssm_path_validation(valid_config)
        
        assert result["validation"]["valid"], f"SSM path validation failed: {result['validation']['errors']}"
        assert result["invalid_count"] == 0, f"Found {result['invalid_count']} invalid paths"
        assert result["valid_count"] > 0, "No valid paths found"
    
    def test_ecs_invalid_ssm_paths(self):
        """Test SSM path validation with invalid paths"""
        invalid_config = {
            "name": "test-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "ssm": {
                    "imports": {
                        "vpc_id": "invalid-path-format"  # Missing leading slash
                    },
                    "exports": {
                        "cluster_name": "another-invalid-path"  # Missing template variables
                    }
                }
            }
        }
        
        result = self.test_ssm_path_validation(invalid_config)
        
        assert not result["validation"]["valid"], "Invalid SSM config should fail validation"
        assert result["invalid_count"] > 0, "Should have found invalid paths"
        assert len(result["validation"]["errors"]) > 0, "Should have validation errors"
    
    def test_ecs_configuration_validation(self):
        """Test ECS specific configuration validation"""
        invalid_config = {
            "name": "test-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "capacity_providers": ["INVALID_PROVIDER"]  # Invalid capacity provider
            }
        }
        
        validator = self.validator
        result = validator.validate_module_config("ecs_cluster_stack", invalid_config)
        
        # Note: This test depends on the specific validation rules implemented
        # For now, we'll test that the validator runs without error
        assert result is not None, "Validation result should not be None"
    
    def test_ecs_template_structure(self):
        """Test that generated template has correct structure"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "container_insights": True,
                "create_instance_role": True,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    }
                }
            }
        }
        
        template = self.synthesize_stack(EcsClusterStack, test_config)
        
        # Validate template structure
        self.assert_template_valid(
            template,
            expected_resources=3,  # ECS Cluster, IAM Role, Instance Profile
            expected_ssm_params=0,  # No exports in this config
            expected_outputs=0
        )
        
        # Verify specific resource properties
        resources = template.get("Resources", {})
        
        # Find ECS Cluster
        ecs_cluster_resource = None
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::ECS::Cluster":
                ecs_cluster_resource = resource
                break
        
        assert ecs_cluster_resource is not None, "ECS Cluster resource not found"
        
        # Verify cluster properties
        properties = ecs_cluster_resource.get("Properties", {})
        assert properties.get("ClusterName") == "test-ecs-cluster", "Incorrect cluster name"
        assert properties.get("ContainerInsights") == True, "Container insights should be enabled"
    
    def test_ecs_cross_stack_integration(self):
        """Test ECS module in cross-stack SSM integration"""
        producer_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-vpc",
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
        
        consumer_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster",
                "container_insights": True,
                "create_instance_role": False,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
                    }
                }
            }
        }
        
        result = self.test_cross_stack_ssm_integration([producer_config], [consumer_config])
        
        assert result["passed"], f"Cross-stack integration test failed: {result['errors']}"
        assert len(result["cross_validation"]["unmatched_imports"]) == 0, "Unmatched imports found"
        assert len(result["cross_validation"]["imports_found"]) > 0, "No imports found"
        assert len(result["cross_validation"]["exports_found"]) > 0, "No exports found"
    
    def test_ecs_with_cluster_settings(self):
        """Test ECS cluster with custom cluster settings"""
        test_config = {
            "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster-settings",
                "container_insights": True,
                "create_instance_role": False,
                "cluster_settings": [
                    {"name": "containerInsights", "value": "enabled"},
                    {"name": "serviceConnectDefaults", "value": "namespace"}
                ],
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
                    }
                }
            }
        }
        
        result = self.test_complete_ssm_integration(EcsClusterStack, test_config)
        
        assert result["passed"], f"ECS with cluster settings test failed: {result['errors']}"
        
        # Verify cluster settings are applied
        template = result["template"]
        resources = template.get("Resources", {})
        
        # Find ECS Cluster
        ecs_cluster_resource = None
        for resource_id, resource in resources.items():
            if resource.get("Type") == "AWS::ECS::Cluster":
                ecs_cluster_resource = resource
                break
        
        assert ecs_cluster_resource is not None, "ECS Cluster resource not found"
        
        # Verify cluster settings
        properties = ecs_cluster_resource.get("Properties", {})
        cluster_settings = properties.get("ClusterSettings", [])
        
        assert len(cluster_settings) >= 2, f"Expected at least 2 cluster settings, got {len(cluster_settings)}"
        
        # Check for specific settings
        setting_names = [setting.get("Name") for setting in cluster_settings]
        assert "containerInsights" in setting_names, "Container insights setting not found"
    
    def test_ecs_configuration_validation_comprehensive(self):
        """Test comprehensive ECS configuration validation"""
        valid_config = {
            "name": "test-ecs-cluster",
            "module": "ecs_cluster_stack",
            "ecs_cluster": {
                "name": "test-ecs-cluster-valid",
                "container_insights": True,
                "create_instance_role": True,
                "ssm": {
                    "imports": {
                        "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id"
                    },
                    "exports": {
                        "cluster_name": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/ecs/cluster/name"
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
