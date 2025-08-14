"""
Unit tests for the Load Balancer Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_certificatemanager as acm

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.load_balancer import LoadBalancerConfig
from cdk_factory.stack_library.load_balancer.load_balancer_stack import LoadBalancerStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_load_balancer_stack_minimal():
    """Test Load Balancer stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "load_balancer": {
                "name": "test-lb",
                "type": "APPLICATION",
                "vpc_id": "vpc-12345",
                "internet_facing": True
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create the stack
    stack = LoadBalancerStack(app, "TestLoadBalancerStack")
    
    # Mock the _build method directly
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
        
        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)


def test_load_balancer_stack_full_config():
    """Test Load Balancer stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "load_balancer": {
                "name": "full-lb",
                "type": "APPLICATION",
                "vpc_id": "vpc-67890",
                "internet_facing": True,
                "deletion_protection": True,
                "idle_timeout": 60,
                "http2_enabled": True,
                "security_groups": ["sg-12345"],
                "subnets": ["subnet-1", "subnet-2"],
                "target_groups": [
                    {
                        "name": "app-tg",
                        "port": 80,
                        "protocol": "HTTP",
                        "target_type": "ip",
                        "health_check": {
                            "path": "/health",
                            "port": "traffic-port",
                            "healthy_threshold": 3,
                            "unhealthy_threshold": 3,
                            "timeout": 5,
                            "interval": 30
                        }
                    }
                ],
                "listeners": [
                    {
                        "port": 80,
                        "protocol": "HTTP",
                        "default_target_group": "app-tg",
                        "rules": [
                            {
                                "priority": 10,
                                "path_patterns": ["/api/*"],
                                "target_group": "app-tg"
                            }
                        ]
                    },
                    {
                        "port": 443,
                        "protocol": "HTTPS",
                        "default_target_group": "app-tg",
                        "certificates": ["arn:aws:acm:us-east-1:123456789012:certificate/abcdef"]
                    }
                ],
                "hosted_zone": {
                    "id": "Z1234567890",
                    "name": "example.com",
                    "record_names": ["app.example.com"]
                }
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create the stack
    stack = LoadBalancerStack(app, "FullLoadBalancerStack")
    
    # Test the config loading
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
        
        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)
        
    # Create a new stack for testing the internal build logic
    stack = LoadBalancerStack(app, "FullLoadBalancerStackInternal")
    
    # Set up the config directly
    stack.stack_config = stack_config
    stack.deployment = deployment
    stack.workload = dummy_workload
    stack.lb_config = LoadBalancerConfig(stack_config.dictionary.get("load_balancer", {}), deployment)
    
    # Mock the internal methods
    with patch.object(stack, "_create_load_balancer") as mock_create_lb:
        with patch.object(stack, "_create_target_groups") as mock_create_tg:
            with patch.object(stack, "_create_listeners") as mock_create_listeners:
                with patch.object(stack, "_setup_dns") as mock_setup_dns:
                    with patch.object(stack, "_add_outputs") as mock_add_outputs:
                        # Create a mock load balancer
                        mock_lb = MagicMock()
                        mock_create_lb.return_value = mock_lb
                        
                        # Call the internal _build method directly
                        stack._build(stack_config, deployment, dummy_workload)
                        
                        # Verify the config was loaded correctly
                        assert stack.lb_config.name == "full-lb"
                        assert stack.lb_config.type == "APPLICATION"
                        assert stack.lb_config.vpc_id == "vpc-67890"
                        assert stack.lb_config.internet_facing is True
                        assert stack.lb_config.deletion_protection is True
                        assert stack.lb_config.idle_timeout == 60
                        assert stack.lb_config.http2_enabled is True
                        assert stack.lb_config.security_groups == ["sg-12345"]
                        assert stack.lb_config.subnets == ["subnet-1", "subnet-2"]
                        
                        # Verify the methods were called
                        mock_create_lb.assert_called_once()
                        mock_create_tg.assert_called_once()
                        mock_create_listeners.assert_called_once()
                        mock_setup_dns.assert_called_once()
                        mock_add_outputs.assert_called_once()


def test_load_balancer_config():
    """Test LoadBalancerConfig class"""
    # Test with minimal configuration
    minimal_config = LoadBalancerConfig(
        {
            "name": "minimal-lb",
            "type": "APPLICATION",
            "vpc_id": "vpc-12345"
        },
        DeploymentConfig(
            workload={"workload": {"name": "test-workload", "devops": {"name": "test-devops"}}},
            deployment={"name": "test-deployment"}
        )
    )
    
    assert minimal_config.name == "minimal-lb"
    assert minimal_config.type == "APPLICATION"
    assert minimal_config.vpc_id == "vpc-12345"
    assert minimal_config.internet_facing is True  # Default value
    assert minimal_config.deletion_protection is False  # Default value
    assert minimal_config.idle_timeout == 60  # Default value
    assert minimal_config.http2_enabled is True  # Default value
    assert minimal_config.security_groups == []  # Default value
    assert minimal_config.subnets == []  # Default value
    assert minimal_config.target_groups == []  # Default value
    assert minimal_config.listeners == []  # Default value
    assert minimal_config.hosted_zone == {}  # Default value
    
    # Test with full configuration
    full_config = LoadBalancerConfig(
        {
            "name": "full-lb",
            "type": "NETWORK",
            "vpc_id": "vpc-67890",
            "internet_facing": True,
            "deletion_protection": True,
            "idle_timeout": 120,
            "http2_enabled": False,
            "security_groups": ["sg-12345", "sg-67890"],
            "subnets": ["subnet-1", "subnet-2", "subnet-3"],
            "target_groups": [
                {
                    "name": "app-tg",
                    "port": 80,
                    "protocol": "TCP"
                }
            ],
            "listeners": [
                {
                    "port": 80,
                    "protocol": "TCP",
                    "default_target_group": "app-tg"
                }
            ],
            "hosted_zone": {
                "id": "Z1234567890",
                "name": "example.com",
                "record_names": ["app.example.com", "api.example.com"]
            }
        },
        DeploymentConfig(
            workload={"workload": {"name": "test-workload", "devops": {"name": "test-devops"}}},
            deployment={"name": "test-deployment"}
        )
    )
    
    assert full_config.name == "full-lb"
    assert full_config.type == "NETWORK"
    assert full_config.vpc_id == "vpc-67890"
    assert full_config.internet_facing is True
    assert full_config.deletion_protection is True
    assert full_config.idle_timeout == 120
    assert full_config.http2_enabled is False
    assert full_config.security_groups == ["sg-12345", "sg-67890"]
    assert full_config.subnets == ["subnet-1", "subnet-2", "subnet-3"]
    assert len(full_config.target_groups) == 1
    assert full_config.target_groups[0]["name"] == "app-tg"
    assert len(full_config.listeners) == 1
    assert full_config.listeners[0]["port"] == 80
    assert full_config.hosted_zone["id"] == "Z1234567890"
    assert full_config.hosted_zone["name"] == "example.com"
    assert full_config.hosted_zone["record_names"] == ["app.example.com", "api.example.com"]
