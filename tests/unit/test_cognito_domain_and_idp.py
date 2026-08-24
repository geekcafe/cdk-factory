"""
Unit tests for Cognito Domain and Identity Provider functionality.
Tests user pool domain creation (prefix and custom) and OIDC identity provider registration.
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


class TestCognitoDomain:
    """Test suite for Cognito User Pool domain configuration"""

    def _create_stack_config(self, config_dict, workload_config):
        """Helper to create StackConfig with workload"""
        return StackConfig(config_dict, workload=workload_config.dictionary)

    def test_prefix_domain_creation(self, app, deployment_config, workload_config):
        """Test creating a Cognito prefix domain"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "domain": {"prefix": "aplos-nca-dev"},
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify User Pool Domain created with prefix
        template.has_resource_properties(
            "AWS::Cognito::UserPoolDomain",
            {"Domain": "aplos-nca-dev"},
        )

    def test_no_domain_when_not_configured(
        self, app, deployment_config, workload_config
    ):
        """Test that no domain is created when domain config is absent"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # No domain resource should exist
        template.resource_count_is("AWS::Cognito::UserPoolDomain", 0)

    def test_custom_domain_creation(self, app, deployment_config, workload_config):
        """Test creating a custom Cognito domain with certificate"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "domain": {
                        "custom_domain": "auth.example.com",
                        "certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/abc-123",
                        "hosted_zone_name": "example.com",
                        "hosted_zone_id": "Z0123456789",
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify custom domain created
        template.has_resource_properties(
            "AWS::Cognito::UserPoolDomain",
            {
                "Domain": "auth.example.com",
                "CustomDomainConfig": {
                    "CertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/abc-123"
                },
            },
        )

        # Verify Route53 A record created
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Name": "auth.example.com.",
                "Type": "A",
            },
        )

        # Verify Route53 AAAA record created
        template.has_resource_properties(
            "AWS::Route53::RecordSet",
            {
                "Name": "auth.example.com.",
                "Type": "AAAA",
            },
        )

    def test_custom_domain_auto_creates_certificate(
        self, app, deployment_config, workload_config
    ):
        """Test creating a custom domain without cert_arn auto-creates via DNS validation"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "ssm": {"imports": {"route53_namespace": "test-app/dev/route53"}},
                "cognito": {
                    "user_pool_name": "test-pool",
                    "domain": {
                        "custom_domain": "auth.example.com",
                        "hosted_zone_name": "example.com",
                        "hosted_zone_id": "Z0123456789",
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify ACM certificate created (auto-generated)
        template.has_resource_properties(
            "AWS::CertificateManager::Certificate",
            {
                "DomainName": "auth.example.com",
            },
        )

        # Verify custom domain created
        template.has_resource_properties(
            "AWS::Cognito::UserPoolDomain",
            {
                "Domain": "auth.example.com",
            },
        )

    def test_custom_domain_requires_certificate_or_hosted_zone(
        self, app, deployment_config, workload_config
    ):
        """Test that custom domain raises error without certificate ARN or hosted zone"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "domain": {
                        "custom_domain": "auth.example.com",
                        # Missing both certificate_arn AND hosted_zone_name
                    },
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        with pytest.raises(
            ValueError,
            match="certificate_arn is empty and hosted_zone_name is required",
        ):
            stack.build(stack_config, deployment_config, workload_config)


