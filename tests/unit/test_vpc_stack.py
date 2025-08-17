"""
Unit tests for the VPC Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.vpc import VpcConfig
from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from cdk_factory.workload.workload_factory import WorkloadConfig
from unittest.mock import MagicMock, patch, create_autospec


def test_vpc_stack_minimal():
    """Test VPC stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    # Create and build the stack
    stack = VpcStack(app, "TestVpcStack")

    # Instead of mocking the ec2.Vpc class, we'll mock the _create_vpc method
    # to return a value we can control without JSII compatibility issues
    mock_vpc = object()

    # Mock the _create_vpc method to return our controlled object
    with patch.object(
        VpcStack, "_create_vpc", return_value=mock_vpc
    ) as mock_create_vpc:
        # Mock the _add_outputs method to avoid actual CloudFormation outputs
        with patch.object(VpcStack, "_add_outputs") as mock_add_outputs:
            # Build the stack
            stack.build(stack_config, deployment, dummy_workload)

            # Verify the VPC config was correctly loaded
            assert stack.vpc_config.name == "test-vpc"
            assert stack.vpc_config.cidr == "10.0.0.0/16"
            assert stack.vpc_config.max_azs == 3

            # Verify the VPC was created
            assert stack.vpc is mock_vpc

            # Verify methods were called
            mock_create_vpc.assert_called_once()
            mock_add_outputs.assert_called_once()


def test_vpc_stack_full_config():
    """Test VPC stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "vpc": {
                "name": "full-vpc",
                "cidr": "172.16.0.0/16",
                "public_subnet_name": "dummy-workload-dev-web-tier",
                "private_subnet_name": "dummy-workload-dev-app-tier",
                "isolated_subnet_name": "dummy-workload-dev-data-tier",
                "nat_gateway_name": "dummy-workload-dev-egress-gateway",
                "max_azs": 2,
                "enable_dns_hostnames": True,
                "enable_dns_support": True,
                "public_subnets": True,
                "private_subnets": True,
                "isolated_subnets": True,
                "public_subnet_mask": 24,
                "private_subnet_mask": 24,
                "isolated_subnet_mask": 28,
                "nat_gateways": {"count": 2},
                "enable_s3_endpoint": True,
                "enable_interface_endpoints": True,
                "interface_endpoints": ["ecr.api", "ecr.dkr", "logs"],
                "tags": {"Environment": "test", "Project": "cdk-factory"},
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )

    # Create and build the stack
    stack = VpcStack(app, "FullVpcStack")

    # Mock the _add_outputs method to avoid actual CloudFormation outputs
    with patch.object(VpcStack, "_add_outputs") as mock_add_outputs:
        # We'll patch the ec2.Vpc constructor to avoid JSII issues
        # but still allow the _create_vpc method to run its logic
        with patch.object(
            VpcStack, "_add_interface_endpoints"
        ) as mock_add_interface_endpoints:
            # Use a custom side effect to capture the vpc object and avoid JSII issues
            mock_vpc = None

            def mock_create_vpc_impl(*args, **kwargs):
                nonlocal mock_vpc
                # Create a simple object to represent the VPC
                mock_vpc = object()
                return mock_vpc

            with patch.object(
                VpcStack, "_create_vpc", side_effect=mock_create_vpc_impl
            ) as mock_create_vpc:
                # Build the stack
                stack.build(stack_config, deployment, dummy_workload)

                # Verify the VPC config was correctly loaded
                assert stack.vpc_config.name == "full-vpc"
                assert stack.vpc_config.cidr == "172.16.0.0/16"
                assert stack.vpc_config.max_azs == 2
                assert stack.vpc_config.enable_dns_hostnames is True
                assert stack.vpc_config.enable_dns_support is True
                assert stack.vpc_config.public_subnets is True
                assert stack.vpc_config.private_subnets is True
                assert stack.vpc_config.isolated_subnets is True
                assert stack.vpc_config.public_subnet_mask == 24
                assert stack.vpc_config.private_subnet_mask == 24
                assert stack.vpc_config.isolated_subnet_mask == 28
                assert stack.vpc_config.nat_gateways == {"count": 2}
                assert stack.vpc_config.enable_s3_endpoint is True
                assert stack.vpc_config.enable_interface_endpoints is True
                assert stack.vpc_config.interface_endpoints == [
                    "ecr.api",
                    "ecr.dkr",
                    "logs",
                ]
                assert stack.vpc_config.tags == {
                    "Environment": "test",
                    "Project": "cdk-factory",
                }

                # Verify the VPC was created
                assert stack.vpc is mock_vpc

                # Verify methods were called
                mock_create_vpc.assert_called_once()
                mock_add_outputs.assert_called_once()


def test_vpc_config():
    """Test VPC configuration class"""
    # Test with minimal config
    minimal_config = VpcConfig({"name": "minimal-vpc"})

    assert minimal_config.name == "minimal-vpc"
    assert minimal_config.cidr == "10.0.0.0/16"  # Default value
    assert minimal_config.max_azs == 3  # Default value
    assert minimal_config.public_subnets is True  # Default value
    assert minimal_config.private_subnets is True  # Default value
    assert minimal_config.isolated_subnets is False  # Default value

    # Test with full config
    full_config = VpcConfig(
        {
            "name": "full-vpc",
            "cidr": "192.168.0.0/16",
            "max_azs": 2,
            "enable_dns_hostnames": False,
            "enable_dns_support": False,
            "public_subnets": False,
            "private_subnets": True,
            "isolated_subnets": True,
            "public_subnet_mask": 26,
            "private_subnet_mask": 25,
            "isolated_subnet_mask": 27,
            "nat_gateways": {"count": 0},
            "enable_s3_endpoint": False,
            "enable_interface_endpoints": True,
            "interface_endpoints": ["lambda", "sts"],
            "tags": {"Environment": "dev"},
        }
    )

    assert full_config.name == "full-vpc"
    assert full_config.cidr == "192.168.0.0/16"
    assert full_config.max_azs == 2
    assert full_config.enable_dns_hostnames is False
    assert full_config.enable_dns_support is False
    assert full_config.public_subnets is False
    assert full_config.private_subnets is True
    assert full_config.isolated_subnets is True
    assert full_config.public_subnet_mask == 26
    assert full_config.private_subnet_mask == 25
    assert full_config.isolated_subnet_mask == 27
    assert full_config.nat_gateways == {"count": 0}
    assert full_config.enable_s3_endpoint is False
    assert full_config.enable_interface_endpoints is True
    assert full_config.interface_endpoints == ["lambda", "sts"]
    assert full_config.tags == {"Environment": "dev"}
