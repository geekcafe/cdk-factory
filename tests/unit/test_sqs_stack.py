"""
Unit tests for SQS Stack
"""

import unittest
from unittest.mock import patch, MagicMock

from aws_cdk import App
from aws_cdk import aws_sqs as sqs

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.sqs import SQS as SQSConfig
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
        {
            "sqs": {
                "queues": [
                    {
                        "queue_name": "test-queue",
                        "id": "test-queue-id"
                    }
                ]
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
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
                        "max_receive_count": 3
                    },
                    {
                        "queue_name": "fifo-queue.fifo",
                        "id": "fifo-queue-id",
                        "visibility_timeout_seconds": 60,
                        "message_retention_period_days": 7,
                        "delay_seconds": 0,
                        "add_dead_letter_queue": False
                    }
                ]
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
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
        
        # Call the create queue method
        result = stack._create_queue(queue_config, queue_name)
        
        # Verify the queue was created with the correct properties
        mock_queue_constructor.assert_called_once()
        args, kwargs = mock_queue_constructor.call_args
        
        # Check that the queue was created with the correct properties
        assert kwargs["queue_name"] == queue_name
        assert "visibility_timeout" in kwargs
        assert "retention_period" in kwargs
        assert "delivery_delay" in kwargs
        assert kwargs["fifo"] is False
        
        # Verify the result is the mock queue
        assert result == mock_queue
        
        # Verify the queue was stored in the stack's queues dictionary
        assert queue_name in stack.queues
        assert stack.queues[queue_name] == mock_queue


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
        
        # Call the create DLQ method
        result = stack._create_dead_letter_queue(queue_config, queue_name)
        
        # Verify the DLQ was created with the correct properties
        mock_queue_constructor.assert_called_once()
        args, kwargs = mock_queue_constructor.call_args
        
        # Check that the DLQ was created with the correct properties
        assert kwargs["queue_name"] == f"{queue_name}-dlq"
        assert "retention_period" in kwargs
        assert kwargs["fifo"] is False
        
        # Verify the result is the mock DLQ
        assert result == mock_dlq
        
        # Verify the DLQ was stored in the stack's dead_letter_queues dictionary
        dlq_name = f"{queue_name}-dlq"
        assert dlq_name in stack.dead_letter_queues
        assert stack.dead_letter_queues[dlq_name] == mock_dlq


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
    mock_dlq.queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue-dlq"
    
    # Add the queues to the stack
    stack.queues = {"test-queue": mock_queue}
    stack.dead_letter_queues = {"test-queue-dlq": mock_dlq}
    
    # Mock the CfnOutput constructor
    with patch("aws_cdk.CfnOutput") as mock_cfn_output:
        # Call the add outputs method
        stack._add_outputs()
        
        # Verify CfnOutput was called for each queue property (ARN and URL)
        assert mock_cfn_output.call_count == 4  # 2 for queue (ARN, URL) + 2 for DLQ (ARN, URL)


def test_sqs_config():
    """Test SQSConfig class"""
    # Test with minimal configuration
    minimal_config = SQSConfig({
        "queues": [
            {
                "queue_name": "minimal-queue"
            }
        ]
    })
    
    # Check that the queues were loaded
    assert len(minimal_config.queues) == 1
    assert minimal_config.queues[0].name == "minimal-queue"
    
    # Test with full configuration
    full_config = SQSConfig({
        "queues": [
            {
                "queue_name": "standard-queue",
                "id": "standard-queue-id",
                "visibility_timeout_seconds": 30,
                "message_retention_period_days": 4,
                "delay_seconds": 5,
                "add_dead_letter_queue": True,
                "max_receive_count": 3
            },
            {
                "queue_name": "fifo-queue.fifo",
                "id": "fifo-queue-id",
                "visibility_timeout_seconds": 60,
                "message_retention_period_days": 7,
                "delay_seconds": 0,
                "add_dead_letter_queue": False
            }
        ]
    })
    
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
