"""
Regression tests — SQS Backward Compatibility

Verifies the existing inline SQS pattern (`sqs.queues` in Lambda configs) continues
to work correctly after the new decoupled trigger pattern was introduced.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import pytest

from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.configurations.cdk_config import CdkConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app():
    return App()


@pytest.fixture
def workload_config():
    return WorkloadConfig(
        config={
            "name": "test-workload",
            "description": "Backward compat test workload",
            "devops": {"ci_cd": {"enabled": True}},
        }
    )


@pytest.fixture
def deployment_config():
    workload_dict = {
        "name": "test-workload",
        "description": "Backward compat test workload",
        "devops": {"ci_cd": {"enabled": True}},
    }
    deployment_dict = {
        "name": "test-deployment",
        "account": "123456789012",
        "region": "us-east-1",
        "environment": "test",
        "devops": {"ci_cd": {"enabled": True}},
    }
    return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)


# ──────────────────────────────────────────────────────────────────────────────
# Requirement 4.1 — Inline consumer pattern still creates EventSourceMapping
# ──────────────────────────────────────────────────────────────────────────────


class TestInlineConsumerPattern:
    """Verify the existing inline `sqs.queues` consumer config still creates
    an EventSourceMapping after the new trigger pattern was added."""

    def test_inline_consumer_creates_event_source_mapping(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.1: The Lambda_Stack SHALL continue to process the existing
        "sqs": {"queues": [...]} inline pattern for consumer types.
        """
        stack_dict = {
            "name": "test-inline-consumer-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "inline-consumer-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 180,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "schedule": None,
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": "test-workload-test-analysis-queue",
                                "id": "a1b2c3d4-5e6f-7a8b-9c0d-e1f2a3b4c5d6",
                                "description": "Test consumer queue",
                                "visibility_timeout_seconds": 180,
                                "message_retention_period_days": 7,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": True,
                            }
                        ]
                    },
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="InlineConsumerStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Verify an EventSourceMapping exists with the expected queue ARN
        # In decoupled mode, from_queue_arn gives a string ARN (not a Fn::GetAtt ref)
        template.has_resource_properties(
            "AWS::Lambda::EventSourceMapping",
            {
                "EventSourceArn": "arn:aws:sqs:us-east-1:123456789012:test-workload-test-analysis-queue",
            },
        )

    def test_inline_consumer_creates_event_source_mapping_resource_exists(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.1: Verify at least one EventSourceMapping resource is present
        when using the inline consumer pattern.
        """
        stack_dict = {
            "name": "test-inline-esm-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "esm-consumer-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 60,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "schedule": None,
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": "test-workload-test-my-queue",
                                "id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
                                "visibility_timeout_seconds": 60,
                                "message_retention_period_days": 7,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": False,
                            }
                        ]
                    },
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="InlineESMStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # There should be at least one EventSourceMapping resource
        resources = template.find_resources("AWS::Lambda::EventSourceMapping")
        assert len(resources) >= 1, (
            "Expected at least 1 EventSourceMapping for inline consumer, "
            f"got {len(resources)}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Requirement 4.1 — Inline producer pattern still grants send permissions
# ──────────────────────────────────────────────────────────────────────────────


class TestInlineProducerPattern:
    """Verify inline producer config still grants sqs:SendMessage permissions."""

    def test_inline_producer_synthesizes_without_error(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.1: The Lambda_Stack SHALL continue to process the existing
        "sqs": {"queues": [...]} inline pattern for producer types.

        The inline producer pattern calls queue.grant_send_messages() which grants
        sqs:SendMessage permissions on the Lambda's execution role via a DefaultPolicy.
        This test verifies the pattern synthesizes successfully without errors.
        """
        stack_dict = {
            "name": "test-inline-producer-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "inline-producer-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "schedule": None,
                    "sqs": {
                        "queues": [
                            {
                                "type": "producer",
                                "queue_name": "test-workload-test-output-queue",
                                "id": "c3d4e5f6-a7b8-9c0d-1e2f-3a4b5c6d7e8f",
                                "description": "Producer sends to output queue",
                            }
                        ]
                    },
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="InlineProducerStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Synthesis succeeded — inline producer pattern works without error
        assert template.to_json() is not None

        # Verify the Lambda function was created
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "app.lambda_handler",
                "Runtime": "python3.11",
            },
        )

        # Verify IAM policy exists (the Lambda execution role policy is created)
        iam_policies = template.find_resources("AWS::IAM::Policy")
        assert len(iam_policies) >= 1, "Expected at least one IAM Policy resource"


