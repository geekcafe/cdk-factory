"""
Regression test for the generic Secrets Manager stack (secrets_manager_stack).

The stack creates one or more Secrets Manager secrets, each seeded with a
PLACEHOLDER value at create time (the real value is seeded out-of-band after
deploy). Secrets default to a RETAIN removal policy so they survive stack
deletion.

This test synthesizes a stack with two secrets and asserts against the SYNTHESIZED
template that:
  * exactly two AWS::SecretsManager::Secret resources are rendered,
  * each has the expected secret Name,
  * each carries the placeholder as its SecretString,
  * each has DeletionPolicy / UpdateReplacePolicy == "Retain".

Hermetic: a ``devops`` section is included in the WorkloadConfig and the test
does not depend on AWS account env vars (mirrors
tests/unit/test_lambda_sqs_trigger_consume_grant.py and
tests/unit/test_api_gateway_lambda_namespace_normalization.py).
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.secrets_manager.secrets_manager_stack import (
    SecretsManagerStack,
)
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestSecretsManagerStack:
    """Verify the Secrets Manager stack renders placeholder secrets with RETAIN."""

    SECRET_INGRESS = "chatops/ingress/shared-secret"
    SECRET_BOT_TOKEN = "chatops/slack/geekcafe/bot-token"
    PLACEHOLDER = "REPLACE_ME"

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        return DeploymentConfig(
            workload={"name": "test-workload"},
            deployment={
                "name": "test-deployment",
                "account": "123456789012",
                "region": "us-east-1",
                "environment": "test",
            },
        )

    @pytest.fixture
    def workload_config(self):
        # Hermetic: include a "devops" section so WorkloadConfig does not fall back
        # to AWS account env vars and sys.exit(1) on a clean environment.
        return WorkloadConfig(config={"name": "test-workload", "devops": {"name": "d"}})

    def _build_template(self, app, deployment_config, workload_config) -> Template:
        stack_dict = {
            "name": "test-secrets-stack",
            "module": "secrets_manager_stack",
            "secrets": [
                {
                    "name": self.SECRET_INGRESS,
                    "description": "Ingress shared secret",
                    "placeholder": self.PLACEHOLDER,
                },
                {
                    "name": self.SECRET_BOT_TOKEN,
                    "description": "Slack bot token",
                    "placeholder": self.PLACEHOLDER,
                },
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload={"name": "test-workload"})

        stack = SecretsManagerStack(
            scope=app,
            id="test-secrets-manager",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        return Template.from_stack(stack)

    def test_two_secret_resources_rendered(
        self, app, deployment_config, workload_config
    ):
        """Exactly two AWS::SecretsManager::Secret resources are synthesized."""
        template = self._build_template(app, deployment_config, workload_config)
        template.resource_count_is("AWS::SecretsManager::Secret", 2)

    def test_each_secret_has_name_placeholder_and_retain(
        self, app, deployment_config, workload_config
    ):
        """Each secret has the expected Name, placeholder SecretString, and
        DeletionPolicy / UpdateReplacePolicy == Retain."""
        template = self._build_template(app, deployment_config, workload_config)

        resources = template.find_resources("AWS::SecretsManager::Secret")
        assert len(resources) == 2

        names_seen = set()
        for resource in resources.values():
            props = resource["Properties"]
            names_seen.add(props["Name"])
            # Placeholder is written verbatim as the SecretString.
            assert props["SecretString"] == self.PLACEHOLDER
            # RETAIN renders on both deletion and replace policies.
            assert resource["DeletionPolicy"] == "Retain"
            assert resource["UpdateReplacePolicy"] == "Retain"

        assert names_seen == {self.SECRET_INGRESS, self.SECRET_BOT_TOKEN}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
