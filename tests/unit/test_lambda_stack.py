"""
Unit tests for Lambda Stack with API Gateway integration.
Tests the enhanced lambda_stack.py functionality including service factory integration.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from aws_cdk import App, Stack, Environment
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_cognito as cognito

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack


class TestLambdaStack:
    """Test cases for Lambda Stack functionality."""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing."""
        return App()

    @pytest.fixture
    def deployment_config(self):
        """Create deployment configuration."""
        config = Mock(spec=DeploymentConfig)
        config.name = "test-deployment"
        config.get_env_var = Mock(return_value="test-value")
        return config

    @pytest.fixture
    def workload_config(self):
        """Create workload configuration."""
        config = Mock(spec=WorkloadConfig)
        config.name = "test-workload"
        return config

    @pytest.fixture
    def stack_config(self):
        """Create stack configuration."""
        config = Mock(spec=StackConfig)
        config.name = "test-lambda-stack"
        config.enabled = True
        return config

    @pytest.fixture
    def lambda_function_config(self):
        """Create lambda function configuration."""
        config = Mock(spec=LambdaFunctionConfig)
        config.name = "test-function"
        config.source_directory = "src/handlers/test"
        config.handler = "handler.lambda_handler"
        config.runtime = "python3.11"
        config.timeout = 30
        config.memory_size = 256
        config.environment_variables = {"TEST_VAR": "test_value"}
        config.api = None
        config.triggers = []
        config.sqs = Mock()
        config.sqs.queues = []
        config.schedule = None
        return config

    @pytest.fixture
    def lambda_function_config_with_api(self, lambda_function_config):
        """Create lambda function configuration with API Gateway integration."""
        api_config = Mock()
        api_config.routes = "/test/endpoint"
        api_config.method = "POST"
        api_config.skip_authorizer = False
        api_config.api_key_required = False
        api_config.request_parameters = {}
        api_config.existing_api_gateway_id = None
        api_config.existing_authorizer_id = None
        
        lambda_function_config.api = api_config
        return lambda_function_config

    def test_lambda_stack_initialization(self, app, deployment_config, workload_config, stack_config):
        """Test Lambda stack initializes correctly."""
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        # Mock the stack config to have empty resources
        stack_config.dictionary = {"resources": []}
        
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config
        )
        
        assert stack is not None
        assert hasattr(stack, 'functions')
        assert stack.api_gateway_integrations == []

    @patch('cdk_factory.stack_library.aws_lambdas.lambda_stack.LambdaConstruct')
    def test_create_lambda_function_basic(self, mock_lambda_construct, app, deployment_config, 
                                        workload_config, stack_config, lambda_function_config):
        """Test basic lambda function creation without API Gateway."""
        # Setup mock
        mock_lambda_instance = Mock()
        mock_lambda_construct.return_value = mock_lambda_instance
        mock_lambda_instance.function.return_value = Mock(spec=_lambda.Function)
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        stack_config.dictionary = {"resources": []}
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config
        )
        
        # Create lambda function
        result = stack._LambdaStack__setup_lambda_code_asset(lambda_function_config)
        
        assert result is not None
        mock_lambda_construct.assert_called_once()
        assert len(stack.api_gateway_integrations) == 0

    @patch('cdk_factory.stack_library.aws_lambdas.lambda_stack.LambdaConstruct')
    def test_create_lambda_function_with_api_gateway(self, mock_lambda_construct, app, deployment_config,
                                                   workload_config, stack_config, lambda_function_config_with_api):
        """Test lambda function creation with API Gateway integration."""
        # Setup mocks
        mock_lambda_instance = Mock()
        mock_lambda_construct.return_value = mock_lambda_instance
        mock_lambda_function = Mock(spec=_lambda.Function)
        mock_lambda_instance.function.return_value = mock_lambda_function
        
        # Mock deployment config for Cognito
        deployment_config.get_env_var.return_value = "test-user-pool-id"
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        with patch.object(stack, '_LambdaStack__setup_api_gateway_integration') as mock_api_setup:
            # Create lambda function
            result = stack._LambdaStack__create_lambda_function(lambda_function_config_with_api)
            
            assert result is not None
            mock_lambda_construct.assert_called_once()
            mock_api_setup.assert_called_once_with(
                lambda_function=mock_lambda_function,
                function_config=lambda_function_config_with_api
            )

    def test_get_or_create_api_gateway_new(self, app, deployment_config, workload_config, stack_config):
        """Test creating new API Gateway."""
        api_config = Mock()
        api_config.existing_api_gateway_id = None
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        with patch('aws_cdk.aws_apigateway.RestApi') as mock_rest_api:
            mock_api = Mock(spec=apigateway.RestApi)
            mock_rest_api.return_value = mock_api
            
            result = stack._LambdaStack__get_or_create_api_gateway(api_config)
            
            assert result == mock_api
            mock_rest_api.assert_called_once()

    def test_get_or_create_api_gateway_existing(self, app, deployment_config, workload_config, stack_config):
        """Test referencing existing API Gateway."""
        api_config = Mock()
        api_config.existing_api_gateway_id = "existing-api-123"
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        with patch('aws_cdk.aws_apigateway.RestApi.from_rest_api_id') as mock_from_api_id:
            mock_api = Mock(spec=apigateway.RestApi)
            mock_from_api_id.return_value = mock_api
            
            result = stack._LambdaStack__get_or_create_api_gateway(api_config)
            
            assert result == mock_api
            mock_from_api_id.assert_called_once_with(
                stack,
                "imported-api-existing-api-123",
                "existing-api-123"
            )

    def test_get_or_create_authorizer_new(self, app, deployment_config, workload_config, stack_config):
        """Test creating new Cognito authorizer."""
        api_config = Mock()
        api_config.existing_authorizer_id = None
        
        mock_api_gateway = Mock(spec=apigateway.RestApi)
        mock_api_gateway.node.id = "test-api"
        
        deployment_config.get_env_var.return_value = "test-user-pool-id"
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        with patch('aws_cdk.aws_cognito.UserPool.from_user_pool_id') as mock_user_pool, \
             patch('aws_cdk.aws_apigateway.CognitoUserPoolsAuthorizer') as mock_authorizer:
            
            mock_pool = Mock(spec=cognito.UserPool)
            mock_user_pool.return_value = mock_pool
            mock_auth = Mock(spec=apigateway.CognitoUserPoolsAuthorizer)
            mock_authorizer.return_value = mock_auth
            
            result = stack._LambdaStack__get_or_create_authorizer(mock_api_gateway, api_config)
            
            assert result == mock_auth
            mock_user_pool.assert_called_once()
            mock_authorizer.assert_called_once()

    def test_get_or_create_authorizer_missing_user_pool(self, app, deployment_config, workload_config, stack_config):
        """Test error when COGNITO_USER_POOL_ID is missing."""
        api_config = Mock()
        api_config.existing_authorizer_id = None
        
        mock_api_gateway = Mock(spec=apigateway.RestApi)
        mock_api_gateway.node.id = "test-api"
        
        deployment_config.get_env_var.return_value = None
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        with pytest.raises(ValueError, match="COGNITO_USER_POOL_ID environment variable is required"):
            stack._LambdaStack__get_or_create_authorizer(mock_api_gateway, api_config)

    def test_get_or_create_resource_root(self, app, deployment_config, workload_config, stack_config):
        """Test getting root resource."""
        mock_api_gateway = Mock(spec=apigateway.RestApi)
        mock_root = Mock(spec=apigateway.Resource)
        mock_api_gateway.root = mock_root
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        result = stack._LambdaStack__get_or_create_resource(mock_api_gateway, "/")
        assert result == mock_root
        
        result = stack._LambdaStack__get_or_create_resource(mock_api_gateway, "")
        assert result == mock_root

    def test_get_or_create_resource_nested(self, app, deployment_config, workload_config, stack_config):
        """Test creating nested resources."""
        mock_api_gateway = Mock(spec=apigateway.RestApi)
        mock_root = Mock(spec=apigateway.Resource)
        mock_api_gateway.root = mock_root
        
        # Mock nested resource creation
        mock_users_resource = Mock(spec=apigateway.Resource)
        mock_root.add_resource.return_value = mock_users_resource
        mock_id_resource = Mock(spec=apigateway.Resource)
        mock_users_resource.add_resource.return_value = mock_id_resource
        
        # Mock node children (empty for new resources)
        mock_root.node.children = []
        mock_users_resource.node.children = []
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        result = stack._LambdaStack__get_or_create_resource(mock_api_gateway, "/users/{id}")
        
        assert result == mock_id_resource
        mock_root.add_resource.assert_called_with("users")
        mock_users_resource.add_resource.assert_called_with("{id}")

    def test_api_gateway_integration_storage(self, app, deployment_config, workload_config, stack_config):
        """Test that API Gateway integrations are stored correctly."""
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            deployment=deployment_config,
            workload=workload_config,
            stack_config=stack_config,
            env=Environment(account="123456789012", region="us-east-1")
        )
        
        # Mock components
        mock_lambda_function = Mock(spec=_lambda.Function)
        mock_api_gateway = Mock(spec=apigateway.RestApi)
        mock_resource = Mock(spec=apigateway.Resource)
        mock_method = Mock(spec=apigateway.Method)
        mock_integration = Mock(spec=apigateway.LambdaIntegration)
        
        function_config = Mock()
        function_config.name = "test-function"
        function_config.api = Mock()
        function_config.api.routes = "/test"
        function_config.api.method = "GET"
        function_config.api.skip_authorizer = True
        function_config.api.api_key_required = False
        function_config.api.request_parameters = {}
        
        with patch.object(stack, '_LambdaStack__get_or_create_api_gateway', return_value=mock_api_gateway), \
             patch.object(stack, '_LambdaStack__get_or_create_resource', return_value=mock_resource), \
             patch('aws_cdk.aws_apigateway.LambdaIntegration', return_value=mock_integration):
            
            mock_resource.add_method.return_value = mock_method
            
            stack._LambdaStack__setup_api_gateway_integration(mock_lambda_function, function_config)
            
            assert len(stack.api_gateway_integrations) == 1
            integration_info = stack.api_gateway_integrations[0]
            assert integration_info["function_name"] == "test-function"
            assert integration_info["api_gateway"] == mock_api_gateway
            assert integration_info["method"] == mock_method
            assert integration_info["resource"] == mock_resource
            assert integration_info["integration"] == mock_integration
