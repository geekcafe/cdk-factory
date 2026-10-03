"""
Regression test for the SQS-trigger consume-grant defect.

Defect: ``LambdaStack.__setup_sqs_trigger`` created the SQS EventSourceMapping and
then granted the consumer ``sqs:ReceiveMessage`` / ``sqs:DeleteMessage`` /
``sqs:GetQueueAttributes`` via ``lambda_function.add_to_role_policy(...)``.  The
Lambda function is wired to its execution role via ``role.without_policy_updates()``
(``LambdaFunctionUtilities.create``), which returns an immutable IRole view that
SILENTLY DROPS statements added through the function.  As a result the grant never
rendered into the synthesized CloudFormation template: ``cdk synth`` succeeded, but
the consumer execution role had NO SQS consume permissions, so at deploy/runtime the
EventSourceMapping could not poll the queue.

The fix attaches the consume policy to the real ``iam.Role`` construct (exposed by
``LambdaConstruct.create_function`` as ``cdk_factory_execution_role``) so it renders.

This test synthesizes a stack with an SQS-triggered Lambda whose queue is imported
via ``queue_ssm_path`` (the exact path ``__setup_sqs_trigger`` is exercised through)
and asserts against the SYNTHESIZED template that the consumer execution-role policy
contains the SQS consume actions scoped to the imported queue.  It FAILS on the old
behavior (no such statement rendered) and PASSES on the fix.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestLambdaSqsTriggerConsumeGrant:
    """Verify SQS-trigger consume permissions render into the synthesized template."""

    QUEUE_SSM_PATH = "/my-app/test/sqs/my-queue/arn"

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
        # Include a "devops" section so the test is hermetic: without it,
        # WorkloadConfig falls back to AWS account env vars and sys.exit(1)s on a
        # clean environment (IDE/CI). Mirrors tests/unit/test_chatops_sqs_queue.py.
        return WorkloadConfig(config={"name": "test-workload", "devops": {"name": "d"}})

    def _build_template(self, app, deployment_config, workload_config) -> Template:
        stack_dict = {
            "name": "test-sqs-consumer-stack",
            "auto_export": True,
            "resources": [
                {
                    "name": "consumer",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "triggers": [
                        {
                            "resource_type": "sqs",
                            "queue_ssm_path": self.QUEUE_SSM_PATH,
                            "batch_size": 1,
                            "max_batching_window_seconds": 0,
                        }
                    ],
                }
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload={"name": "test-workload"})

        stack = LambdaStack(
            scope=app,
            id="test-sqs-consume-grant",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        return Template.from_stack(stack)

    @staticmethod
    def _sqs_consume_statements(template: Template):
        """Return every IAM policy statement that grants the SQS consume actions."""
        policies = template.find_resources("AWS::IAM::Policy")
        matches = []
        for policy in policies.values():
            statements = policy["Properties"]["PolicyDocument"]["Statement"]
            for statement in statements:
                actions = statement.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]
                if {
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                }.issubset(set(actions)):
                    matches.append(statement)
        return matches

    def test_event_source_mapping_created(
        self, app, deployment_config, workload_config
    ):
        """Sanity: the SQS trigger still produces exactly one EventSourceMapping."""
        template = self._build_template(app, deployment_config, workload_config)
        template.resource_count_is("AWS::Lambda::EventSourceMapping", 1)

    def test_consumer_role_has_sqs_consume_permissions(
        self, app, deployment_config, workload_config
    ):
        """
        The synthesized consumer execution-role policy MUST contain the SQS
        consume actions.  This is the exact thing that was empty before the fix.
        """
        template = self._build_template(app, deployment_config, workload_config)

        matches = self._sqs_consume_statements(template)

        assert matches, (
            "No IAM policy statement granting SQS consume permissions "
            "(ReceiveMessage/DeleteMessage/GetQueueAttributes) was rendered into "
            "the synthesized template. The consumer role cannot poll the queue."
        )

        # The grant must be scoped to the imported queue ARN (resolved from the
        # queue_ssm_path SSM parameter), not a wildcard.
        for statement in matches:
            assert statement.get("Effect") == "Allow"
            resource = statement.get("Resource")
            assert resource != "*", "SQS consume grant must not use a wildcard resource"
            # The resource is a CF token (Ref) to the SSM-imported queue ARN.
            assert isinstance(resource, dict) and "Ref" in resource, (
                "SQS consume grant should be scoped to the imported queue ARN token, "
                f"got: {resource!r}"
            )