class TestCognitoIdentityProviders:
    """Test suite for Cognito OIDC identity provider registration"""

    def _create_stack_config(self, config_dict, workload_config):
        """Helper to create StackConfig with workload"""
        return StackConfig(config_dict, workload=workload_config.dictionary)

    def test_oidc_provider_creation(self, app, deployment_config, workload_config):
        """Test creating an OIDC identity provider (Azure AD pattern)"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "identity_providers": [
                        {
                            "name": "AzureAD-TestTenant",
                            "type": "oidc",
                            "oidc": {
                                "client_id": "azure-client-id-123",
                                "client_secret": "test-secret-value",
                                "issuer_url": "https://login.microsoftonline.com/tenant-id-123/v2.0",
                                "scopes": ["openid", "profile", "email"],
                                "attribute_mapping": {
                                    "email": "email",
                                    "given_name": "given_name",
                                    "family_name": "family_name",
                                },
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

        # Verify OIDC Identity Provider created
        template.has_resource_properties(
            "AWS::Cognito::UserPoolIdentityProvider",
            {
                "ProviderName": "AzureAD-TestTenant",
                "ProviderType": "OIDC",
                "ProviderDetails": Match.object_like(
                    {
                        "client_id": "azure-client-id-123",
                        "oidc_issuer": "https://login.microsoftonline.com/tenant-id-123/v2.0",
                        "authorize_scopes": "openid profile email",
                    }
                ),
            },
        )

    def test_no_providers_when_not_configured(
        self, app, deployment_config, workload_config
    ):
        """Test that no identity providers are created when config is absent"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # No IdP resource should exist
        template.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 0)

    def test_provider_requires_name(self, app, deployment_config, workload_config):
        """Test that identity provider raises error without a name"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "identity_providers": [
                        {
                            "type": "oidc",
                            "oidc": {
                                "client_id": "id",
                                "client_secret": "secret",
                                "issuer_url": "https://example.com",
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        with pytest.raises(ValueError, match="'name' is required"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_provider_requires_client_secret(
        self, app, deployment_config, workload_config
    ):
        """Test that OIDC provider raises error without any client secret source"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "identity_providers": [
                        {
                            "name": "NoSecret-Provider",
                            "type": "oidc",
                            "oidc": {
                                "client_id": "id",
                                "issuer_url": "https://example.com",
                                # No client_secret, client_secret_ssm, or client_secret_secrets_manager
                            },
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        with pytest.raises(ValueError, match="No client secret configured"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_unsupported_provider_type_raises_error(
        self, app, deployment_config, workload_config
    ):
        """Test that an unsupported provider type raises ValueError"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "identity_providers": [
                        {
                            "name": "BadType",
                            "type": "ldap",
                            "oidc": {},
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        with pytest.raises(ValueError, match="Unsupported identity provider type"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_multiple_providers(self, app, deployment_config, workload_config):
        """Test creating multiple OIDC identity providers"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "identity_providers": [
                        {
                            "name": "AzureAD-TenantA",
                            "type": "oidc",
                            "oidc": {
                                "client_id": "client-a",
                                "client_secret": "secret-a",
                                "issuer_url": "https://login.microsoftonline.com/tenant-a/v2.0",
                            },
                        },
                        {
                            "name": "AzureAD-TenantB",
                            "type": "oidc",
                            "oidc": {
                                "client_id": "client-b",
                                "client_secret": "secret-b",
                                "issuer_url": "https://login.microsoftonline.com/tenant-b/v2.0",
                            },
                        },
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Verify both providers created
        template.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 2)


class TestCognitoDomainWithIdpAndClient:
    """Integration tests: domain + IdP + app client with OAuth flows together"""

    def _create_stack_config(self, config_dict, workload_config):
        """Helper to create StackConfig with workload"""
        return StackConfig(config_dict, workload=workload_config.dictionary)

    def test_full_sso_configuration(self, app, deployment_config, workload_config):
        """Test complete SSO setup: prefix domain + OIDC IdP + OAuth app client"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "domain": {"prefix": "aplos-nca-test"},
                    "identity_providers": [
                        {
                            "name": "AzureAD-Aplos",
                            "type": "oidc",
                            "oidc": {
                                "client_id": "azure-client-id",
                                "client_secret": "azure-secret",
                                "issuer_url": "https://login.microsoftonline.com/test-tenant/v2.0",
                                "scopes": ["openid", "profile", "email"],
                                "attribute_mapping": {
                                    "email": "email",
                                    "given_name": "given_name",
                                    "family_name": "family_name",
                                },
                            },
                        }
                    ],
                    "app_clients": [
                        {
                            "name": "web-client",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True, "user_password": True},
                            "oauth": {
                                "flows": {"authorization_code_grant": True},
                                "scopes": ["openid", "email", "profile"],
                                "callback_urls": [
                                    "https://app.example.com/",
                                    "http://localhost:5173/",
                                ],
                                "logout_urls": [
                                    "https://app.example.com/",
                                    "http://localhost:5173/",
                                ],
                            },
                            "supported_identity_providers": [
                                "COGNITO",
                                "AzureAD-Aplos",
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

        # Domain exists
        template.has_resource_properties(
            "AWS::Cognito::UserPoolDomain",
            {"Domain": "aplos-nca-test"},
        )

        # IdP exists
        template.has_resource_properties(
            "AWS::Cognito::UserPoolIdentityProvider",
            {
                "ProviderName": "AzureAD-Aplos",
                "ProviderType": "OIDC",
            },
        )

        # App client exists with OAuth and IdP references
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "ClientName": "web-client",
                "AllowedOAuthFlows": ["code"],
                "AllowedOAuthScopes": Match.array_with(["openid", "email", "profile"]),
                "CallbackURLs": Match.array_with(
                    ["https://app.example.com/", "http://localhost:5173/"]
                ),
                "SupportedIdentityProviders": Match.array_with(
                    ["COGNITO", "AzureAD-Aplos"]
                ),
            },
        )

    def test_backward_compatibility_no_domain_no_idp(
        self, app, deployment_config, workload_config
    ):
        """Test that existing configs without domain/IdP continue to work unchanged"""
        stack_config = self._create_stack_config(
            {
                "name": "test-cognito-stack",
                "cognito": {
                    "user_pool_name": "test-pool",
                    "app_clients": [
                        {
                            "name": "web-client",
                            "generate_secret": False,
                            "auth_flows": {"user_srp": True, "user_password": True},
                        }
                    ],
                },
            },
            workload_config,
        )

        stack = CognitoStack(app, "TestStack")
        stack.build(stack_config, deployment_config, workload_config)

        template = Template.from_stack(stack)

        # Pool and client created
        template.resource_count_is("AWS::Cognito::UserPool", 1)
        template.resource_count_is("AWS::Cognito::UserPoolClient", 1)

        # No domain or IdP
        template.resource_count_is("AWS::Cognito::UserPoolDomain", 0)
        template.resource_count_is("AWS::Cognito::UserPoolIdentityProvider", 0)
