"""
Unit tests for SQS Stack
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from aws_cdk import App
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_sqs as sqs

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.sqs import SQS as SQSConfig
from cdk_factory.constructs.sqs.policies.sqs_policies import SqsPolicies
from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_sqs_stack_minimal():
    """Test SQS stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {"sqs": {"queues": [{"queue_name": "test-queue", "id": "test-queue-id"}]}},
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "test"},
    )

    # Create the stack
    stack = SQSStack(app, "TestSQSStack")

    # Mock the _build method directly
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)

        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)


def test_sqs_stack_full_config():
    """Test SQS stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "sqs": {
                "queues": [
                    {
                        "queue_name": "standard-queue",
                        "id": "standard-queue-id",
                        "visibility_timeout_seconds": 30,
                        "message_retention_period_days": 4,
                        "delay_seconds": 5,
                        "add_dead_letter_queue": True,
                        "max_receive_count": 3,
                    },
                    {
                        "queue_name": "fifo-queue.fifo",
                        "id": "fifo-queue-id",
                        "visibility_timeout_seconds": 60,
                        "message_retention_period_days": 7,
                        "delay_seconds": 0,
                        "add_dead_letter_queue": False,
                    },
                ]
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment", "environment": "test"},
    )

    # Create the stack
    stack = SQSStack(app, "FullSQSStack")

    # Test the config loading
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)

        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)

    # Create a new stack for testing the internal build logic
    stack = SQSStack(app, "FullSQSStackInternal")

    # Set up the config directly
    stack.stack_config = stack_config
    stack.deployment = deployment
    stack.workload = dummy_workload
    stack.sqs_config = SQSConfig(stack_config.dictionary.get("sqs", {}))

    # Mock the internal methods
    with patch.object(stack, "_create_queue") as mock_create_queue:
        with patch.object(stack, "_create_dead_letter_queue") as mock_create_dlq:
            with patch.object(stack, "_add_outputs") as mock_add_outputs:
                # Create mock queues
                mock_standard_queue = MagicMock()
                mock_fifo_queue = MagicMock()
                mock_dlq = MagicMock()

                # Set up mock returns
                mock_create_queue.side_effect = [mock_standard_queue, mock_fifo_queue]
                mock_create_dlq.return_value = mock_dlq

                # Call the internal _build method directly
                stack._build(stack_config, deployment, dummy_workload)

                # Verify the methods were called
                assert mock_create_queue.call_count == 2
                mock_create_dlq.assert_called_once()
                mock_add_outputs.assert_called_once()


def test_create_queue():
    """Test queue creation"""
    app = App()
    stack = SQSStack(app, "TestQueueCreation")

    # Set up deployment config
    deployment = MagicMock()
    queue_name = "test-queue"
    # Mock the build_resource_name method to return the queue name directly
    deployment.build_resource_name.return_value = queue_name

    # Create a mock queue config
    queue_config = MagicMock()
    queue_config.name = "test-queue"
    queue_config.resource_id = "test-queue-id"
    queue_config.visibility_timeout_seconds = 30
    queue_config.message_retention_period_days = 4
    queue_config.delay_seconds = 5
    queue_config.max_receive_count = 3

    # Set the deployment on the stack
    stack.deployment = deployment

    # Mock the SQS Queue constructor
    with patch("aws_cdk.aws_sqs.Queue") as mock_queue_constructor:
        # Create a mock queue
        mock_queue = MagicMock()
        mock_queue_constructor.return_value = mock_queue

        # Mock add_to_resource_policy to return a successful result for TLS enforcement
        mock_policy_result = MagicMock()
        mock_policy_result.statement_added = True
        mock_queue.add_to_resource_policy.return_value = mock_policy_result

        # Mock _publish_queue_to_ssm since SSM constructs can't accept mock queue values
        with patch.object(stack, "_publish_queue_to_ssm") as mock_publish:
            # Mock SqsPolicies.get_tls_policy to avoid JSII issues with mock queue ARN
            with patch.object(SqsPolicies, "get_tls_policy") as mock_tls_policy:
                mock_tls_statement = MagicMock()
                mock_tls_policy.return_value = mock_tls_statement

                # Call the create queue method
                result = stack._create_queue(queue_config, queue_name, deployment)

                # Verify the queue was created with the correct properties
                mock_queue_constructor.assert_called_once()
                args, kwargs = mock_queue_constructor.call_args

                # Check that the queue was created with the correct properties
                assert kwargs["queue_name"] == queue_name
                assert "visibility_timeout" in kwargs
                assert "retention_period" in kwargs
                assert "delivery_delay" in kwargs
                assert kwargs["fifo"] is False

                # Verify TLS policy was enforced
                mock_tls_policy.assert_called_once_with(mock_queue)
                mock_queue.add_to_resource_policy.assert_called_once_with(
                    mock_tls_statement
                )

                # Verify the result is the mock queue
                assert result == mock_queue

                # Verify the queue was stored in the stack's queues dictionary
                assert queue_name in stack.queues
                assert stack.queues[queue_name] == mock_queue

                # Verify SSM publishing was called for the primary queue
                mock_publish.assert_called_once_with(
                    mock_queue, queue_config, is_dlq=False
                )


def test_create_dead_letter_queue():
    """Test dead letter queue creation"""
    app = App()
    stack = SQSStack(app, "TestDLQCreation")

    # Set up deployment config with mock
    deployment = MagicMock()
    queue_name = "test-queue"
    # Mock the build_resource_name method to return the queue name directly
    deployment.build_resource_name.return_value = queue_name

    # Create a mock queue config
    queue_config = MagicMock()
    queue_config.name = "test-queue"
    queue_config.resource_id = "test-queue-id"
    queue_config.add_dead_letter_queue = True
    queue_config.max_receive_count = 3

    # Set the deployment on the stack
    stack.deployment = deployment

    # Mock the SQS Queue constructor
    with patch("aws_cdk.aws_sqs.Queue") as mock_queue_constructor:
        # Create a mock queue
        mock_dlq = MagicMock()
        mock_queue_constructor.return_value = mock_dlq

        # Mock add_to_resource_policy to return a successful result for TLS enforcement
        mock_policy_result = MagicMock()
        mock_policy_result.statement_added = True
        mock_dlq.add_to_resource_policy.return_value = mock_policy_result

        # Mock _publish_queue_to_ssm since SSM constructs can't accept mock queue values
        with patch.object(stack, "_publish_queue_to_ssm") as mock_publish:
            # Mock SqsPolicies.get_tls_policy to avoid JSII issues with mock queue ARN
            with patch.object(SqsPolicies, "get_tls_policy") as mock_tls_policy:
                mock_tls_statement = MagicMock()
                mock_tls_policy.return_value = mock_tls_statement

                # Mock cloudwatch.Alarm to verify alarm creation
                with patch("aws_cdk.aws_cloudwatch.Alarm") as mock_alarm_constructor:
                    # Call the create DLQ method
                    result = stack._create_dead_letter_queue(queue_config, queue_name)

                    # Verify the DLQ was created with the correct properties
                    mock_queue_constructor.assert_called_once()
                    args, kwargs = mock_queue_constructor.call_args

                    # Check that the DLQ was created with the correct properties
                    assert kwargs["queue_name"] == f"{queue_name}-dlq"
                    assert "retention_period" in kwargs
                    assert kwargs["fifo"] is False

                    # Verify TLS policy was enforced
                    mock_tls_policy.assert_called_once_with(mock_dlq)
                    mock_dlq.add_to_resource_policy.assert_called_once_with(
                        mock_tls_statement
                    )

                    # Verify CloudWatch alarm was created
                    mock_alarm_constructor.assert_called_once()
                    alarm_args, alarm_kwargs = mock_alarm_constructor.call_args
                    assert alarm_kwargs["alarm_name"] == f"{queue_name}-dlq-messages"
                    assert alarm_kwargs["threshold"] == 1
                    assert alarm_kwargs["evaluation_periods"] == 1

                    # Verify the result is the mock DLQ
                    assert result == mock_dlq

                    # Verify the DLQ was stored in the stack's dead_letter_queues dictionary
                    dlq_name = f"{queue_name}-dlq"
                    assert dlq_name in stack.dead_letter_queues
                    assert stack.dead_letter_queues[dlq_name] == mock_dlq

                    # Verify SSM publishing was called for the DLQ
                    mock_publish.assert_called_once_with(
                        mock_dlq, queue_config, is_dlq=True
                    )


def test_dlq_cloudwatch_alarm_configuration():
    """Test that DLQ CloudWatch alarm matches the NCA-SaaS-Application pattern"""
    app = App()
    stack = SQSStack(app, "TestDLQAlarm")

    # Set up deployment config with mock
    deployment = MagicMock()
    queue_name = "analysis-packaging"
    deployment.build_resource_name.return_value = queue_name

    # Create a mock queue config
    queue_config = MagicMock()
    queue_config.name = "analysis-packaging"
    queue_config.resource_id = "analysis-packaging-id"
    queue_config.add_dead_letter_queue = True
    queue_config.max_receive_count = 5

    # Set the deployment on the stack
    stack.deployment = deployment

    # Mock the SQS Queue constructor
    with patch("aws_cdk.aws_sqs.Queue") as mock_queue_constructor:
        mock_dlq = MagicMock()
        mock_metric = MagicMock()
        mock_dlq.metric_approximate_number_of_messages_visible.return_value = (
            mock_metric
        )
        mock_queue_constructor.return_value = mock_dlq

        mock_policy_result = MagicMock()
        mock_policy_result.statement_added = True
        mock_dlq.add_to_resource_policy.return_value = mock_policy_result

        with patch.object(stack, "_publish_queue_to_ssm"):
            with patch.object(SqsPolicies, "get_tls_policy") as mock_tls_policy:
                mock_tls_policy.return_value = MagicMock()

                with patch("aws_cdk.aws_cloudwatch.Alarm") as mock_alarm_constructor:
                    stack._create_dead_letter_queue(queue_config, queue_name)

                    # Verify alarm was created with exact NCA-SaaS-Application pattern
                    mock_alarm_constructor.assert_called_once()
                    _, alarm_kwargs = mock_alarm_constructor.call_args

                    dlq_name = f"{queue_name}-dlq"
                    assert alarm_kwargs["alarm_name"] == f"{dlq_name}-messages"
                    assert alarm_kwargs["threshold"] == 1
                    assert alarm_kwargs["evaluation_periods"] == 1
                    assert (
                        alarm_kwargs["comparison_operator"]
                        == cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
                    )
                    assert (
                        alarm_kwargs["treat_missing_data"]
                        == cloudwatch.TreatMissingData.NOT_BREACHING
                    )
                    assert alarm_kwargs["metric"] == mock_metric
                    assert "DLQ alarm for" in alarm_kwargs["alarm_description"]

                    # Verify the metric was called with correct parameters
                    mock_dlq.metric_approximate_number_of_messages_visible.assert_called_once()


def test_add_outputs():
    """Test adding outputs"""
    app = App()
    stack = SQSStack(app, "TestOutputs")

    # Set up deployment config with mock
    deployment = MagicMock()
    # Mock the build_resource_name method to return the input with a prefix
    deployment.build_resource_name.side_effect = lambda x: f"test-{x}"

    # Set the deployment on the stack
    stack.deployment = deployment

    # Create mock queues
    mock_queue = MagicMock()
    mock_queue.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
    mock_queue.queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"

    mock_dlq = MagicMock()
    mock_dlq.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue-dlq"
    mock_dlq.queue_url = (
        "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue-dlq"
    )

    # Add the queues to the stack
    stack.queues = {"test-queue": mock_queue}
    stack.dead_letter_queues = {"test-queue-dlq": mock_dlq}

    # Mock the CfnOutput constructor
    with patch("aws_cdk.CfnOutput") as mock_cfn_output:
        # Call the add outputs method
        stack._add_outputs()

        # Verify CfnOutput was called for each queue property (ARN and URL)
        assert (
            mock_cfn_output.call_count == 4
        )  # 2 for queue (ARN, URL) + 2 for DLQ (ARN, URL)


def test_sqs_config():
    """Test SQSConfig class"""
    # Test with minimal configuration
    minimal_config = SQSConfig({"queues": [{"queue_name": "minimal-queue"}]})

    # Check that the queues were loaded
    assert len(minimal_config.queues) == 1
    assert minimal_config.queues[0].name == "minimal-queue"

    # Test with full configuration
    full_config = SQSConfig(
        {
            "queues": [
                {
                    "queue_name": "standard-queue",
                    "id": "standard-queue-id",
                    "visibility_timeout_seconds": 30,
                    "message_retention_period_days": 4,
                    "delay_seconds": 5,
                    "add_dead_letter_queue": True,
                    "max_receive_count": 3,
                },
                {
                    "queue_name": "fifo-queue.fifo",
                    "id": "fifo-queue-id",
                    "visibility_timeout_seconds": 60,
                    "message_retention_period_days": 7,
                    "delay_seconds": 0,
                    "add_dead_letter_queue": False,
                },
            ]
        }
    )

    # Check that the queues were loaded
    assert len(full_config.queues) == 2

    # Check the first queue
    standard_queue = full_config.queues[0]
    assert standard_queue.name == "standard-queue"
    assert standard_queue.resource_id == "standard-queue-id"
    assert standard_queue.visibility_timeout_seconds == 30
    assert standard_queue.message_retention_period_days == 4
    assert standard_queue.delay_seconds == 5
    assert standard_queue.add_dead_letter_queue is True
    assert standard_queue.max_receive_count == 3

    # Check the second queue
    fifo_queue = full_config.queues[1]
    assert fifo_queue.name == "fifo-queue.fifo"
    assert fifo_queue.resource_id == "fifo-queue-id"
    assert fifo_queue.visibility_timeout_seconds == 60
    assert fifo_queue.message_retention_period_days == 7
    assert fifo_queue.delay_seconds == 0
    assert fifo_queue.add_dead_letter_queue is False


def test_publish_queue_to_ssm_primary():
    """Test SSM parameter publishing for a primary queue"""
    app = App()
    stack = SQSStack(app, "TestSSMPublish")

    # Set up deployment mock
    deployment = MagicMock()
    deployment.workload_name = "my-workload"
    deployment.environment = "dev"
    stack.deployment = deployment

    # Create a mock queue config
    queue_config = MagicMock()
    queue_config.name = "analysis-packaging"

    # Mock ssm.StringParameter to capture calls
    with patch(
        "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
    ) as mock_ssm:
        mock_queue = MagicMock()
        mock_queue.queue_arn = "arn:aws:sqs:us-east-1:123456789012:analysis-packaging"
        mock_queue.queue_url = (
            "https://sqs.us-east-1.amazonaws.com/123456789012/analysis-packaging"
        )

        stack._publish_queue_to_ssm(mock_queue, queue_config, is_dlq=False)

        assert mock_ssm.call_count == 2

        # Verify ARN parameter
        arn_call = mock_ssm.call_args_list[0]
        assert (
            arn_call[1]["parameter_name"]
            == "/my-workload/dev/sqs/analysis-packaging/arn"
        )
        assert arn_call[1]["string_value"] == mock_queue.queue_arn

        # Verify URL parameter
        url_call = mock_ssm.call_args_list[1]
        assert (
            url_call[1]["parameter_name"]
            == "/my-workload/dev/sqs/analysis-packaging/url"
        )
        assert url_call[1]["string_value"] == mock_queue.queue_url


def test_publish_queue_to_ssm_dlq():
    """Test SSM parameter publishing for a DLQ"""
    app = App()
    stack = SQSStack(app, "TestSSMPublishDLQ")

    # Set up deployment mock
    deployment = MagicMock()
    deployment.workload_name = "my-workload"
    deployment.environment = "staging"
    stack.deployment = deployment

    # Create a mock queue config
    queue_config = MagicMock()
    queue_config.name = "analysis-packaging"

    # Mock ssm.StringParameter to capture calls
    with patch(
        "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
    ) as mock_ssm:
        mock_dlq = MagicMock()
        mock_dlq.queue_arn = "arn:aws:sqs:us-east-1:123456789012:analysis-packaging-dlq"
        mock_dlq.queue_url = (
            "https://sqs.us-east-1.amazonaws.com/123456789012/analysis-packaging-dlq"
        )

        stack._publish_queue_to_ssm(mock_dlq, queue_config, is_dlq=True)

        assert mock_ssm.call_count == 2

        # Verify ARN parameter uses -dlq suffix
        arn_call = mock_ssm.call_args_list[0]
        assert (
            arn_call[1]["parameter_name"]
            == "/my-workload/staging/sqs/analysis-packaging-dlq/arn"
        )
        assert arn_call[1]["string_value"] == mock_dlq.queue_arn

        # Verify URL parameter uses -dlq suffix
        url_call = mock_ssm.call_args_list[1]
        assert (
            url_call[1]["parameter_name"]
            == "/my-workload/staging/sqs/analysis-packaging-dlq/url"
        )
        assert url_call[1]["string_value"] == mock_dlq.queue_url


# ──────────────────────────────────────────────────────────────────────────────
# Tests for Task 1.1: _discover_consumer_queues_from_lambda_configs
# ──────────────────────────────────────────────────────────────────────────────


class TestDiscoverConsumerQueues(unittest.TestCase):
    """Tests for the _discover_consumer_queues_from_lambda_configs method."""

    def setUp(self):
        import tempfile, os, json

        self.app = App()
        self.stack = SQSStack(self.app, "TestDiscovery")
        self.tmpdir = tempfile.mkdtemp()

        # Set up a workload mock with config_path pointing to our temp dir
        self.workload = MagicMock()
        self.workload.config_path = os.path.join(self.tmpdir, "config.json")
        self.workload.paths = [self.tmpdir]
        self.stack.workload = self.workload

        self.stack_config = MagicMock()

    def _write_json(self, filename, data):
        import os, json

        path = os.path.join(self.tmpdir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_discovers_consumer_queues(self):
        """Consumer queues are extracted with preserved properties."""
        self._write_json(
            "lambda-stack.json",
            {
                "resources": [
                    {
                        "name": "my-lambda",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "analysis-packaging",
                                    "visibility_timeout_seconds": 900,
                                    "message_retention_period_days": 7,
                                    "delay_seconds": 0,
                                    "add_dead_letter_queue": "true",
                                },
                                {
                                    "type": "producer",
                                    "queue_name": "some-output-queue",
                                },
                            ]
                        },
                    }
                ]
            },
        )

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["lambda-stack.json"], self.stack_config
        )

        assert len(result) == 1
        assert result[0].name == "analysis-packaging"
        assert result[0].visibility_timeout_seconds == 900
        assert result[0].message_retention_period_days == 7
        assert result[0].add_dead_letter_queue is True

    def test_skips_producer_queues(self):
        """Producer queues are not included in discovery results."""
        self._write_json(
            "lambda-stack.json",
            {
                "resources": [
                    {
                        "name": "my-lambda",
                        "sqs": {
                            "queues": [
                                {"type": "producer", "queue_name": "output-queue"}
                            ]
                        },
                    }
                ]
            },
        )

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["lambda-stack.json"], self.stack_config
        )

        assert len(result) == 0

    def test_deduplicates_by_queue_name_first_wins(self):
        """When duplicate queue_names appear, first occurrence wins."""
        self._write_json(
            "lambda-a.json",
            {
                "resources": [
                    {
                        "name": "lambda-a",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "shared-queue",
                                    "visibility_timeout_seconds": 100,
                                    "message_retention_period_days": 3,
                                }
                            ]
                        },
                    }
                ]
            },
        )
        self._write_json(
            "lambda-b.json",
            {
                "resources": [
                    {
                        "name": "lambda-b",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "shared-queue",
                                    "visibility_timeout_seconds": 999,
                                    "message_retention_period_days": 14,
                                }
                            ]
                        },
                    }
                ]
            },
        )

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["lambda-a.json", "lambda-b.json"], self.stack_config
        )

        assert len(result) == 1
        assert result[0].name == "shared-queue"
        assert result[0].visibility_timeout_seconds == 100
        assert result[0].message_retention_period_days == 3

    def test_missing_file_skipped_gracefully(self):
        """Missing lambda config files are skipped with a warning."""
        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["nonexistent-file.json"], self.stack_config
        )

        assert len(result) == 0

    def test_invalid_json_skipped_gracefully(self):
        """Invalid JSON files are skipped with an error log."""
        import os

        bad_path = os.path.join(self.tmpdir, "bad.json")
        with open(bad_path, "w") as f:
            f.write("{invalid json content")

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["bad.json"], self.stack_config
        )

        assert len(result) == 0

    def test_multiple_resources_multiple_files(self):
        """Discovers consumer queues across multiple resources and files."""
        self._write_json(
            "lambda-1.json",
            {
                "resources": [
                    {
                        "name": "func-a",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "queue-a",
                                    "visibility_timeout_seconds": 30,
                                    "message_retention_period_days": 4,
                                }
                            ]
                        },
                    },
                    {
                        "name": "func-b",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "queue-b",
                                    "visibility_timeout_seconds": 60,
                                    "message_retention_period_days": 7,
                                }
                            ]
                        },
                    },
                ]
            },
        )
        self._write_json(
            "lambda-2.json",
            {
                "resources": [
                    {
                        "name": "func-c",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "queue-c",
                                    "visibility_timeout_seconds": 120,
                                    "message_retention_period_days": 14,
                                }
                            ]
                        },
                    }
                ]
            },
        )

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["lambda-1.json", "lambda-2.json"], self.stack_config
        )

        names = {q.name for q in result}
        assert names == {"queue-a", "queue-b", "queue-c"}

    def test_empty_resources_array(self):
        """Config with empty resources array returns no queues."""
        self._write_json("empty.json", {"resources": []})

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["empty.json"], self.stack_config
        )

        assert len(result) == 0

    def test_resource_without_sqs_section(self):
        """Resources without an sqs section are skipped."""
        self._write_json(
            "no-sqs.json",
            {"resources": [{"name": "plain-lambda"}]},
        )

        result = self.stack._discover_consumer_queues_from_lambda_configs(
            ["no-sqs.json"], self.stack_config
        )

        assert len(result) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Tests for Task 1.2: _build merge of explicit and discovered queues
# ──────────────────────────────────────────────────────────────────────────────


class TestBuildMergeDiscoveredQueues(unittest.TestCase):
    """Tests for the _build method's merge of explicit and discovered queues."""

    def setUp(self):
        import tempfile, os, json

        self.app = App()
        self.tmpdir = tempfile.mkdtemp()

    def _write_json(self, filename, data):
        import os, json

        path = os.path.join(self.tmpdir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_build_merges_discovered_queues(self):
        """Discovered queues are added to the queue list when no explicit overlap."""
        self._write_json(
            "lambda-stack.json",
            {
                "resources": [
                    {
                        "name": "my-func",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "discovered-queue",
                                    "visibility_timeout_seconds": 60,
                                    "message_retention_period_days": 7,
                                }
                            ]
                        },
                    }
                ]
            },
        )

        stack = SQSStack(self.app, "TestMerge")
        workload = MagicMock()
        workload.config_path = os.path.join(self.tmpdir, "config.json")
        workload.paths = [self.tmpdir]

        stack_config = StackConfig(
            {
                "name": "test-sqs",
                "module": "sqs_stack",
                "lambda_config_paths": ["lambda-stack.json"],
                "sqs": {"queues": []},
            },
            workload={"name": "test-workload"},
        )

        deployment = MagicMock()
        deployment.build_resource_name.side_effect = lambda x: f"test-{x}"

        # Mock the CDK resource creation methods
        with patch.object(stack, "_create_queue") as mock_cq:
            with patch.object(stack, "_create_dead_letter_queue") as mock_dlq:
                with patch.object(stack, "_add_outputs"):
                    stack._build(stack_config, deployment, workload)

                    # Verify the discovered queue was processed
                    assert mock_cq.call_count == 1
                    call_args = mock_cq.call_args
                    assert call_args[0][0].name == "discovered-queue"

    def test_explicit_queue_overrides_discovered(self):
        """Explicit queues take precedence over discovered queues with the same name."""
        import os

        self._write_json(
            "lambda-stack.json",
            {
                "resources": [
                    {
                        "name": "my-func",
                        "sqs": {
                            "queues": [
                                {
                                    "type": "consumer",
                                    "queue_name": "overlap-queue",
                                    "visibility_timeout_seconds": 999,
                                    "message_retention_period_days": 14,
                                }
                            ]
                        },
                    }
                ]
            },
        )

        stack = SQSStack(self.app, "TestOverride")
        workload = MagicMock()
        workload.config_path = os.path.join(self.tmpdir, "config.json")
        workload.paths = [self.tmpdir]

        stack_config = StackConfig(
            {
                "name": "test-sqs",
                "module": "sqs_stack",
                "lambda_config_paths": ["lambda-stack.json"],
                "sqs": {
                    "queues": [
                        {
                            "queue_name": "overlap-queue",
                            "visibility_timeout_seconds": 30,
                            "message_retention_period_days": 4,
                        }
                    ]
                },
            },
            workload={"name": "test-workload"},
        )

        deployment = MagicMock()
        deployment.build_resource_name.side_effect = lambda x: f"test-{x}"

        with patch.object(stack, "_create_queue") as mock_cq:
            with patch.object(stack, "_create_dead_letter_queue"):
                with patch.object(stack, "_add_outputs"):
                    stack._build(stack_config, deployment, workload)

                    # Only the explicit queue should be processed (not the discovered one)
                    assert mock_cq.call_count == 1
                    call_args = mock_cq.call_args
                    # The explicit queue has visibility_timeout_seconds=30
                    assert call_args[0][0].visibility_timeout_seconds == 30

    def test_build_without_lambda_config_paths(self):
        """Build works normally when no lambda_config_paths is specified."""
        stack = SQSStack(self.app, "TestNoDiscovery")
        workload = MagicMock()
        workload.config_path = None
        workload.paths = []

        stack_config = StackConfig(
            {
                "name": "test-sqs",
                "module": "sqs_stack",
                "sqs": {
                    "queues": [
                        {
                            "queue_name": "explicit-only",
                            "visibility_timeout_seconds": 30,
                            "message_retention_period_days": 4,
                        }
                    ]
                },
            },
            workload={"name": "test-workload"},
        )

        deployment = MagicMock()
        deployment.build_resource_name.side_effect = lambda x: f"test-{x}"

        with patch.object(stack, "_create_queue") as mock_cq:
            with patch.object(stack, "_create_dead_letter_queue"):
                with patch.object(stack, "_add_outputs"):
                    stack._build(stack_config, deployment, workload)

                    assert mock_cq.call_count == 1
                    assert mock_cq.call_args[0][0].name == "explicit-only"
