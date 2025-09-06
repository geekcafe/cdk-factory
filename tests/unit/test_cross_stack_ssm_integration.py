"""
Integration test to validate cross-stack SSM parameter sharing
Tests that exports from one stack can be correctly imported by another stack
"""

import unittest
import os
from aws_cdk import App, Stack
from aws_cdk.assertions import Template
from constructs import Construct

from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin


class MockCognitoStack(Stack, EnhancedSsmParameterMixin):
    """Mock Cognito stack that exports user pool parameters"""
    
    def __init__(self, scope: Construct, construct_id: str, config: dict):
        super().__init__(scope, construct_id)
        
        # Initialize enhanced SSM config
        self.enhanced_ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="cognito",
            resource_name="user-pool"
        )
        
        # Mock resource values that would be exported
        self.resource_values = {
            "user_pool_id": "us-east-1_ABC123DEF",
            "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_ABC123DEF",
            "user_pool_name": "my-app-dev-user-pool"
        }
        
        # Auto-export resources
        if self.enhanced_ssm_config.auto_export:
            self.auto_export_resources(self.resource_values)


class MockApiGatewayStack(Stack, EnhancedSsmParameterMixin):
    """Mock API Gateway stack that imports user pool parameters"""
    
    def __init__(self, scope: Construct, construct_id: str, config: dict):
        super().__init__(scope, construct_id)
        
        # Initialize enhanced SSM config
        self.enhanced_ssm_config = EnhancedSsmConfig(
            config=config,
            resource_type="api-gateway",
            resource_name="my-api"
        )
        
        # Auto-import resources
        if self.enhanced_ssm_config.auto_import:
            imported_values = self.auto_import_resources()
            self.imported_user_pool_arn = imported_values.get("user_pool_arn")


