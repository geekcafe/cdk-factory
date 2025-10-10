"""
Simple test to verify the exact SSM path that gets generated for Cognito auto-import.
"""

import pytest
from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig


def test_cognito_user_pool_arn_auto_import_path():
    """
    Test the exact SSM path generated when API Gateway uses "user_pool_arn": "auto".
    This should match what the infrastructure stack exports.
    
    This also tests that metadata fields (workload, environment) are NOT treated as imports.
    """
    # Configuration that mimics geek-cafe-lambdas API Gateway
    # INCLUDING the metadata fields that were causing the bug
    config_dict = {
        "ssm": {
            "enabled": True,
            "workload": "geekcafe",
            "environment": "prod",
            "auto_export": True,
            "auto_import": False,
            "imports": {
                "workload": "geekcafe",      # Metadata field - should be SKIPPED
                "environment": "prod",        # Metadata field - should be SKIPPED  
                "user_pool_arn": "auto"      # Actual import - should be processed
            }
        }
    }
    
    config = EnhancedSsmConfig(
        config=config_dict,
        resource_type="api_gateway",
        resource_name="geekcafe-prod-api"
    )
    
    # Get the import definitions
    import_defs = config.get_import_definitions()
    
    print(f"\n" + "="*80)
    print(f"🔍 Testing Metadata Field Filtering")
    print(f"="*80)
    print(f"\n📝 Import Config:")
    print(f"   {config.ssm_imports}")
    print(f"\n📊 Import Definitions Created: {len(import_defs)}")
    for import_def in import_defs:
        print(f"   - {import_def.attribute}: {import_def.path}")
    
    # CRITICAL: Should only create 1 import (user_pool_arn), NOT 3 (workload, environment, user_pool_arn)
    assert len(import_defs) == 1, f"Expected 1 import, got {len(import_defs)}. Metadata fields should be filtered out!"
    
    # Find the user_pool_arn import
    user_pool_arn_import = None
    for import_def in import_defs:
        if import_def.attribute == "user_pool_arn":
            user_pool_arn_import = import_def
            break
    
    assert user_pool_arn_import is not None, "user_pool_arn import not found"
    
    print(f"\n✅ Metadata fields correctly filtered!")
    print(f"   - 'workload' and 'environment' were NOT processed as imports")
    print(f"   - Only 'user_pool_arn' was processed")
    
    generated_path = user_pool_arn_import.path
    expected_path = "/geekcafe/prod/cognito/user-pool/user-pool-arn"
    
    print(f"\n" + "="*80)
    print(f"🔍 SSM Path Resolution Test")
    print(f"="*80)
    print(f"\n📝 Configuration:")
    print(f"   - Workload: geekcafe")
    print(f"   - Environment: prod")
    print(f"   - Resource Type: api_gateway")
    print(f"   - Import Config: {{'user_pool_arn': 'auto'}}")
    print(f"\n✅ Generated Path: {generated_path}")
    print(f"📋 Expected Path:  {expected_path}")
    print(f"\n🎯 Match: {generated_path == expected_path}")
    
    if generated_path == expected_path:
        print(f"\n✅ SUCCESS: Auto-import path matches infrastructure export!")
        print(f"\n💡 The path resolution logic is CORRECT.")
        print(f"   The deployment error must be caused by something else:")
        print(f"   1. SSM parameter doesn't exist yet (infrastructure not deployed)")
        print(f"   2. IAM permissions issue (CloudFormation can't read SSM)")
        print(f"   3. CloudFormation template parameter resolution issue")
    else:
        print(f"\n❌ MISMATCH: Auto-import path doesn't match!")
        print(f"\n💡 This is the bug - fix the path generation logic")
    
    print(f"="*80 + "\n")
    
    assert generated_path == expected_path, f"Path mismatch: got {generated_path}, expected {expected_path}"


def test_infrastructure_cognito_export_path():
    """
    Test what path the infrastructure Cognito stack exports to.
    """
    # Configuration that mimics geek-cafe-infrastructure Cognito stack
    config_dict = {
        "ssm": {
            "enabled": True,
            "workload": "geekcafe",
            "environment": "prod",
            "auto_export": True,
            "auto_import": False
        }
    }
    
    config = EnhancedSsmConfig(
        config=config_dict,
        resource_type="cognito",
        resource_name="user-pool"
    )
    
    # Get the export definitions
    export_defs = config.get_export_definitions()
    
    # Find the user_pool_arn export
    user_pool_arn_export = None
    for export_def in export_defs:
        if export_def.attribute == "user_pool_arn":
            user_pool_arn_export = export_def
            break
    
    assert user_pool_arn_export is not None, "user_pool_arn export not found"
    
    export_path = user_pool_arn_export.path
    
    print(f"\n" + "="*80)
    print(f"🔍 Infrastructure Export Path Test")
    print(f"="*80)
    print(f"\n📝 Configuration:")
    print(f"   - Workload: geekcafe")
    print(f"   - Environment: prod")
    print(f"   - Resource Type: cognito")
    print(f"   - Resource Name: user-pool")
    print(f"\n✅ Export Path: {export_path}")
    print(f"="*80 + "\n")
    
    # This should match what we see in AWS
    expected = "/geekcafe/prod/cognito/user-pool/user-pool-arn"
    assert export_path == expected, f"Export path mismatch: got {export_path}, expected {expected}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
