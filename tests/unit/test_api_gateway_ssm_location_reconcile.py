"""
Synth regression test for the api-gateway ssm-LOCATION reconciliation defect.

Defect (pre-existing cdk-factory engine inconsistency): the api-gateway stack
read ``ssm.imports`` from TWO different locations depending on the code path, so
a config that satisfied one path fatally failed the other.

- The AUTHORIZER lookup
  (``ApiGatewayIntegrationUtility._get_existing_authorizer_id_with_ssm_fallback``
  and the ``user_pool_arn`` lookup in ``get_or_create_authorizer``) read the
  NESTED block: ``stack_config.dictionary["api_gateway"]["ssm"]``. That path
  WORKED — a real CI log shows the user-pool ARN resolving from
  ``/geekcafe/prod/cognito/user-pool/user-pool-arn``.
- The LAMBDA-ROUTE AUTO-DISCOVERY path
  (``ApiGatewayStack._get_lambda_arn_from_ssm`` and the route-group variant
  ``ApiGatewayRouteGroupNestedStack._resolve_lambda_arn``) read the TOP-LEVEL
  block via ``stack_config.ssm_config`` (= ``stack_config.dictionary["ssm"]``).
  The ``_KNOWN_IMPORT_KEYS`` validation at the top of ``_build`` read the same
  top level.

Real configs (geek-cafe-lambdas api-gateway.json) nest the ssm block INSIDE
``api_gateway``, so the top-level block is EMPTY. Lambda-route auto-discovery
therefore saw no ``lambda_namespace`` and raised::

    ✗ Configuration Error
    Stack 'geekcafe-prod-api-gateway': 'ssm.imports.lambda_namespace' is required
    for Lambda auto-discovery (route references
    lambda_name='geekcafe-prod-chatops-ingress'). Add 'ssm.imports.lambda_namespace'
    to your stack config.

...even though the config DOES define ``api_gateway.ssm.imports.lambda_namespace``.

Fix: a single shared resolver (``StackConfig.resolved_ssm_config("api_gateway")``)
prefers the populated nested ``api_gateway.ssm`` block with a fallback to the
stack top-level ``ssm`` block, and EVERY api-gateway ssm.imports read site routes
through it (import-key validation, authorizer lookup, user-pool lookup,
lambda-route auto-discovery, the route-group variant, route53 auto-discovery).

This test mirrors the REAL downstream shape: ssm ONLY nested under
``api_gateway`` with NO top-level ssm block at all. It FAILS pre-fix with the
exact "'ssm.imports.lambda_namespace' is required" error (top-level read is
empty) and PASSES after the reconciliation. A second test proves a hypothetical
TOP-LEVEL-only ssm api-gateway config still resolves (true backward-compatible
reconcile, not a flip from one broken location to another).

Hermetic: a ``devops`` section is included in the WorkloadConfig and the test
does not depend on AWS account env vars (mirrors
tests/unit/test_api_gateway_lambda_namespace_normalization.py and
tests/unit/test_lambda_sqs_trigger_consume_grant.py).
"""

