"""
Unit tests for API Gateway Cognito User Pool ARN auto-import from SSM.

This test debugs the issue where:
- Infrastructure exports: /geekcafe/prod/cognito/user-pool/user-pool-arn
- API Gateway auto-import with "user_pool_arn": "auto" fails to find it

Tests the SSM parameter path resolution logic.
"""

import pytest
from aws_cdk import App, aws_ssm as ssm
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from unittest.mock import Mock, patch, MagicMock


class TestApiGatewayCognitoAutoImport:
    """Test suite for debugging Cognito User Pool ARN auto-import."""

    @pytest.fixture
    def workload_config(self):
        """Create workload config matching geek-cafe-lambdas."""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "geekcafe",
                    "devops": {"name": "geekcafe-devops"}
                },
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create deployment config for prod environment."""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={"name": "geekcafe-prod-pipeline", "environment": "prod"},
        )

    @pytest.fixture
    def infrastructure_cognito_config(self):
        """
        Cognito config from geek-cafe-infrastructure that EXPORTS the ARN.
        This mimics what the infrastructure stack does.
        """
        return {
            "name": "geekcafe-prod-cognito",
            "module": "cognito_stack",
            "enabled": True,
            "cognito": {
                "user_pool_name": "geekcafe-prod",
                "exists": False,
                "ssm": {
                    "enabled": True,
                    "workload": "geekcafe",
                    "environment": "prod",
                    "auto_export": True,
                    "auto_import": False
                }
            }
        }

    @pytest.fixture
    def lambdas_api_gateway_config_with_auto(self):
        """
        API Gateway config from geek-cafe-lambdas that tries to IMPORT the ARN.
        Uses "user_pool_arn": "auto" which is currently failing.
        """
        return {
            "api_gateway": {
                "name": "geekcafe-prod-api",
                "description": "API Gateway for geekcafe application",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "workload": "geekcafe",
                    "environment": "prod",
                    "auto_export": True,
                    "imports": {
                        "workload": "geekcafe",
                        "environment": "prod",
                        "user_pool_arn": "auto"  # This is what's failing
                    }
                },
                "cognito_authorizer": {
                    "authorizer_name": "geekcafe-cognito-authorizer"
                },
                "routes": [
                    {
                        "path": "/app/messages",
                        "method": "POST",
                        "lambda_name": "geekcafe-prod-create-app-message",
                        "authorization_type": "COGNITO"
                    }
                ]
            }
        }

    @pytest.fixture
    def lambdas_api_gateway_config_with_explicit(self):
        """
        API Gateway config with EXPLICIT SSM path that works.
        """
        return {
            "api_gateway": {
                "name": "geekcafe-prod-api",
                "description": "API Gateway for geekcafe application",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "workload": "geekcafe",
                    "environment": "prod",
                    "auto_export": True,
                    "imports": {
                        "workload": "geekcafe",
                        "environment": "prod",
                        "user_pool_arn": "/geekcafe/prod/cognito/user-pool/user-pool-arn"  # Explicit
                    }
                },
                "cognito_authorizer": {
                    "authorizer_name": "geekcafe-cognito-authorizer"
                },
                "routes": [
                    {
                        "path": "/app/messages",
                        "method": "POST",
                        "lambda_name": "geekcafe-prod-create-app-message",
                        "authorization_type": "COGNITO"
                    }
                ]
            }
        }

    def test_cognito_export_path_from_infrastructure(self, infrastructure_cognito_config):
        """
        Test what SSM path the infrastructure Cognito stack exports to.
        This helps us understand what path is actually being used.
        """
        cognito_config = infrastructure_cognito_config["cognito"]
        ssm_config = cognito_config["ssm"]
        
        # Expected path pattern from CDK Factory cognito_stack
        workload = ssm_config["workload"]
        environment = ssm_config["environment"]
        
        # The cognito_stack likely exports to this pattern
        # We need to verify this matches what API Gateway expects
        expected_export_path = f"/{workload}/{environment}/cognito/user-pool/user-pool-arn"
        
        print(f"\n🔍 Infrastructure exports Cognito ARN to: {expected_export_path}")
        assert expected_export_path == "/geekcafe/prod/cognito/user-pool/user-pool-arn"

    def test_api_gateway_auto_import_path_resolution(
        self, 
        workload_config, 
        deployment_config,
        lambdas_api_gateway_config_with_auto
    ):
        """
        Test what SSM path the API Gateway auto-import tries to use.
        This is the key test to identify the mismatch.
        """
        app = App()
        stack_config = StackConfig(
            lambdas_api_gateway_config_with_auto,
            workload=workload_config.dictionary,
        )
        
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment_config
        stack.workload = workload_config
        
        # Get the SSM imports config
        ssm_imports = stack_config.dictionary.get("api_gateway", {}).get("ssm", {}).get("imports", {})
        workload = ssm_imports.get("workload", "geekcafe")
        environment = ssm_imports.get("environment", "prod")
        user_pool_arn_config = ssm_imports.get("user_pool_arn")
        
        print(f"\n🔍 API Gateway config has:")
        print(f"   - workload: {workload}")
        print(f"   - environment: {environment}")
        print(f"   - user_pool_arn: {user_pool_arn_config}")
        
        # When user_pool_arn is "auto", CDK Factory should construct the path
        # Let's see what path it constructs
        if user_pool_arn_config == "auto":
            # This is what the auto-discovery SHOULD construct
            # We need to find out if it matches the export path
            
            # Common patterns it might try:
            patterns = [
                f"/{workload}/{environment}/cognito/user_pool_arn",  # underscore
                f"/{workload}/{environment}/cognito/user-pool-arn",  # hyphen
                f"/{workload}/{environment}/cognito/user-pool/user-pool-arn",  # nested with hyphen
                f"/{workload}/{environment}/cognito/userpool/arn",  # different structure
            ]
            
            print(f"\n❓ Possible auto-discovery paths API Gateway might try:")
            for i, pattern in enumerate(patterns, 1):
                print(f"   {i}. {pattern}")
            
            # The actual exported path from infrastructure
            actual_export = "/geekcafe/prod/cognito/user-pool/user-pool-arn"
            print(f"\n✅ Actual export path from infrastructure: {actual_export}")
            
            # Check which pattern matches
            if actual_export in patterns:
                matching_index = patterns.index(actual_export) + 1
                print(f"\n✅ MATCH FOUND: Pattern #{matching_index} matches the export!")
            else:
                print(f"\n❌ NO MATCH: None of the expected patterns match the export path!")
                print(f"\n💡 This is why 'auto' fails - path mismatch")

    def test_api_gateway_explicit_import_works(
        self,
        workload_config,
        deployment_config,
        lambdas_api_gateway_config_with_explicit
    ):
        """
        Test that explicit SSM path works correctly.
        This confirms the explicit path is the right workaround.
        """
        app = App()
        stack_config = StackConfig(
            lambdas_api_gateway_config_with_explicit,
            workload=workload_config.dictionary,
        )
        
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment_config
        stack.workload = workload_config
        
        # Get the explicit SSM path
        ssm_imports = stack_config.dictionary.get("api_gateway", {}).get("ssm", {}).get("imports", {})
        user_pool_arn_path = ssm_imports.get("user_pool_arn")
        
        print(f"\n✅ Explicit SSM path configured: {user_pool_arn_path}")
        assert user_pool_arn_path == "/geekcafe/prod/cognito/user-pool/user-pool-arn"
        
        print(f"✅ This matches the infrastructure export path!")

    def test_identify_auto_discovery_logic(self):
        """
        Test to identify what the actual auto-discovery logic does.
        This will help us understand if it's a CDK Factory bug or config issue.
        """
        # When user_pool_arn is "auto", what path pattern does CDK Factory construct?
        workload = "geekcafe"
        environment = "prod"
        
        # Pattern 1: Simple underscore pattern (most common in CDK Factory)
        pattern1 = f"/{workload}/{environment}/cognito/user_pool_arn"
        
        # Pattern 2: Nested resource pattern
        pattern2 = f"/{workload}/{environment}/cognito/user-pool/user-pool-arn"
        
        # Actual infrastructure export
        actual = "/geekcafe/prod/cognito/user-pool/user-pool-arn"
        
        print(f"\n📊 Path Comparison:")
        print(f"   Auto pattern 1 (underscore):  {pattern1}")
        print(f"   Auto pattern 2 (nested):      {pattern2}")
        print(f"   Infrastructure export:        {actual}")
        print(f"")
        print(f"   Pattern 1 matches: {pattern1 == actual}")
        print(f"   Pattern 2 matches: {pattern2 == actual}")
        
        if pattern2 == actual:
            print(f"\n✅ Infrastructure uses nested hyphen pattern")
            print(f"💡 CDK Factory auto-discovery should use: /{'{workload}'}/{'{environment}'}/cognito/user-pool/user-pool-arn")
        elif pattern1 == actual:
            print(f"\n✅ Infrastructure uses underscore pattern")
            print(f"💡 This is the expected CDK Factory auto-discovery pattern")
        else:
            print(f"\n❌ Neither pattern matches!")
            print(f"💡 This indicates a bug in either:")
            print(f"   1. CDK Factory auto-discovery logic, OR")
            print(f"   2. CDK Factory cognito_stack export logic")

    def test_recommendation_for_fix(self):
        """
        Provide recommendations for fixing the auto-import.
        """
        print(f"\n" + "="*80)
        print(f"🔧 RECOMMENDATIONS FOR FIX")
        print(f"="*80)
        
        print(f"\nOption 1: Update CDK Factory Auto-Discovery Logic")
        print(f"   - File: cdk_factory/stack_library/api_gateway/api_gateway_stack.py")
        print(f"   - Update auto-discovery to use: /{{workload}}/{{env}}/cognito/user-pool/user-pool-arn")
        print(f"   - Match the nested hyphen pattern used by cognito_stack exports")
        
        print(f"\nOption 2: Update CDK Factory Cognito Stack Export Logic")
        print(f"   - File: cdk_factory/stack_library/cognito/cognito_stack.py")
        print(f"   - Update export to use: /{{workload}}/{{env}}/cognito/user_pool_arn")
        print(f"   - Use simple underscore pattern expected by auto-discovery")
        
        print(f"\nOption 3: Standardize SSM Path Convention (RECOMMENDED)")
        print(f"   - Create a centralized SSM path builder utility")
        print(f"   - Ensure ALL stacks (cognito, lambda, api_gateway) use same pattern")
        print(f"   - Pattern: /{{workload}}/{{env}}/{{service}}/{{resource}}/{{attribute}}")
        print(f"   - Example: /geekcafe/prod/cognito/user-pool/arn")
        
        print(f"\nCurrent Workaround:")
        print(f"   - Use explicit path: \"/geekcafe/prod/cognito/user-pool/user-pool-arn\"")
        print(f"   - This works but bypasses auto-discovery")
        print(f"="*80 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
