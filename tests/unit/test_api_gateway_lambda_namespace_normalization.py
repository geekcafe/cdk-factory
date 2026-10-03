"""
Synth regression test for the bare-``lambda_namespace`` SSM-path defect.

Defect (long-standing, pre-dates the chatops work): a real CI/CD ``cdk synth`` of
the downstream geek-cafe-lambdas api-gateway stack died with::

    ✗ Configuration Error
    imports.lambda_namespace: SSM path must start with '/': geekcafe/prod

Root cause: the api-gateway stack carries
``ssm.imports.lambda_namespace = "{{WORKLOAD_NAME}}/{{ENVIRONMENT}}"`` which
resolves to the BARE namespace fragment ``"geekcafe/prod"`` (no leading slash).
This is by design — the Lambda-ARN resolution code composes the full path itself
(``/{namespace}/{lambda}/arn``) and the lambda stack exports to exactly
``/geekcafe/prod/<lambda>/arn``. But a COGNITO route drives
``ApiGatewayIntegrationUtility.get_or_create_authorizer`` ->
``StandardizedSsmMixin.setup_ssm_integration`` which validated the ENTIRE
``ssm.imports`` block (including ``lambda_namespace``) with a strict
"must start with '/'" rule, treating the bare fragment as if it were a full path
and fatally rejecting it. One path required the fragment to be bare; another
rejected it for being bare.

Fix: a tolerant normalizing SSM-path helper
(``cdk_factory.utilities.ssm_path_utils``) is applied at the validation and
composition sites so a bare fragment is normalized (leading slash added, ``//``
collapsed) rather than rejected.

This test synthesizes the failing scenario (bare ``lambda_namespace``, a mix of
NONE and COGNITO routes, a cognito authorizer with a full-path ``user_pool_arn``)
and asserts synth SUCCEEDS and the composed Lambda-ARN SSM lookups use the clean
``/geekcafe/prod/<lambda>/arn`` form. It FAILS on the pre-fix engine (strict
reject) and PASSES after.

Hermetic: a ``devops`` section is included in the WorkloadConfig and the test does
not depend on AWS account env vars (mirrors
tests/unit/test_lambda_sqs_trigger_consume_grant.py and
tests/unit/test_chatops_sqs_queue.py).
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


class TestApiGatewayLambdaNamespaceNormalization:
    """Bare lambda_namespace must synth cleanly and compose correct ARN paths."""

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
        # Hermetic: include a "devops" section so WorkloadConfig does not fall back
        # to AWS account env vars and sys.exit(1) on a clean environment.
        return WorkloadConfig(config={"name": self.WORKLOAD, "devops": {"name": "d"}})

    def _stack_dict(self, lambda_namespace: str) -> dict:
        """Build an api-gateway stack config equivalent to the real downstream
        geek-cafe-lambdas api-gateway.json, with the placeholders resolved
        (workload="geekcafe", env="prod") and a parametrizable lambda_namespace so
        the test can prove tolerance to leading/trailing slashes.

        The top-level ``ssm`` block carries the fragment keys used by route
        Lambda-ARN auto-discovery; the nested ``api_gateway.ssm`` block carries the
        full set used by the cognito-authorizer SSM fallback (the exact fatal path
        from the CI log).
        """
        nested_ssm = {
            "enabled": True,
            "workload": self.WORKLOAD,
            "environment": self.ENV,
            "auto_export": True,
            "imports": {
                "workload": self.WORKLOAD,
                "environment": self.ENV,
                # BARE namespace fragment — the exact value that failed in CI.
                "lambda_namespace": lambda_namespace,
                # Already-correct FULL path — must be left untouched (idempotence).
                "user_pool_arn": (
                    f"/{self.WORKLOAD}/{self.ENV}/cognito/user-pool/user-pool-arn"
                ),
            },
        }
        return {
            "name": f"{self.WORKLOAD}-{self.ENV}-api-gateway",
            "module": "api_gateway_stack",
            "enabled": True,
            # Top-level ssm with only the recognized fragment key (api-gateway
            # _KNOWN_IMPORT_KEYS = lambda/route53/cognito namespace).
            "ssm": {
                "enabled": True,
                "imports": {"lambda_namespace": lambda_namespace},
            },
            "api_gateway": {
                "name": f"{self.WORKLOAD}-{self.ENV}-api",
                "description": f"API Gateway for {self.WORKLOAD} application",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": nested_ssm,
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

    def _synth(self, app, deployment_config, workload_config, lambda_namespace):
        stack_dict = self._stack_dict(lambda_namespace)
        stack_config = StackConfig(
            stack=stack_dict, workload={"name": self.WORKLOAD}
        )
        stack = ApiGatewayStack(
            scope=app,
            id="test-api-gw-namespace-norm",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        return Template.from_stack(stack)

    def test_bare_namespace_synthesizes_and_composes_clean_paths(
        self, app, deployment_config, workload_config
    ):
        """The real failing shape: bare 'geekcafe/prod'. Must synth and compose
        '/geekcafe/prod/<lambda>/arn' (single leading slash, no '//')."""
        template = self._synth(
            app, deployment_config, workload_config, "geekcafe/prod"
        )
        blob = json.dumps(template.to_json())

        # Both Lambda-ARN lookups composed to the correct canonical path.
        assert "/geekcafe/prod/geekcafe-prod-chatops-ingress/arn" in blob
        assert "/geekcafe/prod/geekcafe-prod-list-contact-threads/arn" in blob

        # No malformed double-slash crept into any geekcafe/prod path.
        assert not re.search(r"//geekcafe|/geekcafe/prod//|/prod//", blob), (
            "A composed SSM path contains a double slash"
        )

        # API Gateway actually rendered.
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)

    @pytest.mark.parametrize(
        "lambda_namespace",
        ["geekcafe/prod", "/geekcafe/prod", "geekcafe/prod/"],
    )
    def test_namespace_slash_variants_all_resolve_identically(
        self, app, deployment_config, workload_config, lambda_namespace
    ):
        """A leading or trailing slash on the fragment must not change the result:
        all three variants compose the same clean '/geekcafe/prod/<lambda>/arn'."""
        template = self._synth(
            app, deployment_config, workload_config, lambda_namespace
        )
        blob = json.dumps(template.to_json())
        assert "/geekcafe/prod/geekcafe-prod-list-contact-threads/arn" in blob
        assert not re.search(r"//geekcafe|/geekcafe/prod//|/prod//", blob)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
