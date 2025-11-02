"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk as cdk
from aws_cdk import aws_rum as rum
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from constructs import Construct
from aws_lambda_powertools import Logger
from typing import Optional

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.rum import RumConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("rum_library_module")
@register_stack("rum_stack")
class RumStack(IStack, StandardizedSsmMixin):
    """
    RUM Stack - Creates a CloudWatch RUM app monitor with optional Cognito integration.
    Can either use existing Cognito resources or create new ones if not provided.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.id = id
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.rum_config: Optional[RumConfig] = None
        self.app_monitor: Optional[rum.CfnAppMonitor] = None
        self.identity_pool: Optional[cognito.CfnIdentityPool] = None
        self.user_pool: Optional[cognito.UserPool] = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the RUM stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.rum_config = RumConfig(stack_config.dictionary.get("rum", {}))

        logger.info(f"Building RUM stack: {self.rum_config.name}")

        # Setup enhanced SSM integration
        rum_config = stack_config.dictionary.get("rum", {}).copy()

        # Configure SSM imports for cognito resources if needed
        if not self.rum_config.cognito_identity_pool_id:
            # Only add SSM imports if we have the required template variables
            # Check if deployment has organization info for template resolution
            if (hasattr(deployment, 'organization') and deployment.organization and
                hasattr(deployment, 'environment') and deployment.environment):
                # Add explicit import path for cognito identity pool using new pattern
                if "ssm" not in rum_config:
                    rum_config["ssm"] = {}
                if "imports" not in rum_config["ssm"]:
                    rum_config["ssm"]["imports"] = {}
                rum_config["ssm"]["imports"][
                    "cognito_identity_pool_id"
                ] = "/{{ORGANIZATION}}/{{ENVIRONMENT}}/cognito/user-pool/identity-pool-id"

        self.setup_ssm_integration(
            scope=self,
            config=rum_config,
            resource_type="rum",
            resource_name=self.rum_config.name,
        )

        # Process SSM imports using standardized method
        self.process_ssm_imports()

        # Import or create Cognito resources
        identity_pool_id, guest_role_arn = self._setup_cognito_integration()

        # Create the RUM app monitor
        self._create_app_monitor(identity_pool_id, guest_role_arn)

        # Export resources to SSM
        self._export_ssm_parameters()

    def _setup_cognito_integration(self) -> tuple[str, str]:
        """
        Setup Cognito integration - either import existing resources or create new ones.
        Returns (identity_pool_id, guest_role_arn)
        """
        identity_pool_id = None
        guest_role_arn = None

        # Try to import existing Cognito Identity Pool ID from SSM or config
        if self.rum_config.cognito_identity_pool_id:
            identity_pool_id = self.rum_config.cognito_identity_pool_id
            logger.info(f"Using existing Cognito Identity Pool: {identity_pool_id}")
        else:
            # Try to import from SSM using standardized approach
            cognito_identity_pool_id = self.get_ssm_imported_value("cognito_identity_pool_id")

            if cognito_identity_pool_id:
                identity_pool_id = cognito_identity_pool_id
                logger.info(
                    f"Imported Cognito Identity Pool from SSM: {identity_pool_id}"
                )

        # If no existing identity pool found, create new Cognito resources
        if not identity_pool_id and self.rum_config.create_cognito_identity_pool:
            identity_pool_id, guest_role_arn = self._create_cognito_resources()

        # If we still don't have an identity pool, create a minimal one
        if not identity_pool_id:
            identity_pool_id, guest_role_arn = self._create_minimal_identity_pool()

        return identity_pool_id, guest_role_arn

    def _create_cognito_resources(self) -> tuple[str, str]:
        """Create new Cognito User Pool and Identity Pool for RUM"""
        logger.info("Creating new Cognito resources for RUM")

        def _resource_name(name: str) -> str:
            """Helper to generate resource names"""
            return f"{self.rum_config.name}-{name}"

        # Create User Pool if needed
        user_pool_id = self.rum_config.cognito_user_pool_id
        if not user_pool_id and self.rum_config.create_cognito_user_pool:
            self.user_pool = cognito.UserPool(
                self,
                id=_resource_name("user-pool"),
                user_pool_name=self.rum_config.cognito_user_pool_name,
                self_sign_up_enabled=True,
                sign_in_aliases=cognito.SignInAliases(email=True),
                auto_verify=cognito.AutoVerifiedAttrs(email=True),
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )
            user_pool_id = self.user_pool.user_pool_id
            logger.info(f"Created Cognito User Pool: {user_pool_id}")

        # Create Identity Pool
        identity_pool_providers = []
        if user_pool_id and self.user_pool:
            # Create User Pool Client for Identity Pool integration
            user_pool_client = cognito.UserPoolClient(
                self,
                id=_resource_name("user-pool-client"),
                user_pool=self.user_pool,
                generate_secret=False,
                auth_flows=cognito.AuthFlow(user_srp=True, user_password=True),
            )

            identity_pool_providers.append(
                {
                    "providerName": f"cognito-idp.{self.region}.amazonaws.com/{user_pool_id}",
                    "providerType": "COGNITO_USER_POOLS",
                    "clientId": user_pool_client.user_pool_client_id,
                }
            )

        self.identity_pool = cognito.CfnIdentityPool(
            self,
            id=_resource_name("identity-pool"),
            identity_pool_name=self.rum_config.cognito_identity_pool_name,
            allow_unauthenticated_identities=True,
            cognito_identity_providers=(
                identity_pool_providers if identity_pool_providers else None
            ),
        )

        # Create IAM role for unauthenticated users (guest role)
        guest_role = iam.Role(
            self,
            id=_resource_name("guest-role"),
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "unauthenticated"
                    },
                },
            ),
            inline_policies={
                "RUMPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["rum:PutRumEvents"],
                            resources=[
                                f"arn:aws:rum:{self.region}:{self.account}:appmonitor/{self.rum_config.name}"
                            ],
                        )
                    ]
                )
            },
        )

        # Attach the role to the identity pool
        cognito.CfnIdentityPoolRoleAttachment(
            self,
            id=_resource_name("role-attachment"),
            identity_pool_id=self.identity_pool.ref,
            roles={"unauthenticated": guest_role.role_arn},
        )

        logger.info(f"Created Cognito Identity Pool: {self.identity_pool.ref}")
        return self.identity_pool.ref, guest_role.role_arn

    def _create_minimal_identity_pool(self) -> tuple[str, str]:
        """Create a minimal Identity Pool with just a guest role for RUM"""
        logger.info("Creating minimal Cognito Identity Pool for RUM")

        def _resource_name(name: str) -> str:
            """Helper to generate resource names"""
            return f"{self.rum_config.name}-{name}"

        # Create minimal Identity Pool
        minimal_identity_pool = cognito.CfnIdentityPool(
            self,
            id=_resource_name("minimal-identity-pool"),
            identity_pool_name=f"{self.rum_config.name}_minimal_identity_pool",
            allow_unauthenticated_identities=True,
        )

        # Create minimal IAM role for unauthenticated users
        guest_role = iam.Role(
            self,
            id=_resource_name("minimal-guest-role"),
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "unauthenticated"
                    },
                },
            ),
            inline_policies={
                "RUMPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["rum:PutRumEvents"],
                            resources=[
                                f"arn:aws:rum:{self.region}:{self.account}:appmonitor/{self.rum_config.name}"
                            ],
                        )
                    ]
                )
            },
        )

        # Attach the role to the identity pool
        cognito.CfnIdentityPoolRoleAttachment(
            self,
            id=_resource_name("minimal-role-attachment"),
            identity_pool_id=self.identity_pool.ref,
            roles={"unauthenticated": guest_role.role_arn},
        )

        return self.identity_pool.ref, guest_role.role_arn

    def _create_app_monitor(
        self, identity_pool_id: str, guest_role_arn: Optional[str]
    ) -> None:
        """Create the CloudWatch RUM app monitor"""
        logger.info("Creating CloudWatch RUM app monitor")

        def _resource_name(name: str) -> str:
            """Helper to generate resource names"""
            return f"{self.rum_config.name}-{name}"

        # Create app monitor configuration
        app_monitor_config = rum.CfnAppMonitor.AppMonitorConfigurationProperty(
            allow_cookies=self.rum_config.allow_cookies,
            enable_x_ray=self.rum_config.enable_xray,
            favorite_pages=self.rum_config.favorite_pages,
            guest_role_arn=guest_role_arn,
            identity_pool_id=identity_pool_id,
            session_sample_rate=self.rum_config.session_sample_rate,
            telemetries=self.rum_config.telemetries,
        )

        self.app_monitor = rum.CfnAppMonitor(
            self,
            id=_resource_name("app-monitor"),
            name=self.rum_config.name,
            domain=self.rum_config.domain,
            app_monitor_configuration=app_monitor_config,
            cw_log_enabled=self.rum_config.cw_log_enabled,
        )

        logger.info(f"Created CloudWatch RUM app monitor: {self.rum_config.name}")

        # Create custom events configuration if enabled
        custom_events = None
        if self.rum_config.custom_events_enabled:
            custom_events = rum.CfnAppMonitor.CustomEventsProperty(status="ENABLED")

        # Update the app monitor with additional properties
        # (Note: some properties like custom_events need to be set during creation)

        # Add tags if specified
        if self.rum_config.tags:
            for key, value in self.rum_config.tags.items():
                cdk.Tags.of(self.app_monitor).add(key, value)

        logger.info(f"Created RUM app monitor: {self.app_monitor.name}")

    def _export_ssm_parameters(self) -> None:
        """Export RUM resources to SSM using enhanced SSM parameter mixin"""
        if not self.app_monitor:
            logger.warning("No app monitor to export")
            return

        # Prepare resource values for export
        resource_values = {
            "app_monitor_name": self.app_monitor.name,
            "app_monitor_id": self.app_monitor.ref,
        }

        # Add identity pool info if available
        if self.identity_pool:
            resource_values["identity_pool_id"] = self.identity_pool.ref

        # Add user pool info if available
        if self.user_pool:
            resource_values["user_pool_id"] = self.user_pool.user_pool_id

        # Use enhanced SSM parameter export
        exported_params = self.export_ssm_parameters(resource_values)

        if exported_params:
            logger.info(f"Exported {len(exported_params)} RUM parameters to SSM")
        else:
            logger.info("No SSM parameters configured for export")
