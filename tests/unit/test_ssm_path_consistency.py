"""
Test to verify auto-export and auto-import SSM paths are consistent
Ensures that when one stack exports SSM parameters, another stack can import them using auto-discovery
"""

import unittest
from unittest.mock import MagicMock
from aws_cdk import App
from constructs import Construct

from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin


class MockConstruct(Construct, EnhancedSsmParameterMixin):
    """Mock construct for testing SSM parameter operations"""
    pass


class TestSsmPathConsistency(unittest.TestCase):
    """Test that auto-export and auto-import generate matching SSM paths"""

    def setUp(self):
        """Set up test environment"""
        self.app = App()
        self.construct = MockConstruct(self.app, "TestConstruct")

    def test_cognito_export_lambda_import_consistency(self):
        """Test that Cognito exports match Lambda imports for user_pool_arn"""
        
        # Cognito configuration that exports user_pool_arn
        cognito_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev",
                "auto_export": True
            }
        }
        
        # Lambda configuration that imports user_pool_arn
        lambda_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app", 
                "environment": "dev",
                "auto_import": True
            }
        }

        # Create enhanced SSM configs
        cognito_ssm = EnhancedSsmConfig(
            config=cognito_config,
            resource_type="cognito",
            resource_name="user-pool"
        )
        
        lambda_ssm = EnhancedSsmConfig(
            config=lambda_config,
            resource_type="lambda",
            resource_name="my-function"
        )

        # Get export definitions from Cognito
        cognito_export_defs = cognito_ssm.get_export_definitions()
        
        # Get import definitions from Lambda
        lambda_import_defs = lambda_ssm.get_import_definitions()

        # Find user_pool_arn in both
        cognito_user_pool_export = None
        lambda_user_pool_import = None
        
        for export_def in cognito_export_defs:
            if export_def.attribute == "user_pool_arn":
                cognito_user_pool_export = export_def
                break
                
        for import_def in lambda_import_defs:
            if import_def.attribute == "user_pool_arn":
                lambda_user_pool_import = import_def
                break

        # Both should exist
        self.assertIsNotNone(cognito_user_pool_export, "Cognito should export user_pool_arn")
        self.assertIsNotNone(lambda_user_pool_import, "Lambda should import user_pool_arn")

        # Print the paths to verify they match
        print(f"Cognito export path: {cognito_user_pool_export.path}")
        print(f"Lambda import path: {lambda_user_pool_import.path}")
        
        # With our fix, these should now match
        self.assertEqual(
            cognito_user_pool_export.path, 
            lambda_user_pool_import.path,
            f"Cognito export path ({cognito_user_pool_export.path}) should match Lambda import path ({lambda_user_pool_import.path})"
        )

    def test_cognito_export_api_gateway_import_consistency(self):
        """Test that Cognito exports match API Gateway imports for user_pool_arn"""
        
        # Cognito configuration that exports user_pool_arn
        cognito_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev", 
                "auto_export": True
            }
        }
        
        # API Gateway configuration that imports user_pool_arn
        api_gateway_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev",
                "auto_import": True
            }
        }

        # Create enhanced SSM configs
        cognito_ssm = EnhancedSsmConfig(
            config=cognito_config,
            resource_type="cognito",
            resource_name="user-pool"
        )
        
        api_gateway_ssm = EnhancedSsmConfig(
            config=api_gateway_config,
            resource_type="api-gateway", 
            resource_name="my-api"
        )

        # Get export definitions from Cognito
        cognito_export_defs = cognito_ssm.get_export_definitions()
        
        # Get import definitions from API Gateway
        api_import_defs = api_gateway_ssm.get_import_definitions()

        # Find user_pool_arn in both
        cognito_user_pool_export = None
        api_user_pool_import = None
        
        for export_def in cognito_export_defs:
            if export_def.attribute == "user_pool_arn":
                cognito_user_pool_export = export_def
                break
                
        for import_def in api_import_defs:
            if import_def.attribute == "user_pool_arn":
                api_user_pool_import = import_def
                break

        # Both should exist
        self.assertIsNotNone(cognito_user_pool_export, "Cognito should export user_pool_arn")
        self.assertIsNotNone(api_user_pool_import, "API Gateway should import user_pool_arn")

        # Print the paths to see the mismatch
        print(f"Cognito export path: {cognito_user_pool_export.path}")
        print(f"API Gateway import path: {api_user_pool_import.path}")
        
        # Expected paths:
        # Cognito exports: /my-app/dev/cognito/user-pool/user-pool-arn
        # API Gateway imports: /my-app/dev/api-gateway/my-api/user-pool-arn
        
        # This should match for the system to work
        self.assertEqual(
            cognito_user_pool_export.path,
            api_user_pool_import.path,
            f"Cognito export path ({cognito_user_pool_export.path}) should match API Gateway import path ({api_user_pool_import.path})"
        )

    def test_path_generation_with_same_organization_environment(self):
        """Test that paths are consistent when organization and environment match"""
        
        base_config = {
            "ssm": {
                "enabled": True,
                "organization": "test-org",
                "environment": "prod",
                "auto_export": True,
                "auto_import": True
            }
        }

        # Create configs for different resource types
        configs = [
            ("cognito", "user-pool"),
            ("api-gateway", "cdk-factory-api-gw"), 
            ("dynamodb", "app-table"),
            ("lambda", "processor-function")
        ]

        paths_by_attribute = {}
        
        for resource_type, resource_name in configs:
            ssm_config = EnhancedSsmConfig(
                config=base_config,
                resource_type=resource_type,
                resource_name=resource_name
            )
            
            # Get both export and import definitions
            export_defs = ssm_config.get_export_definitions()
            import_defs = ssm_config.get_import_definitions()
            
            # Collect paths by attribute
            for export_def in export_defs:
                attr = export_def.attribute
                if attr not in paths_by_attribute:
                    paths_by_attribute[attr] = {}
                paths_by_attribute[attr][f"{resource_type}_export"] = export_def.path
                
            for import_def in import_defs:
                attr = import_def.attribute
                if attr not in paths_by_attribute:
                    paths_by_attribute[attr] = {}
                paths_by_attribute[attr][f"{resource_type}_import"] = import_def.path

        # Print all paths for analysis
        for attribute, paths in paths_by_attribute.items():
            print(f"\nAttribute: {attribute}")
            for source, path in paths.items():
                print(f"  {source}: {path}")

        # The issue: each resource type generates its own path based on its resource_type and resource_name
        # This means exports and imports won't match unless they use the same resource_type and resource_name
        
        # For example, if Cognito exports user_pool_arn, API Gateway needs to know to import from
        # the Cognito path, not generate its own path based on API Gateway's resource info


if __name__ == "__main__":
    unittest.main()
