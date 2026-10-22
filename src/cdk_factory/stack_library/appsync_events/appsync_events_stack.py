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

import re
from typing import Dict, List, Optional

from aws_cdk import Stack
from aws_cdk import aws_appsync as appsync
from aws_cdk import aws_lambda as _lambda
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


# AWS::AppSync::ChannelNamespace `Name` constraint (per the CloudFormation
# resource spec): 1–50 chars, alphanumeric + hyphen, MUST start and end with an
# alphanumeric — NO underscore. Validating here fails synth with a clear message
# instead of letting CloudFormation reject it at CREATE time (which, in a prod
# pipeline, surfaces as a CREATE_FAILED + stack rollback — e.g. a name like
# "event_bus" passes a naive check but is rejected by AppSync at deploy).
_CHANNEL_NAMESPACE_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,48}[A-Za-z0-9])?$"
)


# Friendly config tokens -> AWS AppSync auth-type identifiers. Config-level auth
# blocks speak the friendly tokens; the construct maps them here.
_FRIENDLY_TO_AUTH_TYPE: Dict[str, str] = {
    "lambda": "AWS_LAMBDA",
    "cognito": "AMAZON_COGNITO_USER_POOLS",
    "api_key": "API_KEY",
}


def _resolve_auth_type(token: str) -> str:
    """Map a friendly auth token to its AppSync auth-type, failing synth on typos."""
    auth_type = _FRIENDLY_TO_AUTH_TYPE.get(token)
    if auth_type is None:
        raise ValueError(f"unknown appsync_events auth token '{token}'")
    return auth_type


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
            raise ValueError("appsync_events config requires 'user_pool_id_ssm_path'")
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
        """Reject invalid or duplicate namespace names.

        Each name must satisfy the AWS::AppSync::ChannelNamespace ``Name``
        constraint (alphanumeric + hyphen, 1–50 chars, start/end alphanumeric,
        no underscore) so an invalid name fails fast at synth rather than at
        CloudFormation CREATE time. Duplicates are also rejected (they would
        collide on construct id).
        """
        seen: set[str] = set()
        for ns in namespaces:
            if not _CHANNEL_NAMESPACE_NAME_PATTERN.match(ns.name or ""):
                raise ValueError(
                    f"Invalid channel namespace name '{ns.name}' in appsync_events "
                    "config: AppSync channel namespace names must be 1–50 characters, "
                    "contain only letters, digits, and hyphens, and start and end "
                    "with a letter or digit (no underscores). "
                    "Pattern: [A-Za-z0-9](?:[A-Za-z0-9-]{0,48}[A-Za-z0-9])?"
                )
            if ns.name in seen:
                raise ValueError(
                    f"Duplicate channel namespace name '{ns.name}' in "
                    "appsync_events config"
                )
            seen.add(ns.name)

    def _build_api(self, namespaces: List[AppSyncEventsChannelNamespaceConfig]) -> None:
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

        auth = self.config.auth

        def _cognito_provider() -> appsync.CfnApi.AuthProviderProperty:
            return appsync.CfnApi.AuthProviderProperty(
                auth_type="AMAZON_COGNITO_USER_POOLS",
                cognito_config=appsync.CfnApi.CognitoConfigProperty(
                    aws_region=region,
                    user_pool_id=user_pool_id,
                ),
            )

        def _lambda_provider() -> appsync.CfnApi.AuthProviderProperty:
            return appsync.CfnApi.AuthProviderProperty(
                auth_type="AWS_LAMBDA",
                lambda_authorizer_config=appsync.CfnApi.LambdaAuthorizerConfigProperty(
                    authorizer_uri=authorizer_fn_arn,
                    authorizer_result_ttl_in_seconds=self.config.authorizer_result_ttl_seconds,
                ),
            )

        def _api_key_provider() -> appsync.CfnApi.AuthProviderProperty:
            return appsync.CfnApi.AuthProviderProperty(auth_type="API_KEY")

        _provider_builders = {
            "cognito": _cognito_provider,
            "lambda": _lambda_provider,
            "api_key": _api_key_provider,
        }

        # PROVIDERS: inherit today's exact set when `auth.providers` is absent,
        # else emit exactly the configured providers in order. Track whether the
        # AWS_LAMBDA authorizer provider is present so we know whether to grant
        # AppSync permission to invoke the authorizer Lambda (below).
        lambda_provider_configured = False
        if auth.providers is None:
            auth_providers = [_cognito_provider(), _lambda_provider()]
            lambda_provider_configured = True
            if self.config.api_key_publish:
                auth_providers.append(_api_key_provider())
        else:
            auth_providers = []
            for token in auth.providers:
                # Validate the token maps to a known auth-type (fail synth on typos)
                # even though the provider builder is keyed on the friendly token.
                _resolve_auth_type(token)
                builder = _provider_builders.get(token)
                if builder is None:
                    raise ValueError(f"unknown appsync_events auth token '{token}'")
                if token == "lambda":
                    lambda_provider_configured = True
                auth_providers.append(builder())

        def _modes(
            configured: Optional[List[str]],
            default_auth_types: List[str],
        ) -> List[appsync.CfnApi.AuthModeProperty]:
            auth_types = (
                default_auth_types
                if configured is None
                else [_resolve_auth_type(token) for token in configured]
            )
            return [
                appsync.CfnApi.AuthModeProperty(auth_type=auth_type)
                for auth_type in auth_types
            ]

        default_publish_auth_type = (
            "API_KEY" if self.config.api_key_publish else "AWS_LAMBDA"
        )

        event_config = appsync.CfnApi.EventConfigProperty(
            auth_providers=auth_providers,
            connection_auth_modes=_modes(auth.connection_auth_modes, ["AWS_LAMBDA"]),
            default_subscribe_auth_modes=_modes(
                auth.subscribe_auth_modes, ["AWS_LAMBDA"]
            ),
            default_publish_auth_modes=_modes(
                auth.publish_auth_modes, [default_publish_auth_type]
            ),
        )

        self.api = appsync.CfnApi(
            self,
            f"{base}-events-api",
            name=base,
            event_config=event_config,
        )

        # The raw L1 CfnApi (unlike the L2 appsync.Api) does NOT auto-grant
        # AppSync permission to invoke the Lambda authorizer. Without this grant
        # the authorizer Lambda's resource policy is empty and AppSync rejects
        # every connection_init with BadRequestException 400 (the authorizer is
        # never invoked). Emit the grant only when an AWS_LAMBDA authorizer is
        # actually configured.
        if lambda_provider_configured:
            self._grant_appsync_invoke_authorizer(base, authorizer_fn_arn)

        for ns in namespaces:
            self._build_namespace(base, ns)

    def _grant_appsync_invoke_authorizer(
        self, base: str, authorizer_fn_arn: str
    ) -> None:
        """Grant AppSync permission to invoke the Lambda authorizer function.

        The authorizer is referenced ARN-only (a deploy-time SSM token), so there
        is no ``IFunction`` to call ``add_permission`` on; use an L1
        ``CfnPermission`` with the token ARN as ``function_name`` (mirrors the
        api_gateway route-group precedent).

        ``source_arn`` is the **bare** API ARN (``{attr_api_arn}``), NOT a
        sub-resource glob. This was confirmed empirically: AppSync Events invokes
        the Lambda authorizer with a ``SourceArn`` equal to the bare API ARN, so
        a resource policy scoped to ``{attr_api_arn}/*`` does NOT match — AppSync
        is then denied, the authorizer is never invoked, and the connection fails
        with 400 ``BadRequestException``. Granting on the bare ARN lets AppSync
        invoke the authorizer (the live console error moved 400 -> 401, i.e.
        AppSync now invokes the authorizer, which then makes its own allow/deny
        decision). Both the API ARN and the authorizer ARN are deploy-time
        CloudFormation tokens, so nothing is resolved at synth and no
        account/region/apiId is hardcoded.
        """
        _lambda.CfnPermission(
            self,
            f"{base}-authorizer-invoke-permission",
            action="lambda:InvokeFunction",
            function_name=authorizer_fn_arn,
            principal="appsync.amazonaws.com",
            source_arn=self.api.attr_api_arn,
        )

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