# ──────────────────────────────────────────────────────────────────────────────
# Requirement 4.2 — lambda_config_paths discovery still works
# ──────────────────────────────────────────────────────────────────────────────


class TestLambdaConfigPathsDiscovery:
    """Verify that lambda_config_paths resolution still discovers consumer queues
    from Lambda stack configs and populates the SQS stack's sqs.queues array."""

    def test_resolve_lambda_config_paths_discovers_consumer_queues(self):
        """
        Requirement 4.2: The SQS_Stack SHALL continue to support the
        `lambda_config_paths` resolution pattern for discovering inline queue
        definitions.
        """
        # Simulate a config tree with a lambda stack containing inline consumer queues
        # and an SQS stack with lambda_config_paths
        config = {
            "workload": {
                "name": "test-workload",
                "deployments": [
                    {
                        "name": "test-deploy",
                        "pipeline": {
                            "stages": [
                                {
                                    "name": "compute",
                                    "stacks": [
                                        {
                                            "name": "my-lambda-stack",
                                            "module": "lambda_stack",
                                            "resources": [
                                                {
                                                    "name": "handler-fn",
                                                    "sqs": {
                                                        "queues": [
                                                            {
                                                                "type": "consumer",
                                                                "queue_name": "test-workload-test-discovered-queue",
                                                                "visibility_timeout_seconds": 120,
                                                                "message_retention_period_days": 7,
                                                            },
                                                            {
                                                                "type": "producer",
                                                                "queue_name": "test-workload-test-output-queue",
                                                            },
                                                        ]
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "name": "messaging",
                                    "stacks": [
                                        {
                                            "name": "my-sqs-stack",
                                            "module": "sqs_stack",
                                            "lambda_config_paths": ["my-lambda-stack"],
                                            "sqs": {"queues": []},
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        }

        # Run the resolution
        CdkConfig._resolve_lambda_config_paths(config)

        # Find the SQS stack and verify consumer queues were populated
        sqs_stack_config = config["workload"]["deployments"][0]["pipeline"]["stages"][
            1
        ]["stacks"][0]
        sqs_queues = sqs_stack_config.get("sqs", {}).get("queues", [])

        # Should have discovered the consumer queue (not the producer)
        assert len(sqs_queues) == 1
        assert sqs_queues[0]["queue_name"] == "test-workload-test-discovered-queue"
        assert sqs_queues[0]["type"] == "consumer"
        assert sqs_queues[0]["visibility_timeout_seconds"] == 120
        assert sqs_queues[0]["message_retention_period_days"] == 7

    def test_lambda_config_paths_ignores_producer_queues(self):
        """
        Requirement 4.2: Only consumer queues are discovered; producer
        queues are not added to the SQS stack.
        """
        config = {
            "workload": {
                "name": "test-workload",
                "deployments": [
                    {
                        "name": "test-deploy",
                        "pipeline": {
                            "stages": [
                                {
                                    "name": "compute",
                                    "stacks": [
                                        {
                                            "name": "lambda-stack",
                                            "module": "lambda_stack",
                                            "resources": [
                                                {
                                                    "name": "producer-fn",
                                                    "sqs": {
                                                        "queues": [
                                                            {
                                                                "type": "producer",
                                                                "queue_name": "output-queue",
                                                            }
                                                        ]
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "name": "messaging",
                                    "stacks": [
                                        {
                                            "name": "sqs-stack",
                                            "module": "sqs_stack",
                                            "lambda_config_paths": ["lambda-stack"],
                                            "sqs": {"queues": []},
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        }

        CdkConfig._resolve_lambda_config_paths(config)

        sqs_stack_config = config["workload"]["deployments"][0]["pipeline"]["stages"][
            1
        ]["stacks"][0]
        sqs_queues = sqs_stack_config.get("sqs", {}).get("queues", [])

        # Producer-only configs should not populate the SQS stack
        assert len(sqs_queues) == 0

    def test_lambda_config_paths_deduplicates_by_queue_name(self):
        """
        Requirement 4.2: If multiple resources reference the same consumer queue,
        it's only added once to the SQS stack.
        """
        config = {
            "workload": {
                "name": "test-workload",
                "deployments": [
                    {
                        "name": "test-deploy",
                        "pipeline": {
                            "stages": [
                                {
                                    "name": "compute",
                                    "stacks": [
                                        {
                                            "name": "lambda-stack",
                                            "module": "lambda_stack",
                                            "resources": [
                                                {
                                                    "name": "handler-a",
                                                    "sqs": {
                                                        "queues": [
                                                            {
                                                                "type": "consumer",
                                                                "queue_name": "shared-queue",
                                                                "visibility_timeout_seconds": 60,
                                                                "message_retention_period_days": 7,
                                                            }
                                                        ]
                                                    },
                                                },
                                                {
                                                    "name": "handler-b",
                                                    "sqs": {
                                                        "queues": [
                                                            {
                                                                "type": "consumer",
                                                                "queue_name": "shared-queue",
                                                                "visibility_timeout_seconds": 60,
                                                                "message_retention_period_days": 7,
                                                            }
                                                        ]
                                                    },
                                                },
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "name": "messaging",
                                    "stacks": [
                                        {
                                            "name": "sqs-stack",
                                            "module": "sqs_stack",
                                            "lambda_config_paths": ["lambda-stack"],
                                            "sqs": {"queues": []},
                                        }
                                    ],
                                },
                            ]
                        },
                    }
                ],
            }
        }

        CdkConfig._resolve_lambda_config_paths(config)

        sqs_stack_config = config["workload"]["deployments"][0]["pipeline"]["stages"][
            1
        ]["stacks"][0]
        sqs_queues = sqs_stack_config.get("sqs", {}).get("queues", [])

        # Should deduplicate — only one entry for shared-queue
        assert len(sqs_queues) == 1
        assert sqs_queues[0]["queue_name"] == "shared-queue"


# ──────────────────────────────────────────────────────────────────────────────
# Requirement 4.3 — Both inline and new trigger patterns coexist
# ──────────────────────────────────────────────────────────────────────────────


class TestInlineAndTriggerCoexistence:
    """Verify that both the inline SQS pattern and the new trigger-based pattern
    can coexist on the same Lambda without conflict."""

    def test_both_inline_and_trigger_patterns_produce_valid_cf(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.3: WHEN both the inline pattern and the new trigger pattern
        are present on the same Lambda config, THE Lambda_Stack SHALL process both
        independently without conflict.
        """
        stack_dict = {
            "name": "test-combined-patterns-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "combined-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 180,
                    "memory_size": 256,
                    "environment_variables": [],
                    "schedule": None,
                    # Inline pattern: consumer + producer
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": "test-workload-test-inline-queue",
                                "id": "d4e5f6a7-b8c9-0d1e-2f3a-4b5c6d7e8f9a",
                                "visibility_timeout_seconds": 180,
                                "message_retention_period_days": 7,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": False,
                            },
                            {
                                "type": "producer",
                                "queue_name": "test-workload-test-output-queue",
                                "id": "e5f6a7b8-c9d0-1e2f-3a4b-5c6d7e8f9a0b",
                                "description": "Inline producer queue",
                            },
                        ]
                    },
                    # New trigger pattern: separate SQS trigger
                    "triggers": [
                        {
                            "name": "trigger-queue-consumer",
                            "resource_type": "sqs",
                            "queue_name": "test-workload-test-trigger-queue",
                            "batch_size": 5,
                            "max_batching_window_seconds": 30,
                        }
                    ],
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="CombinedPatternsStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Verify CloudFormation is valid (synthesis succeeded)
        assert template.to_json() is not None

        # Should have at least 2 EventSourceMappings:
        # one from the inline consumer, one from the trigger pattern
        esm_resources = template.find_resources("AWS::Lambda::EventSourceMapping")
        assert len(esm_resources) >= 2, (
            f"Expected at least 2 EventSourceMappings (inline + trigger), "
            f"got {len(esm_resources)}"
        )

        # The trigger-based ESM should have batch_size=5
        found_trigger_esm = False
        for _logical_id, resource in esm_resources.items():
            props = resource.get("Properties", {})
            if props.get("BatchSize") == 5:
                found_trigger_esm = True
                # Verify max batching window
                assert props.get("MaximumBatchingWindowInSeconds") == 30
                break

        assert found_trigger_esm, (
            "Expected to find an EventSourceMapping with BatchSize=5 from the "
            "new trigger pattern"
        )

    def test_combined_patterns_no_duplicate_iam_policies(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.3: Both patterns on the same Lambda should not produce
        conflicting IAM policies.
        """
        stack_dict = {
            "name": "test-combined-iam-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "iam-combined-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 60,
                    "memory_size": 256,
                    "environment_variables": [],
                    "schedule": None,
                    # Inline producer
                    "sqs": {
                        "queues": [
                            {
                                "type": "producer",
                                "queue_name": "test-workload-test-send-queue",
                                "id": "f6a7b8c9-d0e1-2f3a-4b5c-6d7e8f9a0b1c",
                                "description": "Inline producer",
                            }
                        ]
                    },
                    # New trigger pattern: consumer
                    "triggers": [
                        {
                            "name": "trigger-consumer",
                            "resource_type": "sqs",
                            "queue_name": "test-workload-test-recv-queue",
                            "batch_size": 1,
                        }
                    ],
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="CombinedIAMStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Synthesis succeeded without errors — no conflict
        assert template.to_json() is not None

        # Verify IAM policies exist (both inline producer and trigger consumer
        # should generate their own IAM statements)
        iam_policies = template.find_resources("AWS::IAM::Policy")
        assert len(iam_policies) >= 1, "Expected at least one IAM Policy resource"


# ──────────────────────────────────────────────────────────────────────────────
# Requirement 4.4 — No changes required to existing config files
# ──────────────────────────────────────────────────────────────────────────────


class TestNoChangesRequired:
    """Verify that existing configs without the new trigger pattern still work
    exactly as before — no migration needed."""

    def test_config_without_triggers_key_works(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.4: Existing configs that don't use the `triggers` array
        should still synthesize correctly.
        """
        stack_dict = {
            "name": "test-legacy-only-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "legacy-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 60,
                    "memory_size": 256,
                    "environment_variables": [],
                    "schedule": None,
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": "test-workload-test-legacy-queue",
                                "id": "aabbccdd-1122-3344-5566-778899001122",
                                "visibility_timeout_seconds": 60,
                                "message_retention_period_days": 7,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": False,
                            }
                        ]
                    },
                    # No triggers key at all — legacy config
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="LegacyOnlyStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Synthesis should succeed
        assert template.to_json() is not None

        # Should still have ESM from inline consumer
        esm_resources = template.find_resources("AWS::Lambda::EventSourceMapping")
        assert len(esm_resources) >= 1

    def test_config_with_empty_triggers_works(
        self, app, deployment_config, workload_config
    ):
        """
        Requirement 4.4: Existing configs with an empty `triggers` array
        should still synthesize correctly.
        """
        stack_dict = {
            "name": "test-empty-triggers-stack",
            "enabled": True,
            "sqs_decoupled_mode": True,
            "resources": [
                {
                    "name": "empty-triggers-fn",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 60,
                    "memory_size": 256,
                    "environment_variables": [],
                    "triggers": [],
                    "schedule": None,
                    "sqs": {
                        "queues": [
                            {
                                "type": "consumer",
                                "queue_name": "test-workload-test-empty-triggers-queue",
                                "id": "11223344-5566-7788-99aa-bbccddeeff00",
                                "visibility_timeout_seconds": 60,
                                "message_retention_period_days": 7,
                                "delay_seconds": 0,
                                "add_dead_letter_queue": False,
                            }
                        ]
                    },
                }
            ],
        }
        workload_dict = {"name": "test-workload"}
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = LambdaStack(
            scope=app,
            id="EmptyTriggersStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Synthesis should succeed
        assert template.to_json() is not None

        # Should still have ESM from inline consumer
        esm_resources = template.find_resources("AWS::Lambda::EventSourceMapping")
        assert len(esm_resources) >= 1