class TestCrossStackSsmIntegration(unittest.TestCase):
    """Test cross-stack SSM parameter sharing integration"""

    def setUp(self):
        """Set up test environment"""
        # Set required environment variables
        os.environ["ENVIRONMENT"] = "dev"
        os.environ["AWS_ACCOUNT_NUMBER"] = "123456789012"
        
        self.app = App()

    def test_cognito_to_api_gateway_ssm_parameter_flow(self):
        """Test that Cognito exports can be imported by API Gateway using matching paths"""
        
        # Cognito stack configuration
        cognito_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev",
                "auto_export": True,
                "auto_import": False
            }
        }
        
        # API Gateway stack configuration with explicit import
        api_gateway_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev",
                "auto_export": True,
                "auto_import": True,
                "imports": {
                    "user_pool_arn": "auto"
                }
            }
        }

        # Create SSM configs directly (without full stack synthesis)
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
        cognito_user_pool_export = next((d for d in cognito_export_defs if d.attribute == "user_pool_arn"), None)
        
        # Get import definitions from API Gateway
        api_import_defs = api_gateway_ssm.get_import_definitions()
        user_pool_import = next((d for d in api_import_defs if d.attribute == "user_pool_arn"), None)
        
        self.assertIsNotNone(cognito_user_pool_export, "Cognito should export user_pool_arn")
        self.assertIsNotNone(user_pool_import, "API Gateway should have user_pool_arn import definition")
        
        # Verify the import path matches the export path
        expected_path = "/my-app/dev/cognito/user-pool/user-pool-arn"
        self.assertEqual(cognito_user_pool_export.path, expected_path, 
                        f"Cognito export path should be: {expected_path}")
        self.assertEqual(user_pool_import.path, expected_path, 
                        f"Import path should match export path: {expected_path}")
        
        # Verify paths match between export and import
        self.assertEqual(cognito_user_pool_export.path, user_pool_import.path,
                        "Export and import paths must match for cross-stack parameter sharing")

    def test_multiple_resource_type_consistency(self):
        """Test that multiple resource types can import from the same source consistently"""
        
        base_config = {
            "ssm": {
                "enabled": True,
                "organization": "test-org",
                "environment": "prod",
                "auto_export": True,
                "auto_import": True
            }
        }

        # Create SSM configs for different resource types
        cognito_ssm = EnhancedSsmConfig(
            config=base_config,
            resource_type="cognito",
            resource_name="user-pool"
        )
        
        # Use consistent resource name for cross-stack compatibility
        api_gateway_ssm = EnhancedSsmConfig(
            config=base_config,
            resource_type="api-gateway",
            resource_name="cdk-factory-api-gw"
        )
        
        lambda_ssm = EnhancedSsmConfig(
            config=base_config,
            resource_type="lambda",
            resource_name="auth-function"
        )

        # Get export from Cognito
        cognito_exports = cognito_ssm.get_export_definitions()
        cognito_user_pool_export = next((d for d in cognito_exports if d.attribute == "user_pool_arn"), None)
        
        # Get imports from API Gateway and Lambda
        api_imports = api_gateway_ssm.get_import_definitions()
        lambda_imports = lambda_ssm.get_import_definitions()
        
        api_user_pool_import = next((d for d in api_imports if d.attribute == "user_pool_arn"), None)
        lambda_user_pool_import = next((d for d in lambda_imports if d.attribute == "user_pool_arn"), None)

        # All should exist
        self.assertIsNotNone(cognito_user_pool_export, "Cognito should export user_pool_arn")
        self.assertIsNotNone(api_user_pool_import, "API Gateway should import user_pool_arn")
        self.assertIsNotNone(lambda_user_pool_import, "Lambda should import user_pool_arn")

        # All import paths should match the export path
        expected_path = "/test-org/prod/cognito/user-pool/user-pool-arn"
        
        self.assertEqual(cognito_user_pool_export.path, expected_path)
        self.assertEqual(api_user_pool_import.path, expected_path)
        self.assertEqual(lambda_user_pool_import.path, expected_path)

    def test_explicit_vs_auto_import_consistency(self):
        """Test that explicit imports and auto imports generate the same paths"""
        
        base_config = {
            "ssm": {
                "enabled": True,
                "organization": "my-app",
                "environment": "dev"
            }
        }

        # Config with explicit import using "auto"
        explicit_config = {**base_config}
        explicit_config["ssm"]["imports"] = {"user_pool_arn": "auto"}
        explicit_config["ssm"]["auto_import"] = False
        
        # Config with auto import
        auto_config = {**base_config}
        auto_config["ssm"]["auto_import"] = True

        # Create SSM configs
        explicit_ssm = EnhancedSsmConfig(
            config=explicit_config,
            resource_type="api-gateway",
            resource_name="my-api"
        )
        
        auto_ssm = EnhancedSsmConfig(
            config=auto_config,
            resource_type="api-gateway",
            resource_name="my-api"
        )

        # Get import definitions
        explicit_imports = explicit_ssm.get_import_definitions()
        auto_imports = auto_ssm.get_import_definitions()
        
        explicit_user_pool = next((d for d in explicit_imports if d.attribute == "user_pool_arn"), None)
        auto_user_pool = next((d for d in auto_imports if d.attribute == "user_pool_arn"), None)

        # Both should exist and have the same path
        self.assertIsNotNone(explicit_user_pool, "Explicit import should exist")
        self.assertIsNotNone(auto_user_pool, "Auto import should exist")
        
        self.assertEqual(explicit_user_pool.path, auto_user_pool.path,
                        "Explicit and auto import paths should match")
        
        # Path should use cognito as source
        expected_path = "/my-app/dev/cognito/user-pool/user-pool-arn"
        self.assertEqual(explicit_user_pool.path, expected_path)

    def tearDown(self):
        """Clean up environment variables"""
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
        if "AWS_ACCOUNT_NUMBER" in os.environ:
            del os.environ["AWS_ACCOUNT_NUMBER"]


if __name__ == "__main__":
    unittest.main()
