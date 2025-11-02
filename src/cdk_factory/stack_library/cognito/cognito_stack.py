"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import custom_resources as cr
from constructs import Construct
from aws_lambda_powertools import Logger
from aws_cdk import aws_ssm as ssm
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.cognito import CognitoConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("cognito_library_module")
@register_stack("cognito_stack")
class CognitoStack(IStack, StandardizedSsmMixin):
    """
    Cognito Stack - Creates a Cognito User Pool with configurable settings.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.id = id
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.cognito_config: CognitoConfig | None = None
        self.user_pool: cognito.UserPool | None = None
        self.app_clients: dict = {}  # Store created app clients by name

    def _build_resource_name(self, name: str) -> str:
        """Build resource name using deployment configuration"""
        if self.deployment:
            return self.deployment.build_resource_name(name)
        else:
            # Fallback naming pattern
            return f"{self.cognito_config.user_pool_name or 'cognito'}-{name}"

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.cognito_config = CognitoConfig(stack_config.dictionary.get("cognito", {}))

        # Create user pool with configuration
        self._create_user_pool_with_config()

        # Create app clients if configured
        if self.cognito_config.app_clients:
            self._create_app_clients()

    def _setup_custom_attributes(self):
        attributes = {}
        if self.cognito_config.custom_attributes:
            for custom_attribute in self.cognito_config.custom_attributes:
                if not custom_attribute.get("name"):
                    raise ValueError("Custom attribute name is required")
                name = custom_attribute.get("name")
                if "custom:" in name:
                    name = name.replace("custom:", "")

                # Use StringAttribute for custom attributes (most common type)
                # In a more complete implementation, we could support different attribute types
                # based on a 'type' field in the custom_attribute dict
                attributes[name] = cognito.StringAttribute(
                    mutable=custom_attribute.get("mutable", True),
                    max_len=custom_attribute.get("max_length", None),
                    min_len=custom_attribute.get("min_length", None),
                )
        return attributes

    def _create_user_pool_with_config(self):
        # Build kwargs for all supported Cognito UserPool parameters
        kwargs = {
            "user_pool_name": self.cognito_config.user_pool_name,
            "self_sign_up_enabled": self.cognito_config.self_sign_up_enabled,
            "sign_in_case_sensitive": self.cognito_config.sign_in_case_sensitive,
            "sign_in_aliases": (
                cognito.SignInAliases(**self.cognito_config.sign_in_aliases)
                if self.cognito_config.sign_in_aliases
                else None
            ),
            "sign_in_policy": self.cognito_config.sign_in_policy,
            "auto_verify": (
                cognito.AutoVerifiedAttrs(**self.cognito_config.auto_verify)
                if self.cognito_config.auto_verify
                else None
            ),
            "custom_attributes": self._setup_custom_attributes(),
            "custom_sender_kms_key": self.cognito_config.custom_sender_kms_key,
            "custom_threat_protection_mode": self.cognito_config.custom_threat_protection_mode,
            "deletion_protection": self.cognito_config.deletion_protection,
            "device_tracking": self.cognito_config.device_tracking,
            "email": self.cognito_config.email,
            "enable_sms_role": self.cognito_config.enable_sms_role,
            "feature_plan": self.cognito_config.feature_plan,
            "keep_original": self.cognito_config.keep_original,
            "lambda_triggers": self.cognito_config.lambda_triggers,
            "mfa": (
                cognito.Mfa[self.cognito_config.mfa]
                if self.cognito_config.mfa
                else None
            ),
            "mfa_message": self.cognito_config.mfa_message,
            "mfa_second_factor": (
                cognito.MfaSecondFactor(**self.cognito_config.mfa_second_factor)
                if self.cognito_config.mfa_second_factor
                else None
            ),
            "passkey_relying_party_id": self.cognito_config.passkey_relying_party_id,
            "passkey_user_verification": self.cognito_config.passkey_user_verification,
            "password_policy": (
                cognito.PasswordPolicy(**self.cognito_config.password_policy)
                if self.cognito_config.password_policy
                else None
            ),
            "removal_policy": (
                cdk.RemovalPolicy[self.cognito_config.removal_policy]
                if self.cognito_config.removal_policy
                else None
            ),
            "account_recovery": (
                cognito.AccountRecovery[self.cognito_config.account_recovery]
                if self.cognito_config.account_recovery
                else None
            ),
            "sms_role": self.cognito_config.sms_role,
            "sms_role_external_id": self.cognito_config.sms_role_external_id,
            "sns_region": self.cognito_config.sns_region,
            "standard_attributes": self.cognito_config.standard_attributes,
            "standard_threat_protection_mode": self.cognito_config.standard_threat_protection_mode,
            "user_invitation": self.cognito_config.user_invitation,
            "user_verification": self.cognito_config.user_verification,
            "advanced_security_mode": (
                cognito.AdvancedSecurityMode[self.cognito_config.advanced_security_mode]
                if self.cognito_config.advanced_security_mode
                else None
            ),
        }
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        self.user_pool = cognito.UserPool(
            self,
            id=self._build_resource_name(
                self.cognito_config.user_pool_name
                or self.cognito_config.user_pool_id
                or "user-pool"
            ),
            **kwargs,
        )
        logger.info(f"Created Cognito User Pool: {self.user_pool.user_pool_id}")

        self._export_ssm_parameters(self.user_pool)

    def _create_app_clients(self):
        """Create app clients for the user pool based on configuration"""
        if not self.user_pool:
            raise ValueError("User pool must be created before app clients")

        for client_config in self.cognito_config.app_clients:
            client_name = client_config.get("name")
            if not client_name:
                raise ValueError("App client name is required")

            # Build authentication flows
            auth_flows = self._build_auth_flows(client_config.get("auth_flows", {}))

            # Build OAuth settings
            oauth_settings = self._build_oauth_settings(client_config.get("oauth"))

            # Build token validity settings
            token_validity = self._build_token_validity(client_config)

            # Build app client kwargs
            client_kwargs = {
                "user_pool": self.user_pool,
                "user_pool_client_name": client_name,
                "generate_secret": client_config.get("generate_secret", False),
                "auth_flows": auth_flows,
                "o_auth": oauth_settings,
                "prevent_user_existence_errors": client_config.get(
                    "prevent_user_existence_errors"
                ),
                "enable_token_revocation": client_config.get(
                    "enable_token_revocation", True
                ),
                "access_token_validity": token_validity.get("access_token"),
                "id_token_validity": token_validity.get("id_token"),
                "refresh_token_validity": token_validity.get("refresh_token"),
                "read_attributes": self._build_attributes(
                    client_config.get("read_attributes")
                ),
                "write_attributes": self._build_attributes(
                    client_config.get("write_attributes")
                ),
                "supported_identity_providers": self._build_identity_providers(
                    client_config.get("supported_identity_providers")
                ),
            }

            # Remove None values
            client_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}

            # Create the app client
            app_client = cognito.UserPoolClient(
                self,
                id=self._build_resource_name(f"{client_name}-client"),
                **client_kwargs,
            )

            # Store reference
            self.app_clients[client_name] = app_client
            logger.info(f"Created Cognito App Client: {client_name}")

            # Store client secret in Secrets Manager if generated
            if client_config.get("generate_secret", False):
                self._store_client_secret_in_secrets_manager(
                    client_name, app_client, self.user_pool
                )

    def _build_auth_flows(self, auth_flows_config: dict) -> cognito.AuthFlow:
        """
        Build authentication flows from configuration.

        Note: CDK automatically adds ALLOW_REFRESH_TOKEN_AUTH to all app clients,
        which is required for token refresh functionality.
        """
        if not auth_flows_config:
            return None

        return cognito.AuthFlow(
            user_password=auth_flows_config.get("user_password", False),
            user_srp=auth_flows_config.get("user_srp", False),
            custom=auth_flows_config.get("custom", False),
            admin_user_password=auth_flows_config.get("admin_user_password", False),
        )

    def _build_oauth_settings(self, oauth_config: dict) -> cognito.OAuthSettings:
        """Build OAuth settings from configuration"""
        if not oauth_config:
            return None

        # Build OAuth flows
        flows_config = oauth_config.get("flows", {})
        flows = cognito.OAuthFlows(
            authorization_code_grant=flows_config.get(
                "authorization_code_grant", False
            ),
            implicit_code_grant=flows_config.get("implicit_code_grant", False),
            client_credentials=flows_config.get("client_credentials", False),
        )

        # Build OAuth scopes
        scopes = []
        scope_list = oauth_config.get("scopes", [])
        for scope in scope_list:
            if scope.lower() == "openid":
                scopes.append(cognito.OAuthScope.OPENID)
            elif scope.lower() == "email":
                scopes.append(cognito.OAuthScope.EMAIL)
            elif scope.lower() == "phone":
                scopes.append(cognito.OAuthScope.PHONE)
            elif scope.lower() == "profile":
                scopes.append(cognito.OAuthScope.PROFILE)
            elif scope.lower() == "cognito_admin":
                scopes.append(cognito.OAuthScope.COGNITO_ADMIN)
            else:
                # Custom scope
                scopes.append(cognito.OAuthScope.custom(scope))

        return cognito.OAuthSettings(
            flows=flows,
            scopes=scopes if scopes else None,
            callback_urls=oauth_config.get("callback_urls"),
            logout_urls=oauth_config.get("logout_urls"),
        )

    def _build_token_validity(self, client_config: dict) -> dict:
        """Build token validity settings from configuration"""
        result = {}

        # Access token validity
        if "access_token_validity" in client_config:
            validity = client_config["access_token_validity"]
            if "minutes" in validity:
                result["access_token"] = cdk.Duration.minutes(validity["minutes"])
            elif "hours" in validity:
                result["access_token"] = cdk.Duration.hours(validity["hours"])
            elif "days" in validity:
                result["access_token"] = cdk.Duration.days(validity["days"])

        # ID token validity
        if "id_token_validity" in client_config:
            validity = client_config["id_token_validity"]
            if "minutes" in validity:
                result["id_token"] = cdk.Duration.minutes(validity["minutes"])
            elif "hours" in validity:
                result["id_token"] = cdk.Duration.hours(validity["hours"])
            elif "days" in validity:
                result["id_token"] = cdk.Duration.days(validity["days"])

        # Refresh token validity
        if "refresh_token_validity" in client_config:
            validity = client_config["refresh_token_validity"]
            if "minutes" in validity:
                result["refresh_token"] = cdk.Duration.minutes(validity["minutes"])
            elif "hours" in validity:
                result["refresh_token"] = cdk.Duration.hours(validity["hours"])
            elif "days" in validity:
                result["refresh_token"] = cdk.Duration.days(validity["days"])

        return result

    def _build_attributes(self, attribute_list: list) -> cognito.ClientAttributes:
        """Build client attributes from configuration"""
        if not attribute_list:
            return None

        # Standard attributes mapping
        standard_attrs = {
            "address": lambda: cognito.ClientAttributes().with_standard_attributes(
                address=True
            ),
            "birthdate": lambda: cognito.ClientAttributes().with_standard_attributes(
                birthdate=True
            ),
            "email": lambda: cognito.ClientAttributes().with_standard_attributes(
                email=True
            ),
            "email_verified": lambda: cognito.ClientAttributes().with_standard_attributes(
                email_verified=True
            ),
            "family_name": lambda: cognito.ClientAttributes().with_standard_attributes(
                family_name=True
            ),
            "gender": lambda: cognito.ClientAttributes().with_standard_attributes(
                gender=True
            ),
            "given_name": lambda: cognito.ClientAttributes().with_standard_attributes(
                given_name=True
            ),
            "locale": lambda: cognito.ClientAttributes().with_standard_attributes(
                locale=True
            ),
            "middle_name": lambda: cognito.ClientAttributes().with_standard_attributes(
                middle_name=True
            ),
            "name": lambda: cognito.ClientAttributes().with_standard_attributes(
                fullname=True
            ),
            "nickname": lambda: cognito.ClientAttributes().with_standard_attributes(
                nickname=True
            ),
            "phone_number": lambda: cognito.ClientAttributes().with_standard_attributes(
                phone_number=True
            ),
            "phone_number_verified": lambda: cognito.ClientAttributes().with_standard_attributes(
                phone_number_verified=True
            ),
            "picture": lambda: cognito.ClientAttributes().with_standard_attributes(
                picture=True
            ),
            "preferred_username": lambda: cognito.ClientAttributes().with_standard_attributes(
                preferred_username=True
            ),
            "profile": lambda: cognito.ClientAttributes().with_standard_attributes(
                profile=True
            ),
            "timezone": lambda: cognito.ClientAttributes().with_standard_attributes(
                timezone=True
            ),
            "updated_at": lambda: cognito.ClientAttributes().with_standard_attributes(
                last_update_time=True
            ),
            "website": lambda: cognito.ClientAttributes().with_standard_attributes(
                website=True
            ),
        }

        # Start with empty attributes
        attrs = cognito.ClientAttributes()

        # Build standard attributes
        standard_dict = {}
        custom_list = []

        for attr in attribute_list:
            if attr in standard_attrs:
                standard_dict[attr] = True
            else:
                # Custom attribute
                custom_list.append(attr)

        # Apply standard attributes if any
        if standard_dict:
            # Map attribute names to CDK parameter names
            attr_mapping = {
                "address": "address",
                "birthdate": "birthdate",
                "email": "email",
                "email_verified": "email_verified",
                "family_name": "family_name",
                "gender": "gender",
                "given_name": "given_name",
                "locale": "locale",
                "middle_name": "middle_name",
                "name": "fullname",
                "nickname": "nickname",
                "phone_number": "phone_number",
                "phone_number_verified": "phone_number_verified",
                "picture": "picture",
                "preferred_username": "preferred_username",
                "profile": "profile",
                "timezone": "timezone",
                "updated_at": "last_update_time",
                "website": "website",
            }

            # Convert to CDK parameter names
            cdk_attrs = {attr_mapping.get(k, k): v for k, v in standard_dict.items()}
            attrs = attrs.with_standard_attributes(**cdk_attrs)

        # Add custom attributes if any
        if custom_list:
            attrs = attrs.with_custom_attributes(*custom_list)

        return attrs

    def _build_identity_providers(self, providers: list) -> list:
        """Build identity provider list from configuration"""
        if not providers:
            return None

        result = []
        for provider in providers:
            if isinstance(provider, str):
                if provider.upper() == "COGNITO":
                    result.append(cognito.UserPoolClientIdentityProvider.COGNITO)
                elif provider.upper() == "GOOGLE":
                    result.append(cognito.UserPoolClientIdentityProvider.GOOGLE)
                elif provider.upper() == "FACEBOOK":
                    result.append(cognito.UserPoolClientIdentityProvider.FACEBOOK)
                elif provider.upper() == "AMAZON":
                    result.append(cognito.UserPoolClientIdentityProvider.AMAZON)
                elif provider.upper() == "APPLE":
                    result.append(cognito.UserPoolClientIdentityProvider.APPLE)
                else:
                    # Custom provider
                    result.append(
                        cognito.UserPoolClientIdentityProvider.custom(provider)
                    )

        return result if result else None

    def _store_client_secret_in_secrets_manager(
        self,
        client_name: str,
        app_client: cognito.UserPoolClient,
        user_pool: cognito.UserPool,
    ):
        """
        Store Cognito app client secret in AWS Secrets Manager.
        Uses a custom resource to retrieve the secret from Cognito API.
        """
        # Create a custom resource to retrieve the client secret
        # This is necessary because CDK doesn't expose the client secret
        get_client_secret = cr.AwsCustomResource(
            self,
            f"{client_name}-secret-retriever",
            on_create=cr.AwsSdkCall(
                service="CognitoIdentityServiceProvider",
                action="describeUserPoolClient",
                parameters={
                    "UserPoolId": user_pool.user_pool_id,
                    "ClientId": app_client.user_pool_client_id,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"{client_name}-secret-{app_client.user_pool_client_id}"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["cognito-idp:DescribeUserPoolClient"],
                        resources=[user_pool.user_pool_arn],
                    )
                ]
            ),
        )

        # Get the client secret from the custom resource response
        client_secret = get_client_secret.get_response_field(
            "UserPoolClient.ClientSecret"
        )

        # Create secret in Secrets Manager
        secret = secretsmanager.Secret(
            self,
            f"{client_name}-client-secret",
            secret_name=self._build_resource_name(
                f"cognito/{client_name}/client-secret"
            ),
            description=f"Cognito app client secret for {client_name}",
            secret_string_value=cdk.SecretValue.unsafe_plain_text(client_secret),
        )

        # Also store client ID in the same secret for convenience
        secret_with_metadata = secretsmanager.Secret(
            self,
            f"{client_name}-client-credentials",
            secret_name=self._build_resource_name(f"cognito/{client_name}/credentials"),
            description=f"Cognito app client credentials for {client_name}",
            secret_object_value={
                "client_id": cdk.SecretValue.unsafe_plain_text(
                    app_client.user_pool_client_id
                ),
                "client_secret": cdk.SecretValue.unsafe_plain_text(client_secret),
                "user_pool_id": cdk.SecretValue.unsafe_plain_text(
                    user_pool.user_pool_id
                ),
            },
        )

        logger.info(
            f"Stored client secret for {client_name} in Secrets Manager: "
            f"{secret_with_metadata.secret_name}"
        )

        # Export secret ARN to SSM for cross-stack reference
        if self.cognito_config.ssm.get("enabled"):
            safe_client_name = client_name.replace("-", "_").replace(" ", "_")
            org = self.cognito_config.ssm.get("organization", "default")
            env = self.cognito_config.ssm.get("environment", "dev")

            ssm.StringParameter(
                self,
                f"{client_name}-secret-arn-param",
                parameter_name=f"/{org}/{env}/cognito/user-pool/app_client_{safe_client_name}_secret_arn",
                string_value=secret_with_metadata.secret_arn,
                description=f"Secrets Manager ARN for {client_name} credentials",
            )

    def _export_ssm_parameters(self, user_pool: cognito.UserPool):
        """Export Cognito resources to SSM using enhanced SSM parameter mixin"""

        # Setup enhanced SSM integration with proper resource type and name
        # Use "user-pool" as resource identifier for SSM paths, not the full pool name

        self.setup_ssm_integration(
            scope=self,
            config=self.stack_config.dictionary.get("cognito", {}),
            resource_type="cognito",
            resource_name="user-pool",
        )

        # Prepare resource values for export
        resource_values = {
            "user_pool_id": user_pool.user_pool_id,
            "user_pool_name": self.cognito_config.user_pool_name,
            "user_pool_arn": user_pool.user_pool_arn,
        }

        # Add app client IDs to export
        for client_name, app_client in self.app_clients.items():
            # Export client ID
            safe_client_name = client_name.replace("-", "_").replace(" ", "_")
            resource_values[f"app_client_{safe_client_name}_id"] = (
                app_client.user_pool_client_id
            )

            # Note: Client secrets cannot be exported via SSM as they are only available
            # at creation time and CDK doesn't expose them. Use AWS Secrets Manager
            # or retrieve via AWS Console/CLI if needed.

        # Use enhanced SSM parameter export
        exported_params = self.export_ssm_parameters(resource_values)

        if exported_params:
            logger.info(f"Exported {len(exported_params)} Cognito parameters to SSM")
        else:
            logger.info("No SSM parameters configured for export")
