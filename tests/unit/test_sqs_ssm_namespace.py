"""
Unit tests for SQS Stack SSM publish path generation.
Covers namespace mode (ARN, URL, DLQ) and legacy mode confirmation.
"""

from unittest.mock import patch, MagicMock

from aws_cdk import App

from cdk_factory.stack_library.simple_queue_service.sqs_stack import SQSStack


class TestSQSSSMNamespace:
    """Test SQS Stack SSM publish path generation with namespace."""

    def test_sqs_ssm_namespace_arn(self):
        """Verify namespace SSM path for queue ARN."""
        app = App()
        stack = SQSStack(app, "TestSqsNsArn")

        deployment = MagicMock()
        deployment.workload_name = "my-workload"
        deployment.environment = "dev"
        stack.deployment = deployment

        # Set stack_config with namespace
        stack_config = MagicMock()
        stack_config.dictionary = {"ssm": {"namespace": "my-ns"}}
        stack.stack_config = stack_config

        queue_config = MagicMock()
        queue_config.name = "test-queue"

        with patch(
            "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
        ) as mock_ssm:
            mock_queue = MagicMock()
            mock_queue.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
            mock_queue.queue_url = (
                "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
            )

            stack._publish_queue_to_ssm(mock_queue, queue_config, is_dlq=False)

            arn_call = mock_ssm.call_args_list[0]
            assert arn_call[1]["parameter_name"] == "/my-ns/sqs/test-queue/arn"

    def test_sqs_ssm_namespace_url(self):
        """Verify namespace SSM path for queue URL."""
        app = App()
        stack = SQSStack(app, "TestSqsNsUrl")

        deployment = MagicMock()
        deployment.workload_name = "my-workload"
        deployment.environment = "dev"
        stack.deployment = deployment

        stack_config = MagicMock()
        stack_config.dictionary = {"ssm": {"namespace": "my-ns"}}
        stack.stack_config = stack_config

        queue_config = MagicMock()
        queue_config.name = "test-queue"

        with patch(
            "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
        ) as mock_ssm:
            mock_queue = MagicMock()
            mock_queue.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
            mock_queue.queue_url = (
                "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
            )

            stack._publish_queue_to_ssm(mock_queue, queue_config, is_dlq=False)

            url_call = mock_ssm.call_args_list[1]
            assert url_call[1]["parameter_name"] == "/my-ns/sqs/test-queue/url"

    def test_sqs_ssm_namespace_dlq(self):
        """Verify namespace SSM path for DLQ ARN uses -dlq suffix."""
        app = App()
        stack = SQSStack(app, "TestSqsNsDlq")

        deployment = MagicMock()
        deployment.workload_name = "my-workload"
        deployment.environment = "dev"
        stack.deployment = deployment

        stack_config = MagicMock()
        stack_config.dictionary = {"ssm": {"namespace": "my-ns"}}
        stack.stack_config = stack_config

        queue_config = MagicMock()
        queue_config.name = "test-queue"

        with patch(
            "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
        ) as mock_ssm:
            mock_dlq = MagicMock()
            mock_dlq.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue-dlq"
            mock_dlq.queue_url = (
                "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue-dlq"
            )

            stack._publish_queue_to_ssm(mock_dlq, queue_config, is_dlq=True)

            arn_call = mock_ssm.call_args_list[0]
            assert arn_call[1]["parameter_name"] == "/my-ns/sqs/test-queue-dlq/arn"

    def test_sqs_ssm_legacy_arn(self):
        """Verify legacy SSM path for queue ARN (no namespace)."""
        app = App()
        stack = SQSStack(app, "TestSqsLegacyArn")

        deployment = MagicMock()
        deployment.workload_name = "my-workload"
        deployment.environment = "dev"
        stack.deployment = deployment

        stack_config = MagicMock()
        stack_config.dictionary = {}
        stack.stack_config = stack_config

        queue_config = MagicMock()
        queue_config.name = "test-queue"

        with patch(
            "cdk_factory.stack_library.simple_queue_service.sqs_stack.ssm.StringParameter"
        ) as mock_ssm:
            mock_queue = MagicMock()
            mock_queue.queue_arn = "arn:aws:sqs:us-east-1:123456789012:test-queue"
            mock_queue.queue_url = (
                "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
            )

            stack._publish_queue_to_ssm(mock_queue, queue_config, is_dlq=False)

            arn_call = mock_ssm.call_args_list[0]
            assert (
                arn_call[1]["parameter_name"] == "/my-workload/dev/sqs/test-queue/arn"
            )
