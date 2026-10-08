"""
AppSync Events Stack Pattern for CDK-Factory

Synthesizes a single AppSync **Events** API (``CfnApi`` + ``EventConfig``) plus
one ``CfnChannelNamespace`` per configured namespace, and exports the api-id /
HTTP (publish) endpoint / realtime (subscribe) endpoint to SSM Parameter Store
for downstream consumers (the realtime-publisher Lambda and the Vue subscribe
client).

Auth model (phase1-design §1.3): the API registers a Cognito-User-Pools provider
and an AWS_LAMBDA authorizer provider (and, when ``api_key_publish`` is on, an
API_KEY provider for the server-side publisher). Connect/subscribe are gated by
the Lambda authorizer (which enforces the channel-scope invariant); publish
defaults to API_KEY when enabled, else AWS_LAMBDA.

Cross-stack ids (user-pool id, authorizer ARN) are resolved at DEPLOY time as
CloudFormation tokens via ``aws_ssm.StringParameter.value_for_string_parameter``
— no live boto3, no ``value_from_lookup`` at synth (NFR-2 / constraint C2).

Construct IDs are explicit, stable strings seeded on the config ``name`` (never
the builtin randomized-per-process ``hash`` function), so the synthesized
CloudFormation logical IDs are reproducible across synths (constraint C3).

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, List, Optional

from aws_cdk import Stack
from aws_cdk import aws_appsync as appsync
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.appsync_events import (
    AppSyncEventsChannelNamespaceConfig,
    AppSyncEventsConfig,
)
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="AppSyncEventsStack")


@register_stack("appsync_events_library_module")
@register_stack("appsync_events_stack")
class AppSyncEventsStack(IStack):
    """
    Reusable stack for an AWS AppSync **Events** API.

    Creates one ``CfnApi`` (with Cognito + Lambda-authorizer auth) and one
    ``CfnChannelNamespace`` per configured namespace, then publishes the api-id,
    HTTP endpoint, and realtime endpoint to SSM so other stacks can reference
    them without a direct cross-stack dependency.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config: Optional[AppSyncEventsConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.api: Optional[appsync.CfnApi] = None
        self.channel_namespaces: List[appsync.CfnChannelNamespace] = []

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the AppSync Events stack."""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.config = AppSyncEventsConfig(
            stack_config.dictionary.get("appsync_events", {})
        )

        # Required cross-stack SSM paths (fatal if missing — fail synth).
        if not self.config.user_pool_id_ssm_path:
            raise ValueError(
                "appsync_events config requires 'user_pool_id_ssm_path'"
            )
        if not self.config.authorizer_lambda_arn_ssm_path:
            raise ValueError(
                "appsync_events config requires 'authorizer_lambda_arn_ssm_path'"
            )

        namespaces = self.config.channel_namespaces
        self._validate_namespace_names(namespaces)
        if not namespaces:
            logger.warning(
                "🚨 No channel_namespaces defined in the appsync_events "
                "configuration; creating the API with no namespaces."
            )

        self._build_api(namespaces)
        self._export_to_ssm()

    def _validate_namespace_names(
        self, namespaces: List[AppSyncEventsChannelNamespaceConfig]
    ) -> None:
        """Reject duplicate namespace names (would collide on construct id)."""
        seen: set[str] = set()
        for ns in namespaces:
            if ns.name in seen:
                raise ValueError(
                    f"Duplicate channel namespace name '{ns.name}' in "
                    "appsync_events config"
                )
            seen.add(ns.name)

    def _build_api(
        self, namespaces: List[AppSyncEventsChannelNamespaceConfig]
    ) -> None:
        """Create the ``CfnApi`` and its channel namespaces."""
        workload = self.deployment.workload_name
        env = self.deployment.environment
        base = f"{workload}-{env}-{self.config.name}"

        region = self.config.region or self.deployment.region or Stack.of(self).region

        # Deploy-time CloudFormation tokens (never literals, never live boto3).
        user_pool_id = ssm.StringParameter.value_for_string_parameter(
            self, self.config.user_pool_id_ssm_path
        )
        authorizer_fn_arn = ssm.StringParameter.value_for_string_parameter(
            self, self.config.authorizer_lambda_arn_ssm_path
        )

        auth_providers = [
            appsync.CfnApi.AuthProviderProperty(
                auth_type="AMAZON_COGNITO_USER_POOLS",
                cognito_config=appsync.CfnApi.CognitoConfigProperty(
                    aws_region=region,
                    user_pool_id=user_pool_id,
                ),
            ),
            appsync.CfnApi.AuthProviderProperty(
                auth_type="AWS_LAMBDA",
                lambda_authorizer_config=appsync.CfnApi.LambdaAuthorizerConfigProperty(
                    authorizer_uri=authorizer_fn_arn,
                    authorizer_result_ttl_in_seconds=self.config.authorizer_result_ttl_seconds,
                ),
            ),
        ]
        if self.config.api_key_publish:
            auth_providers.append(
                appsync.CfnApi.AuthProviderProperty(auth_type="API_KEY")
            )

        if self.config.api_key_publish:
            default_publish_auth_modes = [
                appsync.CfnApi.AuthModeProperty(auth_type="API_KEY")
            ]
        else:
            default_publish_auth_modes = [
                appsync.CfnApi.AuthModeProperty(auth_type="AWS_LAMBDA")
            ]

        event_config = appsync.CfnApi.EventConfigProperty(
            auth_providers=auth_providers,
            connection_auth_modes=[
                appsync.CfnApi.AuthModeProperty(auth_type="AWS_LAMBDA")
            ],
            default_subscribe_auth_modes=[
                appsync.CfnApi.AuthModeProperty(auth_type="AWS_LAMBDA")
            ],
            default_publish_auth_modes=default_publish_auth_modes,
        )

        self.api = appsync.CfnApi(
            self,
            f"{base}-events-api",
            name=base,
            event_config=event_config,
        )

        for ns in namespaces:
            self._build_namespace(base, ns)

    def _build_namespace(
        self, base: str, ns: AppSyncEventsChannelNamespaceConfig
    ) -> None:
        """Create one ``CfnChannelNamespace`` honoring any per-namespace overrides."""
        kwargs: Dict = {
            "api_id": self.api.attr_api_id,
            "name": ns.name,
        }
        if ns.publish_auth_modes is not None:
            kwargs["publish_auth_modes"] = [
                appsync.CfnChannelNamespace.AuthModeProperty(
                    auth_type=mode.get("auth_type")
                )
                for mode in ns.publish_auth_modes
            ]
        if ns.subscribe_auth_modes is not None:
            kwargs["subscribe_auth_modes"] = [
                appsync.CfnChannelNamespace.AuthModeProperty(
                    auth_type=mode.get("auth_type")
                )
                for mode in ns.subscribe_auth_modes
            ]

        channel_namespace = appsync.CfnChannelNamespace(
            self,
            f"{base}-ns-{ns.name}",
            **kwargs,
        )
        self.channel_namespaces.append(channel_namespace)

    def _export_to_ssm(self) -> None:
        """Publish the api-id / HTTP endpoint / realtime endpoint to SSM.

        Uses the ``ssm.namespace`` prefix, falling back to
        ``/{workload}/{environment}/appsync-events`` for parity with the SQS and
        SNS modules.
        """
        ssm_config = self.config.ssm
        namespace = ssm_config.get("namespace")
        if namespace:
            prefix = f"/{namespace}"
        else:
            prefix = (
                f"/{self.deployment.workload_name}/"
                f"{self.deployment.environment}/appsync-events"
            )

        name = self.config.name

        ssm.StringParameter(
            self,
            f"ssm-{name}-events-api-id",
            parameter_name=f"{prefix}/{name}/api-id",
            string_value=self.api.attr_api_id,
            description=f"AppSync Events API id for {name}",
        )
        ssm.StringParameter(
            self,
            f"ssm-{name}-events-http-endpoint",
            parameter_name=f"{prefix}/{name}/http-endpoint",
            string_value=self.api.attr_dns_http,
            description=f"AppSync Events HTTP (publish) endpoint for {name}",
        )
        ssm.StringParameter(
            self,
            f"ssm-{name}-events-realtime-endpoint",
            parameter_name=f"{prefix}/{name}/realtime-endpoint",
            string_value=self.api.attr_dns_realtime,
            description=f"AppSync Events realtime (subscribe) endpoint for {name}",
        )
