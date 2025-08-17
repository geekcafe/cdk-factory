"""Tests for Security Group stack synthesis"""
import pytest
from unittest.mock import patch, MagicMock
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2
from aws_cdk.aws_ec2 import Protocol

from cdk_factory.stack_library.security_group.security_group_stack import SecurityGroupStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from utils.synth_test_utils import (
    get_resources_by_type,
    assert_resource_count,
    assert_has_resource_with_properties,
    assert_has_tag,
    find_tag_value
)


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
                    },
                },
                {
                    "name": "sg-test",
                    "module": "security_group_library_module",
                    "enabled": True,
                    "security_group": {
                        "name": "test-sg",
                        "description": "Test security group",
                        "vpc_id": "vpc-12345",
                        "allow_all_outbound": True,
                        "ingress_rules": [
                            {
                                "description": "Allow HTTP",
                                "port": 80,
                                "cidr_ranges": ["0.0.0.0/0"]
                            }
                        ]
                    },
                }
            ],
        }
    )


def test_security_group_stack_synth(dummy_workload):
    """Test that the Security Group stack can be synthesized without errors"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "sg-test",
            "module": "security_group_library_module",
            "enabled": True,
            "security_group": {
                "name": "test-sg",
                "description": "Test security group",
                "vpc_id": "vpc-12345",
                "allow_all_outbound": True,
                "ingress_rules": [
                    {
                        "description": "Allow HTTP",
                        "port": 80,
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ]
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
    stack = SecurityGroupStack(app, "TestSecurityGroupStack")
    
    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"
    
    # Patch the _get_vpc method to use a direct import instead of lookup
    with patch.object(SecurityGroupStack, '_get_vpc') as mock_get_vpc:
        mock_get_vpc.return_value = ec2.Vpc.from_vpc_attributes(
            stack, "ImportedVpc",
            vpc_id="vpc-12345",
            availability_zones=["us-east-1a", "us-east-1b"],
            private_subnet_ids=["subnet-1", "subnet-2"],
            public_subnet_ids=["subnet-3", "subnet-4"]
        )
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestSecurityGroupStack").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a security group
    sg_resources = get_resources_by_type(template, "AWS::EC2::SecurityGroup")
    assert len(sg_resources) == 1
    
    # Get the security group resource
    sg_resource = sg_resources[0]["resource"]
    
    # Check security group properties
    assert sg_resource["Properties"]["GroupDescription"] == "Test security group"
    assert sg_resource["Properties"]["VpcId"] == "vpc-12345"
    assert sg_resource["Properties"]["SecurityGroupEgress"] is not None  # Should have egress rules
    
    # Check that the security group has the correct name tag
    tags = sg_resource["Properties"]["Tags"]
    name_tag_value = find_tag_value(tags, "Name")
    assert "test-sg" in name_tag_value
    
    # Check that we have ingress rules
    ingress_rules = sg_resource["Properties"]["SecurityGroupIngress"]
    assert len(ingress_rules) == 1
    
    # Check the ingress rule properties
    ingress_rule = ingress_rules[0]
    assert ingress_rule["IpProtocol"] == "tcp"
    assert ingress_rule["FromPort"] == 80
    assert ingress_rule["ToPort"] == 80
    assert ingress_rule["CidrIp"] == "0.0.0.0/0"
    assert ingress_rule["Description"] == "Allow HTTP"


def test_security_group_with_peer_rules(dummy_workload):
    """Test that the Security Group stack can be synthesized with peer security group rules"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "sg-test",
            "module": "security_group_library_module",
            "enabled": True,
            "security_group": {
                "name": "test-sg-with-peers",
                "description": "Test security group with peer rules",
                "vpc_id": "vpc-12345",
                "allow_all_outbound": False,
                "ingress_rules": [
                    {
                        "description": "Allow SSH",
                        "port": 22,
                        "cidr_ranges": ["10.0.0.0/16"]
                    }
                ],
                "egress_rules": [
                    {
                        "description": "Allow HTTPS outbound",
                        "port": 443,
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ],
                "peer_security_groups": [
                    {
                        "security_group_id": "sg-67890",
                        "ingress_rules": [
                            {
                                "description": "Allow DB access",
                                "port": 5432
                            }
                        ]
                    }
                ]
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
    stack = SecurityGroupStack(app, "TestSecurityGroupWithPeers")
    
    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"
    
    # Patch the _get_vpc method to use a direct import instead of lookup
    with patch.object(SecurityGroupStack, '_get_vpc') as mock_get_vpc:
        mock_get_vpc.return_value = ec2.Vpc.from_vpc_attributes(
            stack, "ImportedVpc",
            vpc_id="vpc-12345",
            availability_zones=["us-east-1a", "us-east-1b"],
            private_subnet_ids=["subnet-1", "subnet-2"],
            public_subnet_ids=["subnet-3", "subnet-4"]
        )
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestSecurityGroupWithPeers").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a security group
    sg_resources = get_resources_by_type(template, "AWS::EC2::SecurityGroup")
    assert len(sg_resources) == 1
    
    # Get the security group resource
    sg_resource = sg_resources[0]["resource"]
    
    # Check security group properties
    assert sg_resource["Properties"]["GroupDescription"] == "Test security group with peer rules"
    assert sg_resource["Properties"]["VpcId"] == "vpc-12345"
    
    # Check that the security group has egress rules
    egress_rules = sg_resource["Properties"]["SecurityGroupEgress"]
    assert len(egress_rules) == 1
    
    # Check the egress rule properties
    egress_rule = egress_rules[0]
    assert egress_rule["IpProtocol"] == "tcp"
    assert egress_rule["FromPort"] == 443
    assert egress_rule["ToPort"] == 443
    assert egress_rule["CidrIp"] == "0.0.0.0/0"
    assert egress_rule["Description"] == "Allow HTTPS outbound"
    
    # Check that we have ingress rules
    ingress_rules = sg_resource["Properties"]["SecurityGroupIngress"]
    assert len(ingress_rules) == 1
    
    # Check the ingress rule properties
    ingress_rule = ingress_rules[0]
    assert ingress_rule["IpProtocol"] == "tcp"
    assert ingress_rule["FromPort"] == 22
    assert ingress_rule["ToPort"] == 22
    assert ingress_rule["CidrIp"] == "10.0.0.0/16"
    assert ingress_rule["Description"] == "Allow SSH"
    
    # Check that we have peer security group rules
    peer_sg_rules = [r for r in resources.values() if r.get("Type") == "AWS::EC2::SecurityGroupIngress"]
    assert len(peer_sg_rules) == 1
    
    # Check the peer security group rule properties
    peer_sg_rule = list(peer_sg_rules.values())[0]
    assert peer_sg_rule["Properties"]["IpProtocol"] == "tcp"
    assert peer_sg_rule["Properties"]["FromPort"] == 5432
    assert peer_sg_rule["Properties"]["ToPort"] == 5432
    assert peer_sg_rule["Properties"]["GroupId"] == "sg-67890"
    assert peer_sg_rule["Properties"]["Description"] == "Allow DB access"