import json
import re

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewaySsmLocationReconcile:
    """A nested-only ssm api-gateway config must synth, resolve the authorizer,
    AND compose correct lambda-route auto-discovery SSM paths."""

    WORKLOAD = "geekcafe"
    ENV = "prod"

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        return DeploymentConfig(
            workload={"name": self.WORKLOAD},
            deployment={
                "name": "test-deployment",
                "account": "123456789012",
                "region": "us-east-1",
                "environment": self.ENV,
                "workload_name": self.WORKLOAD,
            },
        )

    @pytest.fixture
    def workload_config(self):
        # Hermetic: include a "devops" section so WorkloadConfig does not fall
        # back to AWS account env vars and sys.exit(1) on a clean environment.
        return WorkloadConfig(config={"name": self.WORKLOAD, "devops": {"name": "d"}})

    def _nested_only_stack_dict(self) -> dict:
        """Exact shape of geek-cafe-lambdas/cdk/configs/stacks/api-gateway.json
        with placeholders resolved (workload="geekcafe", env="prod").

        The ssm block lives ONLY nested under ``api_gateway`` — there is NO
        top-level ``ssm`` key. This is the real failing shape: pre-fix, the
        lambda-route auto-discovery read the (missing) top-level block and raised
        "'ssm.imports.lambda_namespace' is required".
        """
        return {
            "name": f"{self.WORKLOAD}-{self.ENV}-api-gateway",
            "module": "api_gateway_stack",
            "enabled": True,
            # NOTE: deliberately NO top-level "ssm" key.
            "api_gateway": {
                "name": f"{self.WORKLOAD}-{self.ENV}-api",
                "description": f"API Gateway for {self.WORKLOAD} application",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "workload": self.WORKLOAD,
                    "environment": self.ENV,
                    "auto_export": True,
                    "imports": {
                        "workload": self.WORKLOAD,
                        "environment": self.ENV,
                        # BARE fragment; engine composes /{ns}/{lambda}/arn.
                        "lambda_namespace": f"{self.WORKLOAD}/{self.ENV}",
                        # Full path consumed by the authorizer lookup.
                        "user_pool_arn": (
                            f"/{self.WORKLOAD}/{self.ENV}"
                            f"/cognito/user-pool/user-pool-arn"
                        ),
                    },
                },
                "cognito_authorizer": {
                    "authorizer_name": f"{self.WORKLOAD}-cognito-authorizer"
                },
                "routes": [
                    {
                        "path": "/notifications/chatops",
                        "method": "POST",
                        "name": f"{self.WORKLOAD}-{self.ENV}-chatops-ingress",
                        "lambda_name": f"{self.WORKLOAD}-{self.ENV}-chatops-ingress",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                        "cors": {
                            "origins": ["*"],
                            "methods": ["POST", "OPTIONS"],
                            "headers": ["Content-Type", "Authorization"],
                        },
                    },
                    {
                        "path": "/contact-threads",
                        "method": "POST",
                        "name": f"{self.WORKLOAD}-{self.ENV}-create-contact-thread",
                        "lambda_name": (
                            f"{self.WORKLOAD}-{self.ENV}-create-contact-thread"
                        ),
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                        "cors": {
                            "origins": ["*"],
                            "methods": ["POST", "OPTIONS"],
                            "headers": [
                                "Content-Type",
                                "Authorization",
                                "x-api-key",
                            ],
                        },
                    },
                    {
                        "path": "/app/contact-threads",
                        "method": "GET",
                        "name": f"{self.WORKLOAD}-{self.ENV}-list-contact-threads",
                        "lambda_name": (
                            f"{self.WORKLOAD}-{self.ENV}-list-contact-threads"
                        ),
                        "authorization_type": "COGNITO",
                        "cors": {
                            "origins": ["*"],
                            "methods": ["GET", "OPTIONS"],
                            "headers": ["Content-Type", "Authorization"],
                        },
                    },
                ],
            },
        }

    def _top_level_only_stack_dict(self) -> dict:
        """Backward-compat shape: the SAME api-gateway stack but with the ssm
        block at the stack TOP LEVEL instead of nested. The resolver must fall
        back to the top-level block so this config still works (proving the fix
        is a true reconcile, not a flip to the other broken location).

        Note: this shape keeps the nested block minimal (only what the authorizer
        user_pool_arn lookup needs) and puts the lambda_namespace at top level.
        """
        return {
            "name": f"{self.WORKLOAD}-{self.ENV}-api-gateway",
            "module": "api_gateway_stack",
            "enabled": True,
            # ssm at the STACK TOP LEVEL (legacy / hypothetical shape).
            "ssm": {
                "enabled": True,
                "imports": {
                    "lambda_namespace": f"{self.WORKLOAD}/{self.ENV}",
                    "user_pool_arn": (
                        f"/{self.WORKLOAD}/{self.ENV}"
                        f"/cognito/user-pool/user-pool-arn"
                    ),
                },
            },
            "api_gateway": {
                "name": f"{self.WORKLOAD}-{self.ENV}-api",
                "api_type": "REST",
                "stage_name": "prod",
                "cognito_authorizer": {
                    "authorizer_name": f"{self.WORKLOAD}-cognito-authorizer"
                },
                "routes": [
                    {
                        "path": "/app/contact-threads",
                        "method": "GET",
                        "name": f"{self.WORKLOAD}-{self.ENV}-list-contact-threads",
                        "lambda_name": (
                            f"{self.WORKLOAD}-{self.ENV}-list-contact-threads"
                        ),
                        "authorization_type": "COGNITO",
                        "cors": {
                            "origins": ["*"],
                            "methods": ["GET", "OPTIONS"],
                            "headers": ["Content-Type", "Authorization"],
                        },
                    },
                ],
            },
        }

    def _synth(self, app, deployment_config, workload_config, stack_dict, cid):
        stack_config = StackConfig(stack=stack_dict, workload={"name": self.WORKLOAD})
        stack = ApiGatewayStack(
            scope=app,
            id=cid,
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        return Template.from_stack(stack)

    def test_nested_only_ssm_synthesizes_and_resolves_everything(
        self, app, deployment_config, workload_config
    ):
        """The real failing shape: ssm ONLY nested under api_gateway. Must synth,
        resolve the authorizer (user_pool_arn), AND auto-discover every lambda
        route's ARN at '/geekcafe/prod/<lambda>/arn'. Pre-fix this raised
        "'ssm.imports.lambda_namespace' is required"."""
        template = self._synth(
            app,
            deployment_config,
            workload_config,
            self._nested_only_stack_dict(),
            "test-api-gw-nested-only",
        )
        blob = json.dumps(template.to_json())

        # Lambda-route auto-discovery composed the correct canonical paths for
        # BOTH a NONE route and a COGNITO route.
        assert "/geekcafe/prod/geekcafe-prod-chatops-ingress/arn" in blob
        assert "/geekcafe/prod/geekcafe-prod-create-contact-thread/arn" in blob
        assert "/geekcafe/prod/geekcafe-prod-list-contact-threads/arn" in blob

        # Authorizer resolved from the nested user_pool_arn full path.
        assert "/geekcafe/prod/cognito/user-pool/user-pool-arn" in blob

        # No malformed double slash crept into any composed path.
        assert not re.search(r"//geekcafe|/geekcafe/prod//|/prod//", blob), (
            "A composed SSM path contains a double slash"
        )

        # The REST API and the Cognito authorizer both rendered.
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)
        template.resource_count_is("AWS::ApiGateway::Authorizer", 1)

    def test_top_level_ssm_still_resolves_backward_compat(
        self, app, deployment_config, workload_config
    ):
        """Backward compat: a top-level-ssm api-gateway config must still resolve
        the lambda_namespace (resolver falls back to top-level when nested is
        empty), proving the fix reconciles rather than flipping the broken
        location."""
        template = self._synth(
            app,
            deployment_config,
            workload_config,
            self._top_level_only_stack_dict(),
            "test-api-gw-top-level",
        )
        blob = json.dumps(template.to_json())

        assert "/geekcafe/prod/geekcafe-prod-list-contact-threads/arn" in blob
        assert "/geekcafe/prod/cognito/user-pool/user-pool-arn" in blob
        assert not re.search(r"//geekcafe|/geekcafe/prod//|/prod//", blob)
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
