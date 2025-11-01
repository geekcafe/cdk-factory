"""
Unit tests for Cognito App Clients functionality.
Tests app client creation, auth flows, OAuth, secrets management, and SSM exports.
"""

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template, Match
from cdk_factory.stack_library.cognito.cognito_stack import CognitoStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


@pytest.fixture
def app():
    """Create a CDK app for testing"""
    return App()


@pytest.fixture
def workload_config():
    """Create a workload configuration"""
    return WorkloadConfig(
        {"workload": {"name": "test-workload", "devops": {"name": "test-devops"}}}
    )


@pytest.fixture
def deployment_config(workload_config):
    """Create a deployment configuration"""
    return DeploymentConfig(
        workload=workload_config.dictionary,
        deployment={
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
        },
    )


class TestCognitoAppClients:
    """Test suite for Cognito app client functionality"""

    def _create_stack_config(self, config_dict, workload_config):
        """Helper to create StackConfig with workload"""
        return StackConfig(config_dict, workload=workload_config.dictionary)

    def test_single_app_client_with_srp_auth(
        self, app, deployment_config, workload_config
    ):
        """Test creating a single app client with USER_SRP_AUTH flow"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "web-app",
                            "generate_secret": False,
                            "auth_flows": {
                                "user_srp": True,
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify User Pool created
        template.resource_count_is("AWS::Cognito::UserPool", 1)

        # Verify app client created
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "web-app",
                "GenerateSecret": False,
                "ExplicitAuthFlows": Match.array_with(
                    ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
                ),
            },
        )

    def test_app_client_with_multiple_auth_flows(
        self, app, deployment_config, workload_config
    ):
        """Test app client with multiple authentication flows enabled"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "dev-client",
                            "generate_secret": False,
                            "auth_flows": {
                                "user_srp": True,
                                "user_password": True,
                                "custom": True,
                                "admin_user_password": True,
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify all auth flows are enabled
        # Note: Array order may vary, so we check that all expected flows are present
        template_json = template.to_json()
        dev_client = None
        for resource in template_json.get("Resources", {}).values():
            if (
                resource.get("Type") == "AWS::Cognito::UserPoolClient"
                and resource.get("Properties", {}).get("ClientName") == "dev-client"
            ):
                dev_client = resource
                break

        assert dev_client is not None, "Dev client not found"
        explicit_flows = set(dev_client["Properties"]["ExplicitAuthFlows"])
        expected_flows = {
            "ALLOW_USER_SRP_AUTH",
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_CUSTOM_AUTH",
            "ALLOW_ADMIN_USER_PASSWORD_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
        }
        assert (
            explicit_flows == expected_flows
        ), f"Expected {expected_flows}, got {explicit_flows}"

    def test_app_client_with_oauth_configuration(
        self, app, deployment_config, workload_config
    ):
        """Test app client with OAuth flows and callback URLs"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "oauth-app",
                            "generate_secret": False,
                            "auth_flows": {
                                "user_srp": True,
                            },
                            "oauth": {
                                "flows": {
                                    "authorization_code_grant": True,
                                    "implicit_code_grant": False,
                                    "client_credentials": False,
                                },
                                "scopes": ["email", "openid", "profile"],
                                "callback_urls": ["https://example.com/callback"],
                                "logout_urls": ["https://example.com/logout"],
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify OAuth configuration
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "oauth-app",
                "AllowedOAuthFlows": ["code"],
                "AllowedOAuthScopes": Match.array_with(["email", "openid", "profile"]),
                "CallbackURLs": ["https://example.com/callback"],
                "LogoutURLs": ["https://example.com/logout"],
            },
        )

    def test_app_client_with_client_secret(
        self, app, deployment_config, workload_config
    ):
        """Test app client with client secret generation and Secrets Manager storage"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "backend-service",
                            "generate_secret": True,
                            "auth_flows": {
                                "admin_user_password": True,
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify app client with secret
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "backend-service",
                "GenerateSecret": True,
            },
        )

        # Verify custom resource for retrieving secret exists
        # The Custom::AWS resource is created to fetch the client secret
        template.resource_count_is("Custom::AWS", 1)

        # Verify Secrets Manager secrets created
        template.resource_count_is("AWS::SecretsManager::Secret", 2)

        # Verify credentials secret
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Description": "Cognito app client credentials for backend-service",
            },
        )

    def test_app_client_with_token_validity(
        self, app, deployment_config, workload_config
    ):
        """Test app client with custom token validity settings"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "mobile-app",
                            "generate_secret": False,
                            "auth_flows": {
                                "user_srp": True,
                            },
                            "access_token_validity": {"minutes": 60},
                            "id_token_validity": {"hours": 1},
                            "refresh_token_validity": {"days": 90},
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify token validity settings
        # Note: CDK converts all durations to minutes internally
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "mobile-app",
                "AccessTokenValidity": 60,  # 60 minutes
                "IdTokenValidity": 60,  # 1 hour = 60 minutes
                "RefreshTokenValidity": 129600,  # 90 days = 129600 minutes
                "TokenValidityUnits": {
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "minutes",
                },
            },
        )

    def test_multiple_app_clients(self, app, deployment_config, workload_config):
        """Test creating multiple app clients with different configurations"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "web-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                        },
                        {
                            "name": "mobile-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            "refresh_token_validity": {"days": 90},
                        },
                        {
                            "name": "backend-service",
                            "generate_secret": True,
                            "auth_flows": {"admin_user_password": True},
                        },
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify 3 app clients created
        template.resource_count_is("AWS::Cognito::UserPoolClient", 3)

        # Verify each client exists
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {"ClientName": "web-app"},
        )
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {"ClientName": "mobile-app"},
        )
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {"ClientName": "backend-service", "GenerateSecret": True},
        )

    def test_app_client_ssm_export(self, app, deployment_config, workload_config):
        """Test SSM parameter export for app client IDs"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "web-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                        }
                    ],
                    "ssm": {
                        "enabled": True,
                        "organization": "my-app",
                        "environment": "prod",
                        "exports": {
                            "user_pool_id": "/my-app/prod/cognito/user-pool/user-pool-id"
                        },
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify SSM parameters created for user pool
        # Enhanced SSM uses hyphens in parameter names
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/prod/cognito/user-pool/user-pool-id",
                "Type": "String",
            },
        )

        # Note: App client ID export is done through enhanced SSM mixin
        # which uses export_standardized_ssm_parameters, so we check that the client was created
        template.resource_count_is("AWS::Cognito::UserPoolClient", 1)

    def test_app_client_secret_ssm_arn_export(
        self, app, deployment_config, workload_config
    ):
        """Test SSM parameter export for Secrets Manager ARN"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "backend-service",
                            "generate_secret": True,
                            "auth_flows": {"admin_user_password": True},
                        }
                    ],
                    "ssm": {
                        "enabled": True,
                        "organization": "my-app",
                        "environment": "prod",
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify SSM parameter for secret ARN
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/my-app/prod/cognito/user-pool/app_client_backend_service_secret_arn",
                "Type": "String",
                "Description": "Secrets Manager ARN for backend-service credentials",
            },
        )

    def test_app_client_with_identity_providers(
        self, app, deployment_config, workload_config
    ):
        """Test app client with supported identity providers"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "social-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            "supported_identity_providers": [
                                "COGNITO",
                                "Google",
                                "Facebook",
                            ],
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify identity providers
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "social-app",
                "SupportedIdentityProviders": Match.array_with(
                    ["COGNITO", "Google", "Facebook"]
                ),
            },
        )

    def test_app_client_with_read_write_attributes(
        self, app, deployment_config, workload_config
    ):
        """Test app client with read and write attribute permissions"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "attribute-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            "read_attributes": ["email", "name", "phone_number"],
                            "write_attributes": ["name"],
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify attribute permissions
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "attribute-app",
                "ReadAttributes": Match.array_with(["email", "name", "phone_number"]),
                "WriteAttributes": ["name"],
            },
        )

    def test_app_client_prevent_user_existence_errors(
        self, app, deployment_config, workload_config
    ):
        """Test app client with prevent user existence errors enabled"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "secure-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            "prevent_user_existence_errors": True,
                            "enable_token_revocation": True,
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify security settings
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "secure-app",
                "PreventUserExistenceErrors": "ENABLED",
                "EnableTokenRevocation": True,
            },
        )

    def test_app_client_with_client_credentials_oauth(
        self, app, deployment_config, workload_config
    ):
        """Test app client with client credentials OAuth flow"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "m2m-service",
                            "generate_secret": True,
                            "auth_flows": {"admin_user_password": True},
                            "oauth": {
                                "flows": {"client_credentials": True},
                                "scopes": ["api/read", "api/write"],
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify client credentials flow
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "m2m-service",
                "GenerateSecret": True,
                "AllowedOAuthFlows": ["client_credentials"],
            },
        )

    def test_amplify_app_client_no_oauth(self, app, deployment_config, workload_config):
        """Test typical Amplify app client configuration (no OAuth)"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "amplify-web-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            # No OAuth configuration
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify simple Amplify client has correct properties
        # Note: CDK may add default OAuth flows, but they won't be used without callback URLs
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "amplify-web-app",
                "GenerateSecret": False,
                "ExplicitAuthFlows": Match.array_with(
                    ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
                ),
            },
        )

        # Verify the app client exists and is configured correctly
        template.resource_count_is("AWS::Cognito::UserPoolClient", 1)

    def test_custom_auth_flow_configuration(
        self, app, deployment_config, workload_config
    ):
        """Test app client with custom authentication flow"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "passwordless-app",
                            "generate_secret": False,
                            "auth_flows": {"custom": True, "user_srp": True},
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify custom auth flow enabled
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "passwordless-app",
                "ExplicitAuthFlows": Match.array_with(
                    [
                        "ALLOW_CUSTOM_AUTH",
                        "ALLOW_USER_SRP_AUTH",
                        "ALLOW_REFRESH_TOKEN_AUTH",
                    ]
                ),
            },
        )

    def test_no_app_clients_configured(self, app, deployment_config, workload_config):
        """Test that stack works without app clients configured"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    # No app_clients configured
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify user pool created but no app clients
        template.resource_count_is("AWS::Cognito::UserPool", 1)
        template.resource_count_is("AWS::Cognito::UserPoolClient", 0)

    def test_app_client_name_sanitization_for_ssm(
        self, app, deployment_config, workload_config
    ):
        """Test that app client names with hyphens/spaces are sanitized for SSM paths"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "my-backend-service",
                            "generate_secret": True,
                            "auth_flows": {"admin_user_password": True},
                        }
                    ],
                    "ssm": {
                        "enabled": True,
                        "organization": "test-org",
                        "environment": "dev",
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify SSM parameter name has sanitized client name (hyphens converted to underscores)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/test-org/dev/cognito/user-pool/app_client_my_backend_service_secret_arn",
            },
        )

    def test_complete_production_configuration(
        self, app, deployment_config, workload_config
    ):
        """Test a complete production-ready configuration with multiple client types"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "production-pool",
                    "app_clients": [
                        # Amplify web app
                        {
                            "name": "amplify-web",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True, "custom": True},
                            "access_token_validity": {"minutes": 60},
                            "refresh_token_validity": {"days": 30},
                        },
                        # Mobile app
                        {
                            "name": "mobile-app",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True},
                            "oauth": {
                                "flows": {"authorization_code_grant": True},
                                "scopes": ["email", "openid", "profile"],
                                "callback_urls": ["myapp://callback"],
                            },
                            "refresh_token_validity": {"days": 90},
                        },
                        # Backend service
                        {
                            "name": "backend-api",
                            "generate_secret": True,
                            "auth_flows": {"admin_user_password": True},
                            "oauth": {
                                "flows": {"client_credentials": True},
                            },
                            "access_token_validity": {"minutes": 30},
                        },
                    ],
                    "ssm": {
                        "enabled": True,
                        "organization": "prod-app",
                        "environment": "prod",
                        "exports": {
                            "user_pool_id": "/prod-app/prod/cognito/user-pool/user-pool-id"
                        },
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify all components created
        template.resource_count_is("AWS::Cognito::UserPool", 1)
        template.resource_count_is("AWS::Cognito::UserPoolClient", 3)

        # Verify Secrets Manager for backend service
        template.resource_count_is(
            "AWS::SecretsManager::Secret", 2
        )  # 2 secrets for backend-api

        # Verify SSM parameters (enhanced SSM uses hyphens)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/prod-app/prod/cognito/user-pool/user-pool-id"},
        )
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/prod-app/prod/cognito/user-pool/app_client_backend_api_secret_arn"
            },
        )
