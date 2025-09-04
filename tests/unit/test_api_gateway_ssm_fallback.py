"""
Unit tests for API Gateway SSM fallback functionality
Tests the SSM parameter -> environment variable -> manual config fallback chain
"""

import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import aws_cdk as cdk
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from cdk_factory.utilities.api_gateway_integration_utility import ApiGatewayIntegrationUtility
from cdk_factory.configurations.resources.apigateway_route_config import ApiGatewayConfigRouteConfig


class TestApiGatewaySSMFallback(unittest.TestCase):
    """Test SSM fallback functionality for API Gateway integration utility"""

    def setUp(self):
        """Set up test environment"""
        self.app = cdk.App()
        self.stack = cdk.Stack(self.app, "TestStack")
        self.utility = ApiGatewayIntegrationUtility(self.stack)
        
        # Mock stack config
        self.stack_config = Mock()
        self.stack_config.name = "test-stack"
        self.stack_config.dictionary = {}
        
        # Mock API config
        self.api_config = ApiGatewayConfigRouteConfig({})

    def test_api_gateway_id_direct_config(self):
        """Test API Gateway ID retrieval from direct config"""
        # Set up direct config
        self.api_config = ApiGatewayConfigRouteConfig({"api_gateway_id": "direct-api-id"})
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "direct-api-id")

    def test_api_gateway_id_stack_config(self):
        """Test API Gateway ID retrieval from stack config"""
        # Set up stack config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id": "stack-config-api-id"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "stack-config-api-id")

    @patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name')
    def test_api_gateway_id_ssm_fallback(self, mock_ssm_param):
        """Test API Gateway ID retrieval from SSM parameter"""
        # Mock SSM parameter
        mock_param = Mock()
        mock_param.string_value = "ssm-api-id"
        mock_ssm_param.return_value = mock_param
        
        # Set up SSM path in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id_ssm_path": "/test/api-gateway/id"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "ssm-api-id")
        mock_ssm_param.assert_called_once()

    @patch.dict(os.environ, {'API_GATEWAY_ID': 'env-api-id'})
    def test_api_gateway_id_env_fallback(self):
        """Test API Gateway ID retrieval from environment variable"""
        # Set up env var name in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id_env_var": "API_GATEWAY_ID"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "env-api-id")

    @patch.dict(os.environ, {'CUSTOM_API_ID': 'custom-env-api-id'})
    def test_api_gateway_id_custom_env_var(self):
        """Test API Gateway ID retrieval from custom environment variable"""
        # Set up custom env var name in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id_env_var": "CUSTOM_API_ID"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "custom-env-api-id")

    def test_authorizer_id_direct_config(self):
        """Test authorizer ID retrieval from direct config"""
        # Set up direct config
        self.api_config = ApiGatewayConfigRouteConfig({"authorizer_id": "direct-authorizer-id"})
        
        result = self.utility._get_existing_authorizer_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "direct-authorizer-id")

    def test_authorizer_id_stack_config(self):
        """Test authorizer ID retrieval from stack config"""
        # Set up stack config
        self.stack_config.dictionary = {
            "api_gateway": {
                "authorizer": {
                    "id": "stack-config-authorizer-id"
                }
            }
        }
        
        result = self.utility._get_existing_authorizer_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "stack-config-authorizer-id")

    @patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name')
    def test_authorizer_id_ssm_fallback(self, mock_ssm_param):
        """Test authorizer ID retrieval from SSM parameter"""
        # Mock SSM parameter
        mock_param = Mock()
        mock_param.string_value = "ssm-authorizer-id"
        mock_ssm_param.return_value = mock_param
        
        # Set up SSM path in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "authorizer": {
                    "id_ssm_path": "/test/authorizer/id"
                }
            }
        }
        
        result = self.utility._get_existing_authorizer_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "ssm-authorizer-id")
        mock_ssm_param.assert_called_once()

    @patch.dict(os.environ, {'COGNITO_AUTHORIZER_ID': 'env-authorizer-id'})
    def test_authorizer_id_env_fallback(self):
        """Test authorizer ID retrieval from environment variable"""
        # Set up env var name in config (uses default)
        self.stack_config.dictionary = {
            "api_gateway": {
                "authorizer": {}
            }
        }
        
        result = self.utility._get_existing_authorizer_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertEqual(result, "env-authorizer-id")

    def test_root_resource_id_direct_config(self):
        """Test root resource ID retrieval from direct config"""
        # Set up stack config
        self.stack_config.dictionary = {
            "api_gateway": {
                "root_resource_id": "direct-root-resource-id"
            }
        }
        
        result = self.utility._get_root_resource_id_with_ssm_fallback(self.stack_config)
        
        self.assertEqual(result, "direct-root-resource-id")

    @patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name')
    def test_root_resource_id_ssm_fallback(self, mock_ssm_param):
        """Test root resource ID retrieval from SSM parameter"""
        # Mock SSM parameter
        mock_param = Mock()
        mock_param.string_value = "ssm-root-resource-id"
        mock_ssm_param.return_value = mock_param
        
        # Set up SSM path in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "root_resource_id_ssm_path": "/test/api-gateway/root-resource-id"
            }
        }
        
        result = self.utility._get_root_resource_id_with_ssm_fallback(self.stack_config)
        
        self.assertEqual(result, "ssm-root-resource-id")
        mock_ssm_param.assert_called_once()

    @patch.dict(os.environ, {'API_GATEWAY_ROOT_RESOURCE_ID': 'env-root-resource-id'})
    def test_root_resource_id_env_fallback(self):
        """Test root resource ID retrieval from environment variable"""
        # Set up env var name in config (uses default)
        self.stack_config.dictionary = {
            "api_gateway": {}
        }
        
        result = self.utility._get_root_resource_id_with_ssm_fallback(self.stack_config)
        
        self.assertEqual(result, "env-root-resource-id")

    @patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name')
    def test_ssm_fallback_with_exception(self, mock_ssm_param):
        """Test SSM fallback behavior when SSM parameter lookup fails"""
        # Mock SSM parameter to raise exception
        mock_ssm_param.side_effect = Exception("SSM parameter not found")
        
        # Set up SSM path in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id_ssm_path": "/test/api-gateway/id"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        # Should return None when SSM fails and no env var is set
        self.assertIsNone(result)

    @patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name')
    @patch.dict(os.environ, {'API_GATEWAY_ID': 'env-fallback-id'})
    def test_ssm_failure_falls_back_to_env(self, mock_ssm_param):
        """Test that SSM failure falls back to environment variable"""
        # Mock SSM parameter to raise exception
        mock_ssm_param.side_effect = Exception("SSM parameter not found")
        
        # Set up SSM path and env var in config
        self.stack_config.dictionary = {
            "api_gateway": {
                "id_ssm_path": "/test/api-gateway/id",
                "id_env_var": "API_GATEWAY_ID"
            }
        }
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        # Should fall back to environment variable
        self.assertEqual(result, "env-fallback-id")

    def test_fallback_chain_priority(self):
        """Test that fallback chain respects priority: direct config > SSM > env var"""
        # Set up all sources
        self.api_config = ApiGatewayConfigRouteConfig({"api_gateway_id": "direct-config-id"})
        
        with patch.dict(os.environ, {'API_GATEWAY_ID': 'env-id'}):
            with patch('aws_cdk.aws_ssm.StringParameter.from_string_parameter_name') as mock_ssm:
                mock_param = Mock()
                mock_param.string_value = "ssm-id"
                mock_ssm.return_value = mock_param
                
                self.stack_config.dictionary = {
                    "api_gateway": {
                        "id_ssm_path": "/test/api-gateway/id",
                        "id_env_var": "API_GATEWAY_ID"
                    }
                }
                
                result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
                    self.api_config, self.stack_config
                )
                
                # Should use direct config and not call SSM
                self.assertEqual(result, "direct-config-id")
                mock_ssm.assert_not_called()

    @patch('aws_cdk.aws_ssm.StringParameter')
    def test_export_api_gateway_to_ssm(self, mock_ssm_param):
        """Test exporting API Gateway configuration to SSM parameters"""
        # Mock API Gateway
        mock_api_gateway = Mock()
        mock_api_gateway.rest_api_id = "test-api-id"
        mock_api_gateway.rest_api_arn = "arn:aws:apigateway:us-east-1::/restapis/test-api-id"
        mock_api_gateway.root.resource_id = "root-resource-id"
        
        # Mock authorizer
        mock_authorizer = Mock()
        mock_authorizer.authorizer_id = "test-authorizer-id"
        
        # Mock SSM parameter creation
        mock_param_instance = Mock()
        mock_param_instance.parameter_name = "/test/param"
        mock_ssm_param.return_value = mock_param_instance
        
        result = self.utility.export_api_gateway_to_ssm(
            mock_api_gateway, mock_authorizer, self.stack_config
        )
        
        # Verify SSM parameters were created
        self.assertEqual(len(result), 4)  # API ID, ARN, root resource ID, authorizer ID
        self.assertIn("api_gateway_id", result)
        self.assertIn("api_gateway_arn", result)
        self.assertIn("root_resource_id", result)
        self.assertIn("authorizer_id", result)
        
        # Verify SSM parameter constructor was called multiple times
        self.assertEqual(mock_ssm_param.call_count, 4)

    def test_no_fallback_sources_returns_none(self):
        """Test that when no fallback sources are configured, None is returned"""
        # Empty config
        self.stack_config.dictionary = {}
        
        result = self.utility._get_existing_api_gateway_id_with_ssm_fallback(
            self.api_config, self.stack_config
        )
        
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
