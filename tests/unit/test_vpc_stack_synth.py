"""Tests for VPC stack synthesis"""
import json
import sys
import os
from pathlib import Path
import pytest
from aws_cdk import App

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


@pytest.fixture
def dummy_workload():
    """Create a dummy workload config for testing"""
    return WorkloadConfig(
        {
            "name": "dummy-workload",
            "description": "Dummy workload for testing",
            "devops": {
                "account": "123456789012",
                "region": "us-east-1",
                "commands": []
            },
            "stacks": [
                {
                    "name": "vpc-test",
                    "module": "vpc_library_module",
                    "enabled": True,
                    "vpc": {
                        "name": "test-vpc",
                        "cidr": "10.0.0.0/16",
                        "max_azs": 2,
                        "nat_gateways": {"count": 1},
                    },
                }
            ],
        }
    )


def test_vpc_stack_synth(dummy_workload):
    """Test that the VPC stack can be synthesized without errors"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "vpc-test",
            "module": "vpc_library_module",
            "enabled": True,
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "nat_gateways": {"count": 1},
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = VpcStack(app, "TestVpcStack")
    stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestVpcStack").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a VPC
    vpc_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::VPC"]
    assert len(vpc_resources) == 1
    
    # Check that we have NAT Gateways
    nat_gateway_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::NatGateway"]
    assert len(nat_gateway_resources) > 0
    
    # Check that the NAT Gateway has a name tag
    for nat_gateway in nat_gateway_resources:
        tags = nat_gateway.get("Properties", {}).get("Tags", [])
        name_tags = [t for t in tags if t.get("Key") == "Name"]
        assert len(name_tags) == 1
        # Just verify the tag exists with some value
        assert name_tags[0].get("Value", "") != ""


def test_vpc_stack_with_custom_subnet_names(dummy_workload):
    """Test that the VPC stack can be synthesized with custom subnet names"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "vpc-test",
            "module": "vpc_library_module",
            "enabled": True,
            "vpc": {
                "name": "test-vpc",
                "cidr": "10.0.0.0/16",
                "max_azs": 2,
                "public_subnet_name": "web-tier",
                "private_subnet_name": "app-tier",
                "isolated_subnet_name": "data-tier",
                "nat_gateways": {"count": 1},
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = VpcStack(app, "TestVpcCustomSubnets")
    stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestVpcCustomSubnets").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have subnets with custom names
    subnet_resources = [r for r in resources.values() if r.get("Type") == "AWS::EC2::Subnet"]
    assert len(subnet_resources) > 0
    
    # Check that the subnets have the correct name tags
    public_subnets = []
    private_subnets = []
    
    for subnet in subnet_resources:
        tags = subnet.get("Properties", {}).get("Tags", [])
        name_tags = [t for t in tags if t.get("Key") == "Name"]
        if name_tags:
            name_value = name_tags[0].get("Value", "")
            if "web-tier" in name_value:
                public_subnets.append(subnet)
            elif "app-tier" in name_value:
                private_subnets.append(subnet)
    
    # We should have at least one public and one private subnet
    assert len(public_subnets) > 0
    assert len(private_subnets) > 0
