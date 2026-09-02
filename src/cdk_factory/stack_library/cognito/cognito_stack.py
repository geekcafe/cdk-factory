"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from aws_lambda_powertools import Logger
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.cognito import CognitoConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig
from constructs import Construct

logger = Logger(__name__)


from cdk_factory.utilities.ssm_path_utils import (
    normalize_ssm_path as _normalize_ssm_path,
)


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
        self.user_pool: cognito.IUserPool | None = None
        self.app_clients: dict = {}  # Store created app clients by name
        # OIDC client secrets created by this stack (keyed by provider name).
        # Populated when an IdP opts into secret creation via
        # 'client_secret_secrets_manager_create'. Used to add a construct
        # dependency so the secret exists before the IdP references it.
        self._created_oidc_secrets: dict = {}

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

        # Resolve SSO config from environment (complex types can't pass through
        # the template engine's string substitution without mangling)
        self._resolve_sso_config_from_env()

        # Create or import user pool
        self._create_user_pool_with_config()

        # Add domain for Hosted UI / OAuth flows (must exist before IdPs for redirect URI)
        self._create_user_pool_domain()

        # Register external identity providers (must exist before app clients reference them)
        self._create_identity_providers()

        # Create app clients (may reference IdPs in supported_identity_providers)
        if self.cognito_config.app_clients:
            self._create_app_clients()

        # Export SSM parameters after all resources are created
        self._export_ssm_parameters(self.user_pool)

    def _is_sso_enabled(self) -> bool:
        """Master gate for all SSO / custom-domain / external-IdP setup.

        Controlled by the ``DEPLOY_SSO`` environment variable (set from the
        deployment config). This is an explicit, single switch so that emptying
        or half-populating individual SSO variables (e.g. blanking a client id
        while leaving ``SSO_AUTH_DOMAIN`` set) can never produce a broken,
        partially-configured provider or an orphaned custom domain.

        When disabled, the stack:
          - ignores ``SSO_IDENTITY_PROVIDERS`` (no external IdPs registered)
          - skips the custom-domain branch of the user-pool domain setup
          - strips any non-``COGNITO`` entries from an app client's
            ``supported_identity_providers``

        Resolution:
          - ``DEPLOY_SSO`` explicitly set → ``true``/``false`` honored.
          - ``DEPLOY_SSO`` unset → defaults to ``True`` to preserve the prior
            implicit behavior (build whatever SSO config is present). Callers
            that want SSO off must set ``DEPLOY_SSO=false``.

        Returns:
            bool: whether SSO-related resources should be created.
        """
        import os

        raw = os.environ.get("DEPLOY_SSO") or os.environ.get("SSO_DEPLOY_ENABLED")
        if raw is None or str(raw).strip() == "":
            # Unset → preserve legacy implicit behavior (enabled).
            return True
        return str(raw).strip().lower() == "true"

    def _resolve_sso_config_from_env(self):
        """Resolve SSO configuration from environment variables.

        Complex types (arrays, objects) cannot pass through the cdk-factory
        template engine's string substitution without being mangled. Instead,
        they are set as environment variables by the deployment config and
        read directly here at synth time.

        Environment variables:
            DEPLOY_SSO: Master gate (see ``_is_sso_enabled``). When not "true",
                SSO config is not resolved and no external IdPs are registered.
            SSO_IDENTITY_PROVIDERS: JSON array of IdP configs (or empty)
            SSO_SUPPORTED_IDENTITY_PROVIDERS: Comma-separated list (e.g., "COGNITO,AzureAD-CustomerX")
        """
        import json
        import os

        # Master gate: when SSO is disabled, do not resolve or inject any IdPs.
        if not self._is_sso_enabled():
            logger.info(
                "DEPLOY_SSO is not enabled — skipping SSO identity provider resolution."
            )
            return

        # Override identity_providers from env if the config has an empty/placeholder value
        idp_env = os.environ.get("SSO_IDENTITY_PROVIDERS", "")
        if idp_env and idp_env.strip():
            try:
                parsed = json.loads(idp_env) if isinstance(idp_env, str) else idp_env
                if isinstance(parsed, list) and parsed:
                    # Inject into the cognito config's underlying dict so
                    # CognitoConfig.identity_providers picks it up
                    cognito_dict = self.stack_config.dictionary.get("cognito", {})
                    cognito_dict["identity_providers"] = parsed
                    # Re-create config to pick up the override
                    self.cognito_config = CognitoConfig(cognito_dict)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "SSO_IDENTITY_PROVIDERS env var is not valid JSON — ignoring"
                )

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

    def _should_import_existing_pool(self) -> bool:
        """Determine whether to import an existing user pool or create a new one.

        Resolution order:
        1. Explicit ``use_existing`` flag (True/False) takes precedence.
        2. If not set, infer from ``user_pool_id``: non-empty → import, empty/missing → create.
        """
        use_existing = self.cognito_config.use_existing
        if use_existing is True:
            return True
        if use_existing is False:
            return False
        # Infer: if a pool ID is supplied, import it
        pool_id = self.cognito_config.user_pool_id
        return bool(pool_id and str(pool_id).strip())

    def _create_user_pool_with_config(self):
        if self._should_import_existing_pool():
            pool_id = self.cognito_config.user_pool_id
            if not pool_id or not str(pool_id).strip():
                raise ValueError(
                    "use_existing is true but no user_pool_id was provided. "
                    "Supply a valid user_pool_id to import an existing pool."
                )
            self.user_pool = cognito.UserPool.from_user_pool_id(
                self,
                id=self._build_resource_name(
                    self.cognito_config.user_pool_name or pool_id or "imported-pool"
                ),
                user_pool_id=pool_id,
            )
            logger.info(f"Imported existing Cognito User Pool: {pool_id}")
            return

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

    def _create_user_pool_domain(self):
        """Create a Cognito User Pool domain for the Hosted UI and OAuth flows.

        Supports two modes:
        - Prefix domain: Simple, no DNS needed. Creates {prefix}.auth.{region}.amazoncognito.com
        - Custom domain: Branded URL (e.g. auth.example.com). Requires ACM cert + Route53 records.
        """
        domain_config = self.cognito_config.domain
        if not domain_config or not isinstance(domain_config, dict):
            return

        if not self.user_pool:
            raise ValueError("User pool must be created before domain")

        if "prefix" in domain_config:
            # Simple prefix domain — no certificate or DNS needed
            domain = self.user_pool.add_domain(
                "CognitoDomain",
                cognito_domain=cognito.CognitoDomainOptions(
                    domain_prefix=domain_config["prefix"]
                ),
            )
            logger.info(
                f"Created Cognito prefix domain: "
                f"{domain_config['prefix']}.auth.{cdk.Stack.of(self).region}.amazoncognito.com"
            )

        elif "custom_domain" in domain_config:
            # Custom domain is part of the SSO/branded-auth surface. Skip entirely
            # when SSO is disabled, so a lingering SSO_AUTH_DOMAIN value can't
            # trigger a custom-domain (and its apex-A / cert dependency) on a
            # non-SSO deploy.
            if not self._is_sso_enabled():
                logger.info(
                    "DEPLOY_SSO is not enabled — skipping Cognito custom domain "
                    f"'{domain_config.get('custom_domain')}'."
                )
                return

            # Custom domain — requires ACM certificate (must be in us-east-1 for Cognito)
            from aws_cdk import aws_certificatemanager as acm
            from aws_cdk import aws_route53 as route53
            from aws_cdk import aws_route53_targets

            custom_domain_name = domain_config["custom_domain"]
            cert_arn = domain_config.get("certificate_arn")
            hosted_zone_name = domain_config.get("hosted_zone_name")
            hosted_zone_id = domain_config.get("hosted_zone_id")

            # Skip if custom_domain or cert_arn resolved to empty (template param not set)
            if not custom_domain_name or not custom_domain_name.strip():
                logger.info("Custom domain name is empty — skipping domain creation")
                return

            if not cert_arn or not cert_arn.strip():
                # Auto-create certificate via DNS validation (same pattern as API Gateway)
                if not hosted_zone_name:
                    raise ValueError(
                        "certificate_arn is empty and hosted_zone_name is required "
                        "to auto-create a certificate for the custom Cognito domain. "
                        "Either provide certificate_arn or hosted_zone_name for DNS validation."
                    )

                # Need hosted zone for DNS validation — resolve it now
                hz_id = hosted_zone_id
                if not hz_id:
                    ssm_imports = self.stack_config.ssm_config.get("imports", {})
                    route53_ns = ssm_imports.get("route53_namespace")
                    if route53_ns:
                        ssm_path = _normalize_ssm_path(f"/{route53_ns}/hosted-zone-id")
                        param = ssm.StringParameter.from_string_parameter_name(
                            self, "cognito-domain-hz-id-for-cert", ssm_path
                        )
                        hz_id = param.string_value

                if not hz_id:
                    raise ValueError(
                        "Cannot auto-create certificate: no hosted_zone_id available. "
                        "Provide certificate_arn, hosted_zone_id, or configure "
                        "ssm.imports.route53_namespace."
                    )

                validation_zone = route53.HostedZone.from_hosted_zone_attributes(
                    self,
                    "CognitoDomainCertValidationZone",
                    hosted_zone_id=hz_id,
                    zone_name=hosted_zone_name,
                )

                certificate = acm.Certificate(
                    self,
                    "CognitoDomainCert",
                    domain_name=custom_domain_name,
                    validation=acm.CertificateValidation.from_dns(validation_zone),
                )
                logger.info(
                    f"Auto-creating ACM certificate for '{custom_domain_name}' "
                    f"with DNS validation in zone '{hosted_zone_name}'"
                )
            else:
                certificate = acm.Certificate.from_certificate_arn(
                    self, "CognitoDomainCert", cert_arn
                )

            domain = self.user_pool.add_domain(
                "CognitoDomain",
                custom_domain=cognito.CustomDomainOptions(
                    domain_name=custom_domain_name,
                    certificate=certificate,
                ),
            )

            # Create Route53 alias records if hosted zone info is provided
            if hosted_zone_name:
                # Auto-discover hosted zone ID from SSM if not provided directly
                if not hosted_zone_id:
                    ssm_imports = self.stack_config.ssm_config.get("imports", {})
                    route53_ns = ssm_imports.get("route53_namespace")
                    if route53_ns:
                        ssm_path = _normalize_ssm_path(f"/{route53_ns}/hosted-zone-id")
                        param = ssm.StringParameter.from_string_parameter_name(
                            self, "cognito-domain-hosted-zone-id-param", ssm_path
                        )
                        hosted_zone_id = param.string_value

                if hosted_zone_id:
                    hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                        self,
                        "CognitoDomainHostedZone",
                        hosted_zone_id=hosted_zone_id,
                        zone_name=hosted_zone_name,
                    )

                    # Create A record pointing to the Cognito domain's CloudFront distribution
                    route53.ARecord(
                        self,
                        "CognitoDomainARecord",
                        zone=hosted_zone,
                        record_name=custom_domain_name,
                        target=route53.RecordTarget.from_alias(
                            aws_route53_targets.UserPoolDomainTarget(domain)
                        ),
                    )

                    # Create AAAA record for IPv6
                    route53.AaaaRecord(
                        self,
                        "CognitoDomainAAAARecord",
                        zone=hosted_zone,
                        record_name=custom_domain_name,
                        target=route53.RecordTarget.from_alias(
                            aws_route53_targets.UserPoolDomainTarget(domain)
                        ),
                    )

                    logger.info(
                        f"Created Cognito custom domain '{custom_domain_name}' "
                        f"with Route53 alias records in zone '{hosted_zone_name}'"
                    )
                else:
                    logger.warning(
                        f"Created Cognito custom domain '{custom_domain_name}' but could not "
                        f"create Route53 records — no hosted_zone_id available. "
                        f"Set hosted_zone_id in the domain config or configure "
                        f"ssm.imports.route53_namespace for auto-discovery."
                    )
            else:
                logger.info(
                    f"Created Cognito custom domain '{custom_domain_name}' "
                    f"(no Route53 records — hosted_zone_name not provided)"
                )

        # Store the domain reference for SSM export
        self._cognito_domain = domain_config.get(
            "custom_domain", domain_config.get("prefix")
        )

    def _create_identity_providers(self):
        """Register external identity providers (OIDC, SAML) on the user pool.

        Each identity provider is created as a child resource of the user pool.
        App clients that reference these providers in `supported_identity_providers`
        must be created AFTER this method runs.
        """
        if not self._is_sso_enabled():
            logger.info(
                "DEPLOY_SSO is not enabled — skipping external identity provider creation."
            )
            return

        providers_config = self.cognito_config.identity_providers
        if not providers_config or not isinstance(providers_config, list):
            return

        if not self.user_pool:
            raise ValueError("User pool must be created before identity providers")

        self._identity_provider_resources = {}

        for idp_config in providers_config:
            idp_name = idp_config.get("name")
            idp_type = idp_config.get("type", "").lower()

            if not idp_name:
                raise ValueError(
                    "Identity provider 'name' is required. "
                    "This name is referenced in app client 'supported_identity_providers'."
                )

            if idp_type == "oidc":
                provider = self._create_oidc_provider(
                    idp_name, idp_config.get("oidc", {})
                )
                self._identity_provider_resources[idp_name] = provider
            elif idp_type == "saml":
                logger.warning(
                    f"SAML identity provider '{idp_name}' configured but SAML support "
                    f"is not yet implemented. Skipping."
                )
            else:
                raise ValueError(
                    f"Unsupported identity provider type '{idp_type}' for '{idp_name}'. "
                    f"Supported types: 'oidc', 'saml'."
                )

    def _create_oidc_provider(
        self, name: str, oidc_config: dict
    ) -> cognito.UserPoolIdentityProviderOidc:
        """Create an OIDC identity provider (e.g., Azure AD, Google Workspace).

        Args:
            name: The provider name (e.g., 'AzureAD-CustomerX'). Must match the
                  value used in app client `supported_identity_providers`.
            oidc_config: OIDC-specific configuration dict.

        Returns:
            The created UserPoolIdentityProviderOidc construct.
        """
        client_id = oidc_config.get("client_id")
        if not client_id:
            raise ValueError(f"OIDC provider '{name}': 'client_id' is required")

        issuer_url = oidc_config.get("issuer_url")
        if not issuer_url:
            raise ValueError(f"OIDC provider '{name}': 'issuer_url' is required")

        # Resolve client secret (priority: plaintext > Secrets Manager > SSM)
        client_secret = self._resolve_oidc_client_secret(name, oidc_config)

        # Build attribute mapping
        attribute_mapping = self._build_oidc_attribute_mapping(
            oidc_config.get("attribute_mapping", {})
        )

        # Determine scopes
        scopes = oidc_config.get("scopes", ["openid", "profile", "email"])

        # Create the OIDC identity provider
        provider = cognito.UserPoolIdentityProviderOidc(
            self,
            id=self._build_resource_name(f"idp-{name}"),
            user_pool=self.user_pool,
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            issuer_url=issuer_url,
            scopes=scopes,
            attribute_request_method=cognito.OidcAttributeRequestMethod.GET,
            attribute_mapping=attribute_mapping,
        )

        # If this stack created the backing secret, ensure it exists before the
        # IdP resolves the {{resolve:secretsmanager}} reference at deploy time.
        created_secret = self._created_oidc_secrets.get(name)
        if created_secret is not None:
            provider.node.add_dependency(created_secret)

        logger.info(f"Created OIDC identity provider: {name} (issuer: {issuer_url})")
        return provider

    def _resolve_oidc_client_secret(self, provider_name: str, oidc_config: dict) -> str:
        """Resolve the OIDC client secret from one of three sources.

        Priority:
            1. client_secret — plain text (testing only)
            2. client_secret_secrets_manager — Secrets Manager secret name/ARN
            3. client_secret_ssm — SSM SecureString parameter path

        Returns:
            The resolved client secret string (may be a CloudFormation token).
        """
        # 1. Plain text (for dev/testing — NOT recommended for production)
        plain_secret = oidc_config.get("client_secret")
        if plain_secret:
            logger.warning(
                f"OIDC provider '{provider_name}': using plain-text client_secret. "
                f"Use 'client_secret_secrets_manager' or 'client_secret_ssm' in production."
            )
            return plain_secret

        # 2. Secrets Manager
        sm_ref = oidc_config.get("client_secret_secrets_manager")
        if sm_ref:
            # Opt-in: create the Secrets Manager secret as part of this stack
            # instead of expecting it to already exist. This makes the deploy
            # self-sufficient (no manual pre-provisioning) and avoids the
            # ResourceNotFoundException that occurs when the secret is missing.
            #
            # The secret is created with:
            #   - secret_name = sm_ref (so the IdP reference resolves to it)
            #   - an initial value from 'client_secret_value' (real or placeholder)
            #   - RemovalPolicy.RETAIN (never delete a credential on stack changes)
            #
            # NOTE: Cognito resolves this value at DEPLOY time and stores it on the
            # provider. Updating the secret value later (out-of-band) does NOT update
            # the IdP automatically — a redeploy of this stack is required to
            # re-resolve the reference. This is a Cognito/CloudFormation limitation.
            create_secret = (
                str(
                    oidc_config.get("client_secret_secrets_manager_create", False)
                ).lower()
                == "true"
            )

            if create_secret:
                created = self._create_oidc_client_secret(
                    provider_name, sm_ref, oidc_config
                )
                # Reference the created secret's value for the IdP. Using the
                # construct's secret_value keeps a construct-level relationship so
                # CDK understands the ordering; we also record the construct so
                # _create_oidc_provider can add an explicit dependency.
                self._created_oidc_secrets[provider_name] = created
                return created.secret_value.unsafe_unwrap()

            # Reference-only (default, unchanged): resolve an existing secret via a
            # CloudFormation dynamic reference {{resolve:secretsmanager:name}}.
            return cdk.SecretValue.secrets_manager(sm_ref).unsafe_unwrap()

        # 3. SSM SecureString
        ssm_path = oidc_config.get("client_secret_ssm")
        if ssm_path:
            return ssm.StringParameter.value_for_string_parameter(self, ssm_path)

        raise ValueError(
            f"OIDC provider '{provider_name}': No client secret configured. "
            f"Provide one of: 'client_secret', 'client_secret_secrets_manager', "
            f"or 'client_secret_ssm'."
        )

    # Placeholder used when an OIDC secret is created without an initial value.
    # It is intentionally recognizable so it is easy to spot an un-populated
    # credential in the console. Replace it with the real value out-of-band
    # (then redeploy this stack so Cognito re-resolves the reference).
    _OIDC_SECRET_PLACEHOLDER = "PLACEHOLDER_UPDATE_ME"

    def _create_oidc_client_secret(
        self, provider_name: str, secret_name: str, oidc_config: dict
    ) -> secretsmanager.Secret:
        """Create the Secrets Manager secret backing an OIDC client secret.

        Opt-in via ``client_secret_secrets_manager_create: true`` on the OIDC
        config. The secret is created at ``secret_name`` (the same path the IdP
        references) with an initial value taken from ``client_secret_value`` when
        provided, otherwise a recognizable placeholder.

        The secret is created with ``RemovalPolicy.RETAIN`` so it is never deleted
        when the stack is updated or a resource is replaced — a client credential
        should outlive stack churn.

        Args:
            provider_name: The IdP name (used only for construct IDs / logging).
            secret_name: The Secrets Manager secret name (matches the IdP reference).
            oidc_config: The OIDC config dict (source of ``client_secret_value``).

        Returns:
            The created ``secretsmanager.Secret`` construct.
        """
        initial_value = oidc_config.get("client_secret_value")
        used_placeholder = False
        if initial_value is None or str(initial_value).strip() == "":
            initial_value = self._OIDC_SECRET_PLACEHOLDER
            used_placeholder = True

        secret = secretsmanager.Secret(
            self,
            self._build_resource_name(f"oidc-secret-{provider_name}"),
            secret_name=secret_name,
            description=(
                f"OIDC client secret for identity provider '{provider_name}'. "
                f"Managed by the Cognito stack."
            ),
            secret_string_value=cdk.SecretValue.unsafe_plain_text(str(initial_value)),
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        if used_placeholder:
            logger.warning(
                f"OIDC provider '{provider_name}': created Secrets Manager secret "
                f"'{secret_name}' with a PLACEHOLDER value. Update it with the real "
                f"client secret, then redeploy this stack so Cognito picks it up."
            )
        else:
            logger.info(
                f"OIDC provider '{provider_name}': created Secrets Manager secret "
                f"'{secret_name}' with a provided initial value."
            )

        return secret

    def _build_oidc_attribute_mapping(
        self, mapping_config: dict
    ) -> cognito.AttributeMapping:
        """Build a Cognito AttributeMapping from the config dict.

        Maps OIDC token claim names to Cognito user pool attributes.
        Standard mappings (email, given_name, family_name) are handled specially.
        Custom mappings use ProviderAttribute.other().
        """
        if not mapping_config:
            # Default mapping for Azure AD / standard OIDC providers
            return cognito.AttributeMapping(
                email=cognito.ProviderAttribute.other("email"),
                given_name=cognito.ProviderAttribute.other("given_name"),
                family_name=cognito.ProviderAttribute.other("family_name"),
            )

        kwargs = {}
        custom = {}

        # Standard Cognito attribute mappings
        standard_map = {
            "email": "email",
            "given_name": "given_name",
            "family_name": "family_name",
            "name": "name",
            "phone_number": "phone_number",
            "preferred_username": "preferred_username",
            "birthdate": "birthdate",
            "gender": "gender",
            "locale": "locale",
            "nickname": "nickname",
            "picture": "picture",
            "profile_page": "profile_page",
            "website": "website",
        }

        for cognito_attr, oidc_claim in mapping_config.items():
            if cognito_attr in standard_map:
                kwargs[cognito_attr] = cognito.ProviderAttribute.other(oidc_claim)
            else:
                # Custom attribute mapping
                custom[cognito_attr] = cognito.ProviderAttribute.other(oidc_claim)

        if custom:
            kwargs["custom"] = custom

        return cognito.AttributeMapping(**kwargs)

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
                "supported_identity_providers": self._build_identity_providers_with_dependencies(
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

            # Validate ssm_namespace early — raise on empty/whitespace strings
            client_ssm_ns = client_config.get("ssm_namespace")
            if client_ssm_ns is not None and not client_ssm_ns.strip():
                raise ValueError(
                    f"App client '{client_name}': "
                    f"'ssm_namespace' must be a non-empty string or omitted entirely."
                )

            # Warn if client has ssm_namespace but auto_export is disabled
            # and no explicit exports are configured
            if (
                client_config.get("ssm_namespace")
                and not self.stack_config.ssm_auto_export
                and not self.stack_config.ssm_config.get("exports", {})
            ):
                logger.warning(
                    f"App client '{client_name}' has 'ssm_namespace' configured but "
                    f"ssm.auto_export is disabled and no explicit exports are configured. "
                    f"The client-level namespace will be ignored."
                )

            # Store client secret in Secrets Manager if generated
            if client_config.get("generate_secret", False):
                self._store_client_secret_in_secrets_manager(
                    client_name, app_client, self.user_pool, client_config
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

    def _build_identity_providers(self, providers) -> list:
        """Build identity provider list from configuration.

        Handles:
        - Native list: ["COGNITO", "AzureAD-CustomerX"]
        - JSON-encoded string: '["COGNITO", "AzureAD-CustomerX"]'
        - Comma-separated string: "COGNITO,AzureAD-CustomerX"
        """
        if isinstance(providers, str):
            providers = providers.strip()
            if not providers:
                return None
            # Try JSON parse first (handles '["COGNITO"]' format)
            if providers.startswith("["):
                try:
                    import json

                    providers = json.loads(providers)
                except (json.JSONDecodeError, TypeError):
                    return None
            else:
                # Comma-separated string: "COGNITO,AzureAD-CustomerX"
                providers = [p.strip() for p in providers.split(",") if p.strip()]

        if not providers or not isinstance(providers, list):
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

    def _build_identity_providers_with_dependencies(self, providers) -> list:
        """Build identity provider list, using CDK construct references for proper ordering.

        For providers that are being created in this same stack (registered in
        self._identity_provider_resources), uses the construct's provider_name token
        instead of a raw string. This creates an implicit CloudFormation dependency,
        ensuring the IdP resource is fully created before the app client references it.

        This solves the first-deploy ordering problem where CF would try to update the
        app client with a provider that doesn't exist yet.
        """
        # When SSO is disabled, an app client must not reference any external IdP
        # (those IdPs are not created). Collapse to COGNITO-only so the client is
        # still valid. If the config listed only external providers, fall back to
        # the CDK default (None → COGNITO).
        if not self._is_sso_enabled():
            raw_names = self._get_raw_provider_names(providers)
            if any(name.upper() != "COGNITO" for name in raw_names if name):
                logger.info(
                    "DEPLOY_SSO is not enabled — restricting app client "
                    "supported_identity_providers to COGNITO."
                )
            providers = "COGNITO" if raw_names else providers

        # Parse the raw providers value (handles string, JSON, comma-separated)
        parsed = self._build_identity_providers(providers)
        if not parsed:
            return None

        # If no custom IdPs were created in this stack, return as-is
        if (
            not hasattr(self, "_identity_provider_resources")
            or not self._identity_provider_resources
        ):
            return parsed

        # Rebuild the list, substituting CDK construct references for custom providers
        # that were created in this stack. This forces CF dependency ordering.
        result = []
        # Re-parse the raw provider names to check against our registry
        raw_names = self._get_raw_provider_names(providers)

        for i, cdk_provider in enumerate(parsed):
            raw_name = raw_names[i] if i < len(raw_names) else None
            if raw_name and raw_name in self._identity_provider_resources:
                # Use the construct reference — CDK will create DependsOn automatically
                idp_construct = self._identity_provider_resources[raw_name]
                result.append(
                    cognito.UserPoolClientIdentityProvider.custom(
                        idp_construct.provider_name
                    )
                )
            else:
                result.append(cdk_provider)

        return result if result else None

    def _get_raw_provider_names(self, providers) -> list:
        """Extract raw string provider names from the input (before CDK enum mapping)."""
        if isinstance(providers, str):
            providers = providers.strip()
            if not providers:
                return []
            if providers.startswith("["):
                try:
                    import json

                    providers = json.loads(providers)
                except (json.JSONDecodeError, TypeError):
                    return []
            else:
                providers = [p.strip() for p in providers.split(",") if p.strip()]
        if not providers or not isinstance(providers, list):
            return []
        return [p if isinstance(p, str) else "" for p in providers]

    def _store_client_secret_in_secrets_manager(
        self,
        client_name: str,
        app_client: cognito.UserPoolClient,
        user_pool: cognito.IUserPool,
        client_config: dict,
    ):
        """
        Store Cognito app client secret in AWS Secrets Manager.
        Uses a custom resource to retrieve the secret from Cognito API.
        """
        # Create a custom resource to retrieve the client secret
        # This is necessary because CDK doesn't expose the client secret.
        # Both on_create and on_update are needed so the secret is retrieved
        # on initial deployment AND on subsequent stack updates.
        sdk_call = cr.AwsSdkCall(
            service="CognitoIdentityServiceProvider",
            action="describeUserPoolClient",
            parameters={
                "UserPoolId": user_pool.user_pool_id,
                "ClientId": app_client.user_pool_client_id,
            },
            physical_resource_id=cr.PhysicalResourceId.of(
                f"{client_name}-secret-{app_client.user_pool_client_id}"
            ),
        )
        get_client_secret = cr.AwsCustomResource(
            self,
            f"{client_name}-secret-retriever",
            on_create=sdk_call,
            on_update=sdk_call,
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["cognito-idp:DescribeUserPoolClient"],
                        resources=[user_pool.user_pool_arn],
                    )
                ]
            ),
        )

        # Ensure the app client is fully created before the custom resource
        # tries to describe it. Without this, CloudFormation may execute the
        # describeUserPoolClient call before the client exists, resulting in
        # a missing ClientSecret attribute error.
        get_client_secret.node.add_dependency(app_client)

        # Get the client secret from the custom resource response
        client_secret = get_client_secret.get_response_field(
            "UserPoolClient.ClientSecret"
        )

        # Resolve the secret name using the client's namespace if available
        namespace = self._resolve_client_namespace(client_config)
        if namespace:
            secret_name = f"{namespace}/credentials"
        else:
            secret_name = self._build_resource_name(
                f"cognito/{client_name}/credentials"
            )

        # Store all client credentials in a single secret
        secret_with_metadata = secretsmanager.Secret(
            self,
            f"{client_name}-client-credentials",
            secret_name=secret_name,
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
        ssm_config = self.stack_config.ssm_config
        if ssm_config.get("auto_export"):
            namespace = self._resolve_client_namespace(client_config)
            if namespace:
                client_has_own_namespace = (
                    client_config.get("ssm_namespace") is not None
                )

                if client_has_own_namespace:
                    secret_key = "secret-arn"
                else:
                    safe_client_name = client_name.replace(" ", "-")
                    secret_key = f"app-client-{safe_client_name}-secret-arn"

                ssm.StringParameter(
                    self,
                    f"{client_name}-secret-arn-param",
                    parameter_name=f"/{namespace}/{secret_key}",
                    string_value=secret_with_metadata.secret_arn,
                    description=f"Secrets Manager ARN for {client_name} credentials",
                )

    def _resolve_client_namespace(self, client_config: dict) -> str:
        """
        Resolve the effective SSM namespace for an app client.
        Returns client-level namespace if specified, otherwise pool-level namespace.
        Raises ValueError if client namespace is an empty string.
        """
        client_ns = client_config.get("ssm_namespace")
        if client_ns is not None:
            if not client_ns.strip():
                raise ValueError(
                    f"App client '{client_config.get('name')}': "
                    f"'ssm_namespace' must be a non-empty string or omitted entirely."
                )
            return client_ns
        return self.stack_config.ssm_namespace

    def _export_ssm_parameters(self, user_pool: cognito.IUserPool):
        """Export Cognito resources to SSM using top-level ssm config"""

        ssm_config = self.stack_config.ssm_config
        exports = ssm_config.get("exports", {})
        auto_export = self.stack_config.ssm_auto_export

        if not ssm_config or (not auto_export and not exports):
            logger.info("No SSM parameters configured for export")
            return

        # Setup SSM integration using the top-level ssm block via stack_config
        self.setup_ssm_integration(
            scope=self,
            config=self.stack_config.dictionary,
            resource_type="cognito",
            resource_name="user-pool",
        )

        # Prepare pool-level resource values for export (use dashes for consistency)
        pool_resource_values = {
            "user-pool-id": user_pool.user_pool_id,
            "user-pool-name": self.cognito_config.user_pool_name,
            "user-pool-arn": user_pool.user_pool_arn,
        }

        # Include domain in exports if configured
        if hasattr(self, "_cognito_domain") and self._cognito_domain:
            domain_config = self.cognito_config.domain or {}
            if "custom_domain" in domain_config:
                pool_resource_values["domain"] = domain_config["custom_domain"]
            elif "prefix" in domain_config:
                pool_resource_values["domain"] = (
                    f"{domain_config['prefix']}.auth.{cdk.Stack.of(self).region}.amazoncognito.com"
                )

        if auto_export:
            # Path pattern: /{namespace}/{attribute}
            # The namespace in config should include the resource context,
            # e.g. "acme-saas/beta/cognito"
            namespace = self.stack_config.ssm_namespace
            if not namespace:
                raise ValueError(
                    f"Stack '{self.stack_config.name}': "
                    f"'ssm.namespace' is required when 'ssm.auto_export' is true. "
                    f"Add 'ssm.namespace' to your stack config."
                )

            # Export pool-level parameters under the pool namespace
            pool_prefix = f"/{namespace}"
            exported_count = 0

            for export_key, export_value in pool_resource_values.items():
                if export_value is None:
                    continue
                parameter_path = f"{pool_prefix}/{export_key}"
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.id}-{export_key}",
                    value=export_value,
                    parameter_name=parameter_path,
                    description=f"Cognito {export_key}",
                )
                exported_count += 1

            # Export app client parameters under per-client namespaces
            for client_config in self.cognito_config.app_clients:
                client_name = client_config.get("name")
                if not client_name or client_name not in self.app_clients:
                    continue

                app_client = self.app_clients[client_name]
                client_has_own_namespace = (
                    client_config.get("ssm_namespace") is not None
                )
                client_namespace = self._resolve_client_namespace(client_config)
                client_prefix = f"/{client_namespace}"

                if client_has_own_namespace:
                    # Client has its own namespace — use simple key names
                    export_key = "client-id"
                else:
                    # Fallback to pool namespace — include client name in key
                    safe_client_name = client_name.replace(" ", "-")
                    export_key = f"app-client-{safe_client_name}-id"

                parameter_path = f"{client_prefix}/{export_key}"
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.id}-{client_name}-{export_key}",
                    value=app_client.user_pool_client_id,
                    parameter_name=parameter_path,
                    description=f"Cognito {export_key}",
                )
                exported_count += 1

            logger.info(f"Auto-exported {exported_count} Cognito parameters to SSM")
        else:
            # Use explicit exports mapping — combine pool + client values
            resource_values = dict(pool_resource_values)
            for client_name, app_client in self.app_clients.items():
                safe_client_name = client_name.replace(" ", "-")
                resource_values[f"app-client-{safe_client_name}-id"] = (
                    app_client.user_pool_client_id
                )
            exported_params = self.export_ssm_parameters(resource_values)
            if exported_params:
                logger.info(
                    f"Exported {len(exported_params)} Cognito parameters to SSM"
                )
            else:
                logger.info("No SSM exports configured")
