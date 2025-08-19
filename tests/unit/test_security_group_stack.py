"""Tests for Security Group stack synthesis - Best practices approach"""

import pytest
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2

from cdk_factory.stack_library.security_group.security_group_stack import (
    SecurityGroupStack,
)
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from utils.synth_test_utils import (
    get_resources_by_type,
    assert_resource_count,
    assert_has_resource_with_properties,
    assert_has_tag,
    find_tag_value,
)
from aws_cdk import Environment


# Create a testable subclass of SecurityGroupStack
class TestableSecurityGroupStack(SecurityGroupStack):
    """A testable version of SecurityGroupStack that overrides problematic methods"""

    def __init__(self, scope, id):
        env = Environment(account="123456789012", region="us-east-1")
        super().__init__(scope, id, env=env)
        self._mock_vpc = None
        # Enable test mode by default in the test subclass
        self.set_test_mode(True)

    def _get_vpc(self):
        """Override to return a mock VPC"""
        if self._mock_vpc:
            return self._mock_vpc

        return ec2.Vpc.from_vpc_attributes(
            self,
            "ImportedVpc",
            vpc_id="vpc-12345",
            availability_zones=["us-east-1a", "us-east-1b"],
            private_subnet_ids=["subnet-1", "subnet-2"],
            public_subnet_ids=["subnet-3", "subnet-4"],
        )

    def set_mock_vpc(self, mock_vpc):
        """Set the mock VPC to be returned by _get_vpc"""
        self._mock_vpc = mock_vpc


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
                "commands": [],
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
                                "cidr_ranges": ["0.0.0.0/0"],
                            }
                        ],
                    },
                },
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
                        "cidr_ranges": ["0.0.0.0/0"],
                    }
                ],
            },
        },
        workload=dummy_workload.dictionary,
    )

    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )

    # Create and build the stack using our testable subclass
    stack = TestableSecurityGroupStack(app, "TestSecurityGroupStack")

    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"

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
    assert (
        sg_resource["Properties"]["SecurityGroupEgress"] is not None
    )  # Should have egress rules

    # Check that the security group has the correct name tag if Tags are present
    if "Tags" in sg_resource["Properties"]:
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

    # Create the stack config with peer security groups
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
                        "cidr_ranges": ["10.0.0.0/16"],
                    }
                ],
                "egress_rules": [
                    {
                        "description": "Allow HTTPS outbound",
                        "port": 443,
                        "cidr_ranges": ["0.0.0.0/0"],
                    }
                ],
                "peer_security_groups": [
                    {
                        "security_group_id": "sg-0123456789abcdef0",
                        "ingress_rules": [
                            {"description": "Allow DB access", "port": 5432}
                        ],
                    }
                ],
            },
        },
        workload=dummy_workload.dictionary,
    )

    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )

    # Create and build the stack using our testable subclass
    stack = TestableSecurityGroupStack(app, "TestSecurityGroupWithPeers")

    # Set the VPC ID on the workload
    dummy_workload.vpc_id = "vpc-12345"

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
    assert (
        sg_resource["Properties"]["GroupDescription"]
        == "Test security group with peer rules"
    )
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
    # We expect 2 ingress rules: one for SSH and one for the peer security group
    assert len(ingress_rules) == 2

    # Check the SSH ingress rule properties
    ssh_rule = next(rule for rule in ingress_rules if rule.get("FromPort") == 22)
    assert ssh_rule["IpProtocol"] == "tcp"
    assert ssh_rule["ToPort"] == 22
    assert ssh_rule["CidrIp"] == "10.0.0.0/16"
    assert ssh_rule["Description"] == "Allow SSH"

    # Check that we have peer security group rules in the ingress rules
    # Find the peer security group rule in the ingress rules
    peer_sg_rule = next(
        (
            rule
            for rule in ingress_rules
            if rule.get("SourceSecurityGroupId") == "sg-0123456789abcdef0"
        ),
        None,
    )

    # If peer security group rule is found, validate its properties
    if peer_sg_rule:
        assert peer_sg_rule["IpProtocol"] == "tcp"
        assert peer_sg_rule["FromPort"] == 5432
        assert peer_sg_rule["ToPort"] == 5432
        assert peer_sg_rule["Description"] == "Allow DB access"
