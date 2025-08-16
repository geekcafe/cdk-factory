"""
Unit tests for the Security Group Stack
"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.security_group.security_group_stack import SecurityGroupStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_security_group_stack_minimal():
    """Test Security Group stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "security_group": {
                "name": "test-sg",
                "description": "Test security group",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = SecurityGroupStack(app, "TestSecurityGroupStack")
    
    # Mock VPC
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    
    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc
    
    # Mock the security group
    mock_sg = MagicMock()
    mock_sg.security_group_id = "sg-12345"
    
    # Mock the _create_security_group method
    with patch.object(SecurityGroupStack, "_create_security_group", return_value=mock_sg) as mock_create_sg:
        with patch.object(SecurityGroupStack, "_add_outputs") as mock_add_outputs:
            # Build the stack
            stack.build(stack_config, deployment, dummy_workload)
            
            # Verify the Security Group config was correctly loaded
            assert stack.sg_config.name == "test-sg"
            assert stack.sg_config.description == "Test security group"
            assert stack.sg_config.allow_all_outbound is True  # Default value
            
            # Verify the security group was created
            assert stack.security_group is mock_sg
            
            # Verify methods were called
            mock_create_sg.assert_called_once()
            mock_add_outputs.assert_called_once()


def test_security_group_stack_full_config():
    """Test Security Group stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "security_group": {
                "name": "full-sg",
                "description": "Full security group",
                "vpc_id": "vpc-67890",
                "allow_all_outbound": False,
                "ingress_rules": [
                    {
                        "description": "Allow HTTP from anywhere",
                        "port": 80,
                        "cidr_ranges": ["0.0.0.0/0"]
                    },
                    {
                        "description": "Allow HTTPS from anywhere",
                        "port": 443,
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ],
                "egress_rules": [
                    {
                        "description": "Allow all outbound HTTPS",
                        "port": 443,
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ],
                "peer_security_groups": [
                    {
                        "security_group_id": "sg-67890",
                        "ingress_rules": [
                            {
                                "description": "Allow SSH from bastion",
                                "port": 22
                            }
                        ]
                    }
                ],
                "tags": {
                    "Environment": "test",
                    "Project": "cdk-factory"
                }
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create and build the stack
    stack = SecurityGroupStack(app, "FullSecurityGroupStack")
    
    # Mock VPC
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-67890"
    
    # Mock peer security group
    mock_peer_sg = MagicMock()
    mock_peer_sg.security_group_id = "sg-67890"
    
    # Mock the security group
    mock_sg = MagicMock()
    mock_sg.security_group_id = "sg-12345"
    
    # Mock the methods
    with patch.object(SecurityGroupStack, "_get_vpc", return_value=mock_vpc) as mock_get_vpc:
        with patch.object(SecurityGroupStack, "_create_security_group", return_value=mock_sg) as mock_create_sg:
            with patch.object(SecurityGroupStack, "_add_ingress_rules") as mock_add_ingress:
                with patch.object(SecurityGroupStack, "_add_egress_rules") as mock_add_egress:
                    with patch.object(SecurityGroupStack, "_add_peer_security_group_rules") as mock_add_peer:
                        with patch.object(SecurityGroupStack, "_add_outputs") as mock_add_outputs:
                                # Build the stack
                                stack.build(stack_config, deployment, dummy_workload)
                                
                                # Verify the Security Group config was correctly loaded
                                assert stack.sg_config.name == "full-sg"
                                assert stack.sg_config.description == "Full security group"
                                assert stack.sg_config.vpc_id == "vpc-67890"
                                assert stack.sg_config.allow_all_outbound is False
                                assert len(stack.sg_config.ingress_rules) == 2
                                assert stack.sg_config.ingress_rules[0]["port"] == 80
                                assert len(stack.sg_config.egress_rules) == 1
                                assert stack.sg_config.egress_rules[0]["port"] == 443
                                assert len(stack.sg_config.peer_security_groups) == 1
                                assert stack.sg_config.peer_security_groups[0]["security_group_id"] == "sg-67890"
                                assert stack.sg_config.tags == {"Environment": "test", "Project": "cdk-factory"}
                                
                                # Verify the security group was created
                                assert stack.security_group is mock_sg
                                
                                # Verify methods were called
                                mock_get_vpc.assert_called_once()
                                mock_create_sg.assert_called_once()
                                mock_add_ingress.assert_called_once()
                                mock_add_egress.assert_called_once()
                                mock_add_peer.assert_called_once()
                                mock_add_outputs.assert_called_once()


def test_security_group_stack_import_existing():
    """Test Security Group stack with importing an existing security group"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "security_group": {
                "name": "imported-sg",
                "existing_security_group_id": "sg-abcdef",
                "ingress_rules": [
                    {
                        "description": "Allow SSH from anywhere",
                        "port": 22,
                        "cidr_ranges": ["0.0.0.0/0"]
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
    
    # Create and build the stack
    stack = SecurityGroupStack(app, "ImportSecurityGroupStack")
    
    # Mock the security group
    mock_sg = MagicMock()
    mock_sg.security_group_id = "sg-abcdef"
    
    # Mock VPC
    mock_vpc = MagicMock()
    mock_vpc.vpc_id = "vpc-12345"
    
    # Mock the workload object with VPC
    dummy_workload.vpc = mock_vpc
    
    # Mock the methods
    with patch.object(SecurityGroupStack, "_get_vpc", return_value=mock_vpc) as mock_get_vpc:
        with patch.object(SecurityGroupStack, "_import_existing_security_group", return_value=mock_sg) as mock_import_sg:
            with patch.object(SecurityGroupStack, "_add_ingress_rules") as mock_add_ingress:
                with patch.object(SecurityGroupStack, "_add_outputs") as mock_add_outputs:
                    # Build the stack
                    stack.build(stack_config, deployment, dummy_workload)
                    
                    # Verify the Security Group config was correctly loaded
                    assert stack.sg_config.name == "imported-sg"
                    assert stack.sg_config.existing_security_group_id == "sg-abcdef"
                    assert len(stack.sg_config.ingress_rules) == 1
                    assert stack.sg_config.ingress_rules[0]["port"] == 22
                    
                    # Verify the security group was imported
                    assert stack.security_group is mock_sg
                    
                    # Verify methods were called
                    mock_get_vpc.assert_called_once()
                    mock_import_sg.assert_called_once()
                    mock_add_ingress.assert_called_once()
                    mock_add_outputs.assert_called_once()
