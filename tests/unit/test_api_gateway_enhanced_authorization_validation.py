"""
Unit tests for enhanced API Gateway authorization validation functionality.

Tests the new security validation logic including:
- Security conflict detection
- Explicit override requirements
- Verbose warning generation
- Configuration error handling
"""

import unittest
import os
import logging
from unittest.mock import patch, MagicMock
from io import StringIO
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewayEnhancedAuthorizationValidation(unittest.TestCase):
    """Test enhanced authorization validation with security conflict detection"""

    def setUp(self):
        """Set up test environment"""
        # Set required environment variables
        os.environ["ENVIRONMENT"] = "test"
        os.environ["AWS_ACCOUNT_NUMBER"] = "123456789012"

        self.app = App()

        # Create base workload config
        self.base_workload = WorkloadConfig(
            {
                "name": "test-workload",
                "description": "Test workload for enhanced authorization validation",
                "devops": {
                    "account": "123456789012",
                    "region": "us-east-1",
                    "commands": [],
                },
                "stacks": [],
            }
        )

        # Set up logging capture for both stack and utility
        self.log_capture = StringIO()
        self.log_handler = logging.StreamHandler(self.log_capture)
        
        # Capture logs from both the stack and utility
        self.stack_logger = logging.getLogger("cdk_factory.stack_library.api_gateway.api_gateway_stack")
        self.utility_logger = logging.getLogger("cdk_factory.utilities.api_gateway_integration_utility")
        
        self.stack_logger.addHandler(self.log_handler)
        self.utility_logger.addHandler(self.log_handler)
        self.stack_logger.setLevel(logging.INFO)
        self.utility_logger.setLevel(logging.INFO)

    def tearDown(self):
        """Clean up test environment"""
        self.stack_logger.removeHandler(self.log_handler)
        self.utility_logger.removeHandler(self.log_handler)

    def test_security_conflict_detection_without_override(self):
        """Test that security conflicts are detected when Cognito is available but NONE auth requested without override"""
        
        # Configuration with Cognito + NONE auth + NO override = Should raise error
        stack_config = StackConfig(
            {
                "name": "api-security-conflict",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-conflict",
                    "description": "Test API with security conflict",
                    "endpoint_types": ["REGIONAL"],
                    "cognito_authorizer": {
                        "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123",
                        "authorizer_name": "TestAuthorizer",
                    },
                    "routes": [
                        {
                            "path": "/dangerous-public",
                            "method": "POST",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            "authorization_type": "NONE",  # Dangerous: public with Cognito available
                            # Missing: "allow_public_override": true
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

        # Create and build the stack - should raise ValueError
        stack = ApiGatewayStack(self.app, "TestSecurityConflict")
        
        with self.assertRaises(ValueError) as context:
            stack.build(stack_config, deployment, self.base_workload)

        # Verify error message contains security conflict details
        error_message = str(context.exception)
        self.assertIn("SECURITY CONFLICT DETECTED", error_message)
        self.assertIn("/dangerous-public", error_message)
        self.assertIn("POST", error_message)
        self.assertIn("Cognito authorizer is configured", error_message)
        self.assertIn("authorization_type is set to 'NONE'", error_message)
        self.assertIn("allow_public_override", error_message)

    def test_explicit_public_override_with_warnings(self):
        """Test that explicit public override works and generates appropriate warnings"""
        
        with patch('builtins.print') as mock_print:
            # Configuration with Cognito + NONE auth + explicit override = Should work with warnings
            stack_config = StackConfig(
                {
                    "name": "api-explicit-override",
                    "module": "api_gateway_library_module", 
                    "enabled": True,
                    "api_gateway": {
                        "name": "test-api-override",
                        "description": "Test API with explicit public override",
                        "endpoint_types": ["REGIONAL"],
                        "cognito_authorizer": {
                            "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123",
                            "authorizer_name": "TestAuthorizer",
                        },
                        "routes": [
                            {
                                "path": "/intentional-public",
                                "method": "GET",
                                "src": "./src/cdk_factory/lambdas",
                                "handler": "health_handler.lambda_handler",
                                "authorization_type": "NONE",
                                "allow_public_override": True,  # Explicit override
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

            # Create and build the stack - should succeed with warnings
            stack = ApiGatewayStack(self.app, "TestExplicitOverride")
            stack.build(stack_config, deployment, self.base_workload)

            # Verify warning was printed to console
            mock_print.assert_called()
            warning_output = str(mock_print.call_args)
            self.assertIn("PUBLIC ENDPOINT CONFIGURED", warning_output)
            self.assertIn("/intentional-public", warning_output)
            self.assertIn("GET", warning_output)
            self.assertIn("allow_public_override: true", warning_output)
            self.assertIn("Cognito authentication is available but overridden", warning_output)

            # Verify structured logging
            log_output = self.log_capture.getvalue()
            self.assertIn("Public endpoint configured with Cognito available", log_output)

    def test_configuration_error_cognito_requested_but_not_available(self):
        """Test error when COGNITO auth is requested but no Cognito authorizer is configured"""
        
        # Configuration with NO Cognito + COGNITO auth = Should raise error
        stack_config = StackConfig(
            {
                "name": "api-config-error",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-config-error",
                    "description": "Test API with configuration error",
                    "endpoint_types": ["REGIONAL"],
                    # No cognito_authorizer section
                    "routes": [
                        {
                            "path": "/secure-but-no-auth",
                            "method": "POST",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            "authorization_type": "COGNITO",  # Requested but not available
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

        # Create and build the stack - should raise ValueError
        stack = ApiGatewayStack(self.app, "TestConfigError")
        
        with self.assertRaises(ValueError) as context:
            stack.build(stack_config, deployment, self.base_workload)

        # Verify error message contains configuration error details
        error_message = str(context.exception)
        self.assertIn("CONFIGURATION ERROR", error_message)
        self.assertIn("/secure-but-no-auth", error_message)
        self.assertIn("POST", error_message)
        self.assertIn("authorization_type is explicitly set to 'COGNITO'", error_message)
        self.assertIn("no Cognito authorizer configured", error_message)

    def test_public_only_api_info_logging(self):
        """Test that public-only APIs (no Cognito available) log appropriately"""
        
        # Configuration with NO Cognito + NONE auth = Should work with info logging
        stack_config = StackConfig(
            {
                "name": "api-public-only",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-public-only",
                    "description": "Test API that is public-only",
                    "endpoint_types": ["REGIONAL"],
                    # No cognito_authorizer section
                    "routes": [
                        {
                            "path": "/health",
                            "method": "GET",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            "authorization_type": "NONE",
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

        # Create and build the stack - should succeed
        stack = ApiGatewayStack(self.app, "TestPublicOnly")
        stack.build(stack_config, deployment, self.base_workload)

        # Verify info logging for public-only API
        log_output = self.log_capture.getvalue()
        self.assertIn("Public endpoint configured (no Cognito available)", log_output)
        self.assertIn("/health", log_output)
        self.assertIn("GET", log_output)

    def test_secure_by_default_behavior(self):
        """Test that routes default to COGNITO authorization when Cognito is available"""
        
        # Configuration with Cognito + no explicit auth type = Should default to COGNITO
        stack_config = StackConfig(
            {
                "name": "api-secure-default",
                "module": "api_gateway_library_module",
                "enabled": True,
                "api_gateway": {
                    "name": "test-api-secure-default",
                    "description": "Test API with secure by default",
                    "endpoint_types": ["REGIONAL"],
                    "cognito_authorizer": {
                        "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123",
                        "authorizer_name": "TestAuthorizer",
                    },
                    "routes": [
                        {
                            "path": "/secure-default",
                            "method": "POST",
                            "src": "./src/cdk_factory/lambdas",
                            "handler": "health_handler.lambda_handler",
                            # No authorization_type specified - should default to COGNITO
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

        # Create and build the stack - should succeed with secure defaults
        stack = ApiGatewayStack(self.app, "TestSecureDefault")
        stack.build(stack_config, deployment, self.base_workload)

        # Synthesize to CloudFormation and verify COGNITO_USER_POOLS authorization
        template = Template.from_stack(stack)
        cf_template = template.to_json()

        # Find method resources
        method_resources = []
        for resource_id, resource in cf_template.get("Resources", {}).items():
            if resource.get("Type") == "AWS::ApiGateway::Method":
                method_resources.append(resource)

        # Verify at least one method has COGNITO_USER_POOLS authorization
        cognito_methods = [
            method for method in method_resources
            if method["Properties"].get("AuthorizationType") == "COGNITO_USER_POOLS"
            and method["Properties"].get("HttpMethod") != "OPTIONS"  # Skip CORS
        ]
        
        self.assertGreater(len(cognito_methods), 0, "Should have at least one COGNITO authorized method")

    def test_mixed_authorization_types(self):
        """Test API with mixed authorization types (some public, some secure)"""
        
        with patch('builtins.print') as mock_print:
            # Configuration with mixed auth types
            stack_config = StackConfig(
                {
                    "name": "api-mixed-auth",
                    "module": "api_gateway_library_module",
                    "enabled": True,
                    "api_gateway": {
                        "name": "test-api-mixed",
                        "description": "Test API with mixed authorization",
                        "endpoint_types": ["REGIONAL"],
                        "cognito_authorizer": {
                            "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123",
                            "authorizer_name": "TestAuthorizer",
                        },
                        "routes": [
                            {
                                "path": "/public-health",
                                "method": "GET",
                                "src": "./src/cdk_factory/lambdas",
                                "handler": "health_handler.lambda_handler",
                                "authorization_type": "NONE",
                                "allow_public_override": True,  # Explicit public
                            },
                            {
                                "path": "/secure-data",
                                "method": "POST",
                                "src": "./src/cdk_factory/lambdas",
                                "handler": "data_handler.lambda_handler",
                                "authorization_type": "COGNITO",  # Explicit secure
                            },
                            {
                                "path": "/secure-default",
                                "method": "PUT",
                                "src": "./src/cdk_factory/lambdas",
                                "handler": "data_handler.lambda_handler",
                                # No auth type - defaults to COGNITO
                            },
                        ],
                    },
                },
                workload=self.base_workload.dictionary,
            )

            deployment = DeploymentConfig(
                workload=self.base_workload.dictionary,
                deployment={"name": "test-deployment"},
            )

            # Create and build the stack - should succeed with warnings for public endpoint
            stack = ApiGatewayStack(self.app, "TestMixedAuth")
            stack.build(stack_config, deployment, self.base_workload)

            # Verify warning was printed for public endpoint
            mock_print.assert_called()
            warning_output = str(mock_print.call_args)
            self.assertIn("PUBLIC ENDPOINT CONFIGURED", warning_output)
            self.assertIn("/public-health", warning_output)

            # Synthesize and verify mixed authorization types
            template = Template.from_stack(stack)
            cf_template = template.to_json()

            method_resources = []
            for resource_id, resource in cf_template.get("Resources", {}).items():
                if resource.get("Type") == "AWS::ApiGateway::Method":
                    method_resources.append(resource)

            # Count authorization types (excluding OPTIONS methods)
            none_methods = []
            cognito_methods = []
            
            for method in method_resources:
                if method["Properties"].get("HttpMethod") == "OPTIONS":
                    continue
                    
                auth_type = method["Properties"].get("AuthorizationType")
                if auth_type == "NONE":
                    none_methods.append(method)
                elif auth_type == "COGNITO_USER_POOLS":
                    cognito_methods.append(method)

            # Verify we have both public and secure endpoints
            self.assertEqual(len(none_methods), 1, "Should have 1 public endpoint")
            self.assertEqual(len(cognito_methods), 2, "Should have 2 secure endpoints")


if __name__ == "__main__":
    unittest.main()
