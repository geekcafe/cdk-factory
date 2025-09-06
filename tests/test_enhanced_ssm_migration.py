#!/usr/bin/env python3
"""
Test script to verify the enhanced SSM parameter pattern migration.
Tests both the new enhanced functionality and backward compatibility.
"""

import os
import sys
import json
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_enhanced_base_config():
    """Test the EnhancedBaseConfig functionality"""
    print("Testing EnhancedBaseConfig...")
    
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    # Test basic configuration
    config = {
        "name": "test-vpc",
        "ssm": {
            "enabled": True,
            "organization": "test-org",
            "environment": "dev",
            "auto_export": True,
            "auto_import": True
        }
    }
    
    enhanced_config = EnhancedBaseConfig(config, resource_type="vpc", resource_name="test-vpc")
    
    # Test properties
    assert enhanced_config.ssm_enabled == True
    assert enhanced_config.ssm_organization == "test-org"
    assert enhanced_config.ssm_environment == "dev"
    assert enhanced_config.ssm_auto_export == True
    assert enhanced_config.ssm_auto_import == True
    
    # Test auto-discovery
    export_defs = enhanced_config.get_export_definitions()
    import_defs = enhanced_config.get_import_definitions()
    
    print(f"  ✓ Auto-discovered {len(export_defs)} export parameters")
    print(f"  ✓ Auto-discovered {len(import_defs)} import parameters")
    
    # Test parameter path generation
    vpc_id_path = enhanced_config.get_parameter_path("vpc_id")
    expected_path = "/test-org/dev/vpc/test-vpc/vpc_id"
    assert vpc_id_path == expected_path, f"Expected {expected_path}, got {vpc_id_path}"
    
    print("  ✓ EnhancedBaseConfig tests passed")

def test_vpc_config_migration():
    """Test that VpcConfig was migrated correctly"""
    print("Testing VpcConfig migration...")
    
    from cdk_factory.configurations.resources.vpc import VpcConfig
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    config = {
        "name": "test-vpc",
        "cidr": "10.0.0.0/16",
        "ssm": {
            "enabled": True,
            "organization": "test-org",
            "environment": "dev"
        }
    }
    
    vpc_config = VpcConfig(config)
    
    # Test that it inherits from EnhancedBaseConfig
    assert isinstance(vpc_config, EnhancedBaseConfig)
    
    # Test that existing properties still work
    assert vpc_config.name == "test-vpc"
    assert vpc_config.cidr == "10.0.0.0/16"
    
    # Test enhanced SSM functionality
    assert vpc_config.ssm_enabled == True
    assert vpc_config.resource_type == "vpc"
    assert vpc_config.resource_name == "test-vpc"
    
    print("  ✓ VpcConfig migration tests passed")

def test_ecr_config_migration():
    """Test that ECRConfig was migrated correctly"""
    print("Testing ECRConfig migration...")
    
    from cdk_factory.configurations.resources.ecr import ECRConfig
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    config = {
        "name": "test-repo",
        "ssm": {
            "enabled": True,
            "organization": "test-org",
            "environment": "dev"
        }
    }
    
    ecr_config = ECRConfig(config)
    
    # Test that it inherits from EnhancedBaseConfig
    assert isinstance(ecr_config, EnhancedBaseConfig)
    
    # Test enhanced SSM functionality
    assert ecr_config.ssm_enabled == True
    assert ecr_config.resource_type == "ecr"
    assert ecr_config.resource_name == "test-repo"
    
    print("  ✓ ECRConfig migration tests passed")

def test_backward_compatibility():
    """Test that existing configurations still work"""
    print("Testing backward compatibility...")
    
    from cdk_factory.configurations.resources.vpc import VpcConfig
    
    # Test old-style configuration without enhanced SSM
    old_config = {
        "name": "legacy-vpc",
        "cidr": "10.0.0.0/16",
        "ssm_parameters": {
            "vpc_id_path": "/legacy/vpc/id",
            "vpc_cidr_path": "/legacy/vpc/cidr"
        }
    }
    
    vpc_config = VpcConfig(old_config)
    
    # Test that legacy properties still work
    assert vpc_config.name == "legacy-vpc"
    assert vpc_config.cidr == "10.0.0.0/16"
    assert vpc_config.ssm_parameters["vpc_id_path"] == "/legacy/vpc/id"
    
    # Test that enhanced functionality is available but not required
    assert hasattr(vpc_config, 'ssm_enabled')
    assert hasattr(vpc_config, 'get_export_definitions')
    
    print("  ✓ Backward compatibility tests passed")

