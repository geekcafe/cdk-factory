"""Unit tests for Load Balancer Stack SSM Import Features"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ssm as ssm

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.load_balancer.load_balancer_stack import LoadBalancerStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestLoadBalancerSSMImports(unittest.TestCase):
    """Test cases for Load Balancer Stack SSM import functionality"""

    def setUp(self):
        """Set up common test fixtures"""
        self.app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
        self.dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        self.deployment = DeploymentConfig(
            workload=self.dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "prod"},
        )

    def test_alb_subnet_ids_ssm_import_with_fn_split(self):
        """Test ALB imports subnet IDs from SSM and uses Fn::Split for comma-separated values"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                        }
                    },
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 80,
                            "protocol": "HTTP",
                        }
                    ],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBSubnetSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify SSM parameters are imported (check they exist, not exact names)
        params = template_dict.get("Parameters", {})
        vpc_id_params = [p for p in params if "importvpcid" in p.lower()]
        subnet_id_params = [p for p in params if "importsubnetids" in p.lower()]
        
        assert len(vpc_id_params) == 1, f"Expected 1 VPC ID parameter, found {len(vpc_id_params)}"
        assert len(subnet_id_params) == 1, f"Expected 1 subnet IDs parameter, found {len(subnet_id_params)}"
        
        assert params[vpc_id_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[vpc_id_params[0]]["Default"] == "/prod/app/vpc/id"
        
        assert params[subnet_id_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[subnet_id_params[0]]["Default"] == "/prod/app/vpc/public-subnet-ids"

        # Verify ALB resource exists with Fn::Split for subnets
        alb_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::ElasticLoadBalancingV2::LoadBalancer"}
        assert len(alb_resources) == 1, "Expected 1 ALB resource"
        
        alb = list(alb_resources.values())[0]
        assert alb["Properties"]["Type"] == "application"
        assert alb["Properties"]["Scheme"] == "internet-facing"
        assert "Fn::Split" in alb["Properties"]["Subnets"]
        assert alb["Properties"]["Subnets"]["Fn::Split"][0] == ","

    def test_alb_certificate_arns_ssm_import(self):
        """Test ALB imports certificate ARNs from SSM"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "certificate_arns": ["/prod/app/certificate/arn"],
                        }
                    },
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 80,
                            "protocol": "HTTP",
                        }
                    ],
                    "listeners": [
                        {
                            "name": "https",
                            "port": 443,
                            "protocol": "HTTPS",
                            "ssl_policy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
                            "default_action": {
                                "type": "fixed-response",
                                "status_code": 404,
                            },
                        }
                    ],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBCertSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify certificate SSM parameter is imported
        params = template_dict.get("Parameters", {})
        cert_params = [p for p in params if "importcertificatearns" in p.lower()]
        
        assert len(cert_params) == 1, f"Expected 1 certificate parameter, found {len(cert_params)}"
        assert params[cert_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[cert_params[0]]["Default"] == "/prod/app/certificate/arn"

        # Verify HTTPS listener uses the certificate from SSM
        listener_resources = {k: v for k, v in template_dict["Resources"].items() 
                             if v.get("Type") == "AWS::ElasticLoadBalancingV2::Listener"}
        
        https_listeners = [v for v in listener_resources.values() 
                          if v["Properties"].get("Port") == 443]
        assert len(https_listeners) == 1, "Expected 1 HTTPS listener"
        
        listener = https_listeners[0]
        assert listener["Properties"]["Protocol"] == "HTTPS"
        assert "Certificates" in listener["Properties"]
        assert len(listener["Properties"]["Certificates"]) > 0
        # Verify certificate references the SSM parameter
        cert = listener["Properties"]["Certificates"][0]
        assert "CertificateArn" in cert
        assert "Ref" in cert["CertificateArn"]

    def test_alb_multiple_ssm_imports(self):
        """Test ALB with multiple SSM imports (VPC, subnets, security groups, certificates)"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_groups": ["/prod/app/sg/alb-id"],
                            "certificate_arns": ["/prod/app/certificate/arn"],
                        }
                    },
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 8000,
                            "protocol": "HTTP",
                        }
                    ],
                    "listeners": [
                        {
                            "name": "https",
                            "port": 443,
                            "protocol": "HTTPS",
                        }
                    ],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBMultipleSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify all SSM parameters are imported
        params = template_dict.get("Parameters", {})
        assert any("importvpcid" in p.lower() for p in params), "VPC ID parameter not found"
        assert any("importsubnetids" in p.lower() for p in params), "Subnet IDs parameter not found"
        assert any("importsecuritygroups" in p.lower() for p in params), "Security groups parameter not found"
        assert any("importcertificatearns" in p.lower() for p in params), "Certificate ARN parameter not found"

        # Verify ALB is created with all SSM references
        alb_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::ElasticLoadBalancingV2::LoadBalancer"}
        assert len(alb_resources) == 1, "Expected 1 ALB resource"
        
        alb = list(alb_resources.values())[0]
        props = alb["Properties"]
        
        assert props["Type"] == "application"
        assert props["Scheme"] == "internet-facing"
        assert len(props["SecurityGroups"]) > 0
        assert "Ref" in props["SecurityGroups"][0]
        assert "Fn::Split" in props["Subnets"]
        assert props["Subnets"]["Fn::Split"][0] == ","

    def test_alb_vpc_from_attributes_with_dummy_subnets(self):
        """Test that VPC imported from SSM includes dummy subnet IDs for CDK validation"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                        }
                    },
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 80,
                            "protocol": "HTTP",
                        }
                    ],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBVPCDummy")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Verify the VPC was created
        self.assertIsNotNone(stack.vpc)
        
        # The VPC should have been created using from_vpc_attributes
        # which means it won't have concrete subnet objects at synth time
        # but the stack should still synthesize successfully
        template = Template.from_stack(stack)
        
        # Verify template has the ALB resource
        template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 1)

    def test_alb_certificate_fallback_to_config(self):
        """Test ALB falls back to config certificate_arns if SSM import not provided"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "certificate_arns": [
                        "arn:aws:acm:us-east-1:123456789012:certificate/abc-123"
                    ],
                    "target_groups": [
                        {
                            "name": "web-tg",
                            "port": 80,
                            "protocol": "HTTP",
                        }
                    ],
                    "listeners": [
                        {
                            "name": "https",
                            "port": 443,
                            "protocol": "HTTPS",
                        }
                    ],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBCertFallback")
        
        # Create a VPC directly in the stack scope
        vpc = ec2.Vpc(stack, "TestVpc", max_azs=2)
        stack._vpc = vpc
        
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify HTTPS listener uses the hardcoded certificate ARN
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::Listener",
            {
                "Port": 443,
                "Protocol": "HTTPS",
                "Certificates": Match.array_with([
                    {
                        "CertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/abc-123"
                    }
                ]),
            },
        )

    def test_alb_subnet_ids_token_detection(self):
        """Test that _get_subnets correctly identifies unresolved CDK tokens"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                        }
                    },
                    "target_groups": [],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestTokenDetection")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # The _get_subnets method should return None for tokens
        # This is tested indirectly by verifying the Fn::Split is used
        template = Template.from_stack(stack)
        
        template.has_resource_properties(
            "AWS::ElasticLoadBalancingV2::LoadBalancer",
            {
                "Subnets": {
                    "Fn::Split": Match.any_value()
                }
            },
        )


class TestLoadBalancerSSMSecurityGroups(unittest.TestCase):
    """Test cases for security group SSM imports in Load Balancer Stack"""

    def setUp(self):
        """Set up common test fixtures"""
        self.app = App(
            context={
                "aws-cdk:enableDiffNoFail": True,
            }
        )
        self.dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        self.deployment = DeploymentConfig(
            workload=self.dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "prod"},
        )

    def test_alb_security_groups_ssm_import(self):
        """Test ALB imports security group IDs from SSM as list"""
        stack_config = StackConfig(
            {
                "load_balancer": {
                    "name": "test-alb",
                    "type": "APPLICATION",
                    "internet_facing": True,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_groups": [
                                "/prod/app/sg/alb-id",
                                "/prod/app/sg/common-id",
                            ],
                        }
                    },
                    "target_groups": [],
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = LoadBalancerStack(self.app, "TestALBMultipleSG")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify multiple security group parameters
        params = template_dict.get("Parameters", {})
        sg_params = [p for p in params if "importsecuritygroups" in p.lower()]
        
        assert len(sg_params) == 2, f"Expected 2 security group parameters, found {len(sg_params)}"
        
        # Find which param corresponds to which path
        sg_defaults = [params[p]["Default"] for p in sg_params]
        assert "/prod/app/sg/alb-id" in sg_defaults
        assert "/prod/app/sg/common-id" in sg_defaults


if __name__ == "__main__":
    unittest.main()
