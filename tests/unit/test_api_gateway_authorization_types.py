"""
Unit tests for API Gateway authorization types functionality
Tests the authorization_type logic using factory build and CloudFormation synthesis
"""

import unittest
import os
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from utils.synth_test_utils import (
    get_resources_by_type,
    assert_resource_count,
    assert_has_resource_with_properties
)


class TestApiGatewayAuthorizationTypes(unittest.TestCase):
    """Test API Gateway authorization types functionality with real CDK synthesis"""

    def setUp(self):
        """Set up test environment"""
        # Set required environment variables
        os.environ["ENVIRONMENT"] = "test"
        os.environ["AWS_ACCOUNT_NUMBER"] = "123456789012"
        
        self.app = App()
        
        # Create base workload config
        self.base_workload = WorkloadConfig({
            "name": "test-workload",
            "description": "Test workload for authorization types testing",
            "devops": {
                "account": "123456789012",
                "region": "us-east-1",
                "commands": []
            },
            "stacks": []
        })

    def test_authorization_type_none(self):
        """Test that authorization_type: NONE creates public routes"""
        
        # Configuration with authorization_type: NONE for public routes
        stack_config = StackConfig({
            "name": "api-auth-none",
            "module": "api_gateway_library_module",
            "enabled": True,
            "api_gateway": {
                "name": "test-api-public",
                "description": "Test API with public routes",
                "endpoint_types": ["REGIONAL"],
                # No cognito_authorizer section since all routes are public
                "routes": [
                    {
                        "path": "/public-health",
                        "method": "GET",
                        "src": "./src/cdk_factory/lambdas",
                        "handler": "health_handler.lambda_handler",
                        "authorization_type": "NONE"  # Explicit public access
                    },
                    {
                        "path": "/public-status",
                        "method": "POST",
                        "src": "./src/cdk_factory/lambdas",
                        "handler": "health_handler.lambda_handler",
                        "authorization_type": "NONE"  # Explicit public access
                    }
                ]
            }
        }, workload=self.base_workload.dictionary)

        deployment = DeploymentConfig(
            workload=self.base_workload.dictionary,
            deployment={"name": "test-deployment"}
        )

        # Create and build the stack
        stack = ApiGatewayStack(self.app, "TestAuthorizationTypeNone")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Verify we have methods
        method_resources = get_resources_by_type(cf_template, "AWS::ApiGateway::Method")
        self.assertGreaterEqual(len(method_resources), 2, "Should have at least 2 methods")

        # All methods should have AuthorizationType: NONE and no AuthorizerId
        none_methods = []
        
        for method_info in method_resources:
            method = method_info["resource"]
            # Skip OPTIONS methods (CORS)
            if method["Properties"].get("HttpMethod") == "OPTIONS":
                continue
                
            auth_type = method["Properties"].get("AuthorizationType")
            if auth_type == "NONE":
                none_methods.append(method)

        # Verify all non-OPTIONS methods use NONE authorization
        self.assertEqual(len(none_methods), 2, "Both routes should have NONE authorization")
        
        # Verify no methods have AuthorizerId (since they're public)
        for method in none_methods:
            self.assertNotIn("AuthorizerId", method["Properties"], 
                           "NONE auth method should not have AuthorizerId")

    def test_secure_by_default_cognito_authorization(self):
        """Test that routes default to COGNITO_USER_POOLS authorization when not specified"""
        
        # Configuration with mixed authorization types
        stack_config = StackConfig({
            "name": "api-auth-mixed",
            "module": "api_gateway_library_module",
            "enabled": True,
            "api_gateway": {
                "name": "test-api-mixed",
                "description": "Test API with mixed authorization",
                "endpoint_types": ["REGIONAL"],
                "cognito_authorizer": {
                    "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123",
                    "authorizer_name": "TestAuthorizer"
                },
                "routes": [
                    {
                        "path": "/public",
                        "method": "GET",
                        "src": "./src/cdk_factory/lambdas",
                        "handler": "health_handler.lambda_handler",
                        "authorization_type": "NONE"  # Explicit public access
                    },
                    {
                        "path": "/secure-explicit",
                        "method": "POST",
                        "src": "./src/cdk_factory/lambdas",
                        "handler": "health_handler.lambda_handler",
                        "authorization_type": "COGNITO_USER_POOLS"  # Explicit secure
                    },
                    {
                        "path": "/secure-default",
                        "method": "PUT",
                        "src": "./src/cdk_factory/lambdas",
                        "handler": "health_handler.lambda_handler"
                        # No authorization_type - should default to COGNITO_USER_POOLS
                    }
                ]
            }
        }, workload=self.base_workload.dictionary)

        deployment = DeploymentConfig(
            workload=self.base_workload.dictionary,
            deployment={"name": "test-deployment"}
        )

        # Create and build the stack
        stack = ApiGatewayStack(self.app, "TestSecureByDefault")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Verify we have methods
        method_resources = get_resources_by_type(cf_template, "AWS::ApiGateway::Method")
        self.assertGreaterEqual(len(method_resources), 3, "Should have at least 3 methods")

        # Categorize methods by authorization type
        none_methods = []
        cognito_methods = []
        
        for method_info in method_resources:
            method = method_info["resource"]
            # Skip OPTIONS methods (CORS)
            if method["Properties"].get("HttpMethod") == "OPTIONS":
                continue
                
            auth_type = method["Properties"].get("AuthorizationType")
            if auth_type == "NONE":
                none_methods.append(method)
            elif auth_type == "COGNITO_USER_POOLS":
                cognito_methods.append(method)

        # Verify we have the expected authorization distribution
        self.assertEqual(len(none_methods), 1, "Should have 1 public route (authorization_type: NONE)")
        self.assertEqual(len(cognito_methods), 2, "Should have 2 secure routes (explicit + default)")
        
        # Verify the public method has no AuthorizerId
        for method in none_methods:
            self.assertNotIn("AuthorizerId", method["Properties"], 
                           "NONE auth method should not have AuthorizerId")
        
        # Verify the secure methods have AuthorizerId
        for method in cognito_methods:
            self.assertIn("AuthorizerId", method["Properties"], 
                        "COGNITO_USER_POOLS auth method should have AuthorizerId")


if __name__ == "__main__":
    unittest.main()