def test_enhanced_ssm_mixin():
    """Test the EnhancedSsmParameterMixin functionality"""
    print("Testing EnhancedSsmParameterMixin...")
    
    from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    # Create a mock scope for testing
    class MockScope:
        def __init__(self):
            self.constructs = {}
    
    # Create test configuration
    config = {
        "name": "test-resource",
        "ssm": {
            "enabled": True,
            "organization": "test-org",
            "environment": "dev",
            "auto_export": True,
            "exports": {
                "resource_id_path": "auto",
                "custom_value_path": "/custom/path"
            }
        }
    }
    
    enhanced_config = EnhancedBaseConfig(config, resource_type="test", resource_name="test-resource")
    
    # Create mixin instance
    mixin = EnhancedSsmParameterMixin()
    mock_scope = MockScope()
    
    # Test setup
    mixin.setup_enhanced_ssm_integration(mock_scope, enhanced_config)
    assert hasattr(mixin, 'enhanced_ssm_config')
    assert mixin.enhanced_ssm_config == enhanced_config
    
    print("  ✓ EnhancedSsmParameterMixin tests passed")

def test_environment_variable_support():
    """Test environment variable support in SSM patterns"""
    print("Testing environment variable support...")
    
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    # Set environment variable
    os.environ["TEST_ENV"] = "production"
    
    config = {
        "name": "test-vpc",
        "ssm": {
            "enabled": True,
            "organization": "test-org",
            "environment": "${TEST_ENV}",
            "auto_export": True
        }
    }
    
    enhanced_config = EnhancedBaseConfig(config, resource_type="vpc", resource_name="test-vpc")
    
    # Test that environment variable is resolved
    assert enhanced_config.ssm_environment == "production"
    
    # Test parameter path generation with environment variable
    vpc_id_path = enhanced_config.get_parameter_path("vpc_id")
    expected_path = "/test-org/production/vpc/test-vpc/vpc_id"
    assert vpc_id_path == expected_path, f"Expected {expected_path}, got {vpc_id_path}"
    
    # Clean up
    del os.environ["TEST_ENV"]
    
    print("  ✓ Environment variable support tests passed")

def test_custom_patterns():
    """Test custom SSM parameter patterns"""
    print("Testing custom SSM parameter patterns...")
    
    from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
    
    config = {
        "name": "test-resource",
        "ssm": {
            "enabled": True,
            "organization": "acme-corp",
            "environment": "prod",
            "pattern": "/{organization}/{environment}/{resource_name}-{attribute}",
            "auto_export": True
        }
    }
    
    enhanced_config = EnhancedBaseConfig(config, resource_type="api_gateway", resource_name="cdk-factory-api-gw")
    
    # Test custom pattern
    api_id_path = enhanced_config.get_parameter_path("api_gateway_id")
    expected_path = "/acme-corp/prod/cdk-factory-api-gw-api_gateway_id"
    assert api_id_path == expected_path, f"Expected {expected_path}, got {api_id_path}"
    
    print("  ✓ Custom pattern tests passed")

def main():
    """Run all migration tests"""
    print("🧪 Testing Enhanced SSM Parameter Pattern Migration")
    print("=" * 60)
    
    try:
        test_enhanced_base_config()
        test_vpc_config_migration()
        test_ecr_config_migration()
        test_backward_compatibility()
        test_enhanced_ssm_mixin()
        test_environment_variable_support()
        test_custom_patterns()
        
        print("\n✅ All migration tests passed!")
        print("🎉 The enhanced SSM parameter pattern is working correctly")
        print("🔄 Backward compatibility is maintained")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
