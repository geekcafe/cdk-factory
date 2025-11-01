"""Unit tests for the Load Balancer Stack"""

import unittest
from unittest.mock import patch, MagicMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match
from aws_cdk import aws_ec2 as ec2

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.load_balancer import LoadBalancerConfig
from cdk_factory.stack_library.load_balancer.load_balancer_stack import (
    LoadBalancerStack,
)
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestLoadBalancerStack(unittest.TestCase):
    """Test cases for LoadBalancerStack"""

    def test_minimal_alb_configuration(self):
        """Test Load Balancer stack with minimal ALB configuration"""
        app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )

        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "dummy-workload",
                    "devops": {"name": "dummy-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-lb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 80,
                            "protocol": "HTTP",
                            "health_check": {
                                "path": "/health",
                                "interval": 30,
                                "timeout": 5,
                                "healthy_threshold": 2,
                                "unhealthy_threshold": 5,
                            },
                        }
                    ],
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "dummy-deployment", "environment": "test"},
        )

        # Create and build the stack
        stack = LoadBalancerStack(app, "TestStack")
        # Create a VPC directly in the stack scope
        vpc = ec2.Vpc(stack, "TestVpc", max_azs=2)
        # Override the VPC property to use our test VPC
        stack._vpc = vpc
        stack.build(stack_config, deployment, dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify ALB was created
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {"Type": "application", "Scheme": "internet-facing"},
        )

        # Verify stack configuration was loaded correctly
        self.assertEqual(stack.lb_config.name, "test-lb")
        self.assertEqual(stack.lb_config.type, "APPLICATION")
        self.assertTrue(stack.lb_config.internet_facing)

    def test_full_alb_configuration(self):
        """Test Load Balancer stack with full ALB configuration"""
        app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "dummy-workload",
                    "devops": {"name": "dummy-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "full-lb",
                    "type": "APPLICATION",
                    "vpc_id": "vpc-12345678",
                    "internet_facing": True,
                    "deletion_protection": False,
                    "idle_timeout": 120,
                    "http2_enabled": True,
                    "security_groups": ["sg-12345678"],
                    "subnets": ["subnet-12345678", "subnet-87654321"],
                    "target_groups": [
                        {
                            "name": "web-servers",
                            "port": 80,
                            "protocol": "HTTP",
                            "target_type": "INSTANCE",
                            "health_check": {
                                "path": "/health",
                                "port": "traffic-port",
                                "healthy_threshold": 2,
                                "unhealthy_threshold": 5,
                                "timeout": 5,
                                "interval": 30,
                                "healthy_http_codes": "200",
                            },
                        },
                        {
                            "name": "api-servers",
                            "port": 8080,
                            "protocol": "HTTP",
                            "target_type": "INSTANCE",
                        },
                    ],
                    "listeners": [
                        {
                            "name": "http-listener",
                            "port": 80,
                            "protocol": "HTTP",
                            "default_target_group": "web-servers",
                            "rules": [
                                {
                                    "priority": 100,
                                    "path_patterns": ["/api/*"],
                                    "target_group": "api-servers",
                                }
                            ],
                        }
                    ],
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )

        # Create and build the stack
        stack = LoadBalancerStack(app, "FullLoadBalancerStack")
        # Create a VPC directly in the stack scope
        vpc = ec2.Vpc(stack, "TestVpc2", max_azs=2)
        # Override the VPC property to use our test VPC
        stack._vpc = vpc
        stack.build(stack_config, deployment, dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify ALB was created with correct properties
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Type": "application",
                "Scheme": "internet-facing",
            },
        )

        # Verify specific load balancer attributes are present
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "LoadBalancerAttributes": Match.array_with(
                    [{"Key": "idle_timeout.timeout_seconds", "Value": "120"}]
                )
            },
        )

        # Verify target groups were created
        template.resource_count_is("AWS::ElasticLoadBalancingV2::TargetGroup", 2)

        # Verify listeners were created
        template.resource_count_is("AWS::ElasticLoadBalancingV2::Listener", 1)

        # Verify listener rules were created
        template.resource_count_is("AWS::ElasticLoadBalancingV2::ListenerRule", 1)

        # Verify configuration was loaded correctly
        self.assertEqual(stack.lb_config.name, "full-lb")
        self.assertEqual(stack.lb_config.type, "APPLICATION")
        self.assertEqual(stack.lb_config.idle_timeout, 120)
        self.assertTrue(stack.lb_config.http2_enabled)
        self.assertEqual(len(stack.lb_config.target_groups), 2)
        self.assertEqual(len(stack.lb_config.listeners), 1)

    def test_network_load_balancer_configuration(self):
        """Test Load Balancer stack with Network Load Balancer configuration"""
        app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "dummy-workload",
                    "devops": {"name": "dummy-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "nlb-test",
                    "type": "NETWORK",
                    "vpc_id": "vpc-12345678",
                    "subnets": ["subnet-12345678", "subnet-87654321"],
                    "internet_facing": True,
                    "target_groups": [
                        {
                            "name": "tcp-servers",
                            "port": 80,
                            "protocol": "TCP",
                            "target_type": "INSTANCE",
                        }
                    ],
                    "listeners": [
                        {
                            "name": "tcp-listener",
                            "port": 80,
                            "protocol": "TCP",
                            "default_target_group": "tcp-servers",
                        }
                    ],
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )

        # Create and build the stack
        stack = LoadBalancerStack(app, "NLBTestStack")
        # Create a VPC directly in the stack scope
        vpc = ec2.Vpc(stack, "TestVpc3", max_azs=2)
        # Override the VPC property to use our test VPC
        stack._vpc = vpc
        stack.build(stack_config, deployment, dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify NLB was created
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {"Type": "network", "Scheme": "internet-facing"},
        )

        # Verify target group was created with TCP protocol
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::TargetGroup",
            {"Protocol": "TCP", "Port": 80, "TargetType": "instance"},
        )

        # Verify listener was created
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener", {"Protocol": "TCP", "Port": 80}
        )

        # Verify configuration
        self.assertEqual(stack.lb_config.name, "nlb-test")
        self.assertEqual(stack.lb_config.type, "NETWORK")

    def test_ssm_parameter_export(self):
        """Test Load Balancer stack with SSM parameter export configuration"""
        app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "dummy-workload",
                    "devops": {"name": "dummy-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "ssm-lb",
                    "type": "APPLICATION",
                    "vpc_id": "vpc-12345678",
                    "subnets": ["subnet-12345678", "subnet-87654321"],
                    "security_groups": ["sg-12345678"],
                    "target_groups": [
                        {"name": "web-servers", "port": 80, "protocol": "HTTP"}
                    ],
                    "ssm": {
                        "exports": {
                            "alb_dns_name": "/my-app/alb/dns-name",
                            "alb_arn": "/my-app/alb/arn",
                            "target_group_web-servers_arn": "/my-app/alb/web-servers-arn",
                        },
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )

        # Create and build the stack
        stack = LoadBalancerStack(app, "SSMTestStack")
        # Create a VPC directly in the stack scope
        vpc = ec2.Vpc(stack, "TestVpc4", max_azs=2)
        # Override the VPC property to use our test VPC
        stack._vpc = vpc
        stack.build(stack_config, deployment, dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # make sure our parameters are created
        template.resource_count_is("AWS::SSM::Parameter", 3)

        # Verify that the load balancer was created successfully
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {"Type": "application", "Name": "ssm-lb"},
        )

    def test_load_balancer_config(self):
        """Test LoadBalancerConfig class"""
        # Test with minimal configuration
        minimal_config = LoadBalancerConfig(
            {"name": "minimal-lb", "type": "APPLICATION", "vpc_id": "vpc-12345"},
            DeploymentConfig(
                workload={
                    "workload": {
                        "name": "test-workload",
                        "devops": {"name": "test-devops"},
                    }
                },
                deployment={"name": "test-deployment", "environment": "test"},
            ),
        )

        self.assertEqual(minimal_config.name, "minimal-lb")
        self.assertEqual(minimal_config.type, "APPLICATION")
        self.assertEqual(minimal_config.vpc_id, "vpc-12345")
        self.assertTrue(minimal_config.internet_facing)  # Default value
        self.assertFalse(minimal_config.deletion_protection)  # Default value
        self.assertEqual(minimal_config.idle_timeout, 60)  # Default value
        self.assertTrue(minimal_config.http2_enabled)  # Default value
        self.assertEqual(minimal_config.security_groups, [])  # Default value
        self.assertEqual(minimal_config.subnets, [])  # Default value
        self.assertEqual(minimal_config.target_groups, [])  # Default value
        self.assertEqual(minimal_config.listeners, [])  # Default value
        self.assertEqual(minimal_config.hosted_zone, {})  # Default value

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
                "target_groups": [{"name": "app-tg", "port": 80, "protocol": "TCP"}],
                "listeners": [
                    {"port": 80, "protocol": "TCP", "default_target_group": "app-tg"}
                ],
                "hosted_zone": {
                    "id": "Z1234567890",
                    "name": "example.com",
                    "record_names": ["app.example.com", "api.example.com"],
                },
            },
            DeploymentConfig(
                workload={
                    "workload": {
                        "name": "test-workload",
                        "devops": {"name": "test-devops"},
                    }
                },
                deployment={"name": "test-deployment", "environment": "test"},
            ),
        )

        self.assertEqual(full_config.name, "full-lb")
        self.assertEqual(full_config.type, "NETWORK")
        self.assertEqual(full_config.vpc_id, "vpc-67890")
        self.assertTrue(full_config.internet_facing)
        self.assertTrue(full_config.deletion_protection)
        self.assertEqual(full_config.idle_timeout, 120)
        self.assertFalse(full_config.http2_enabled)
        self.assertEqual(full_config.security_groups, ["sg-12345", "sg-67890"])
        self.assertEqual(full_config.subnets, ["subnet-1", "subnet-2", "subnet-3"])
        self.assertEqual(len(full_config.target_groups), 1)
        self.assertEqual(full_config.target_groups[0]["name"], "app-tg")
        self.assertEqual(len(full_config.listeners), 1)
        self.assertEqual(full_config.listeners[0]["port"], 80)
        self.assertEqual(full_config.hosted_zone["id"], "Z1234567890")
        self.assertEqual(full_config.hosted_zone["name"], "example.com")
        self.assertEqual(
            full_config.hosted_zone["record_names"],
            ["app.example.com", "api.example.com"],
        )


if __name__ == "__main__":
    unittest.main()
