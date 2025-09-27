"""
Unit tests to verify that allow_public_override actually generates NONE authorization in CloudFormation.

This test specifically validates that the enhanced authorization validation 
correctly produces AuthorizationType: NONE in the synthesized CloudFormation template.
"""

import unittest
import os
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewayPublicOverrideSynthesis(unittest.TestCase):
    """Test that allow_public_override actually produces NONE authorization in CloudFormation"""

    def setUp(self):
        """Set up test environment"""
        # Set required environment variables
        os.environ["ENVIRONMENT"] = "test"
        os.environ["AWS_ACCOUNT_NUMBER"] = "123456789012"

        self.app = App()

        # Create base workload config
        self.base_workload = WorkloadConfig(
            {
                "name": "test-public-override",
                "description": "Test workload for public override synthesis",
                "devops": {
                    "account": "123456789012",
                    "region": "us-east-1",
                    "commands": [],
                },
                "stacks": [],
            }
        )

    def test_allow_public_override_produces_none_authorization(self):
        """Test that allow_public_override: true actually produces AuthorizationType: NONE in CloudFormation"""
        
        # Configuration that should produce NONE authorization
        stack_config = StackConfig(
            {
                "name": "api-public-override-synthesis",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-public-override",
                    "description": "Test API with public override synthesis",
                    "endpoint_types": ["REGIONAL"],
                    # NO cognito_authorizer section - this is key!
                    "routes": [
                        {
                            "path": "/public-messages",
                            "method": "POST",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            "authorization_type": "NONE",
                            "allow_public_override": True,  # This should work without Cognito
                        }
                    ],
                },
            },
            workload=self.base_workload.dictionary,
        )

        deployment = DeploymentConfig(
            workload=self.base_workload.dictionary,
            deployment={"name": "test-deployment"},
        )

        # Create and build the stack
        stack = ApiGatewayStack(self.app, "TestPublicOverrideSynthesis")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Find API Gateway Method resources
        method_resources = []
        for resource_id, resource in cf_template.get("Resources", {}).items():
            if resource.get("Type") == "AWS::ApiGateway::Method":
                method_resources.append((resource_id, resource))

        # Filter out OPTIONS methods (CORS)
        non_options_methods = [
            (resource_id, resource) for resource_id, resource in method_resources
            if resource["Properties"].get("HttpMethod") != "OPTIONS"
        ]

        # Should have exactly one non-OPTIONS method
        self.assertEqual(len(non_options_methods), 1, 
                        f"Expected 1 non-OPTIONS method, found {len(non_options_methods)}")

        resource_id, method_resource = non_options_methods[0]
        
        # Verify the method properties
        properties = method_resource["Properties"]
        self.assertEqual(properties.get("HttpMethod"), "POST")
        
        # This is the critical test - should be NONE, not COGNITO_USER_POOLS
        self.assertEqual(properties.get("AuthorizationType"), "NONE", 
                        f"Expected AuthorizationType: NONE, but got: {properties.get('AuthorizationType')}")
        
        # Should not have an authorizer reference
        self.assertNotIn("AuthorizerId", properties, 
                        "Public endpoint should not have AuthorizerId")

        print(f"✅ SUCCESS: Method {resource_id} has AuthorizationType: {properties.get('AuthorizationType')}")

    def test_no_cognito_with_explicit_none_produces_none_authorization(self):
        """Test that explicit NONE without Cognito produces AuthorizationType: NONE"""
        
        # Configuration without Cognito and explicit NONE
        stack_config = StackConfig(
            {
                "name": "api-no-cognito-explicit-none",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-no-cognito",
                    "description": "Test API without Cognito",
                    "endpoint_types": ["REGIONAL"],
                    # NO cognito_authorizer section
                    "routes": [
                        {
                            "path": "/health",
                            "method": "GET",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            "authorization_type": "NONE",  # Explicit NONE without Cognito
                        }
                    ],
                },
            },
            workload=self.base_workload.dictionary,
        )

        deployment = DeploymentConfig(
            workload=self.base_workload.dictionary,
            deployment={"name": "test-deployment"},
        )

        # Create and build the stack
        stack = ApiGatewayStack(self.app, "TestNoCognitoExplicitNone")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Find the GET method
        method_resources = []
        for resource_id, resource in cf_template.get("Resources", {}).items():
            if (resource.get("Type") == "AWS::ApiGateway::Method" and 
                resource["Properties"].get("HttpMethod") == "GET"):
                method_resources.append((resource_id, resource))

        self.assertEqual(len(method_resources), 1, "Should have exactly one GET method")
        
        resource_id, method_resource = method_resources[0]
        properties = method_resource["Properties"]
        
        # Should be NONE authorization
        self.assertEqual(properties.get("AuthorizationType"), "NONE",
                        f"Expected AuthorizationType: NONE, but got: {properties.get('AuthorizationType')}")

    def test_default_behavior_without_cognito_produces_none_authorization(self):
        """Test that default behavior without Cognito produces AuthorizationType: NONE"""
        
        # Configuration without Cognito and no explicit authorization_type
        stack_config = StackConfig(
            {
                "name": "api-default-no-cognito",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-default-no-cognito",
                    "description": "Test API default behavior without Cognito",
                    "endpoint_types": ["REGIONAL"],
                    # NO cognito_authorizer section
                    "routes": [
                        {
                            "path": "/default-auth",
                            "method": "PUT",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            # No authorization_type specified - should default to NONE when no Cognito
                        }
                    ],
                },
            },
            workload=self.base_workload.dictionary,
        )

        deployment = DeploymentConfig(
            workload=self.base_workload.dictionary,
            deployment={"name": "test-deployment"},
        )

        # Create and build the stack
        stack = ApiGatewayStack(self.app, "TestDefaultNoCognito")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Find the PUT method
        method_resources = []
        for resource_id, resource in cf_template.get("Resources", {}).items():
            if (resource.get("Type") == "AWS::ApiGateway::Method" and 
                resource["Properties"].get("HttpMethod") == "PUT"):
                method_resources.append((resource_id, resource))

        self.assertEqual(len(method_resources), 1, "Should have exactly one PUT method")
        
        resource_id, method_resource = method_resources[0]
        properties = method_resource["Properties"]
        
        # Should be NONE authorization (fallback behavior)
        self.assertEqual(properties.get("AuthorizationType"), "NONE",
                        f"Expected AuthorizationType: NONE (fallback), but got: {properties.get('AuthorizationType')}")

        print(f"✅ SUCCESS: Default behavior produces AuthorizationType: {properties.get('AuthorizationType')}")


if __name__ == "__main__":
    unittest.main()
