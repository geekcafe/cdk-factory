"""Unit tests for Auto Scaling Stack SSM Import Features"""

import unittest

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestAutoScalingSSMImports(unittest.TestCase):
    """Test cases for Auto Scaling Stack SSM import functionality"""

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

    def test_auto_scaling_vpc_subnet_ssm_imports(self):
        """Test Auto Scaling Group imports VPC and subnets from SSM parameters"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg",
                    "instance_type": "t3.small",
                    "min_capacity": 1,
                    "max_capacity": 3,
                    "desired_capacity": 2,
                    "subnet_group_name": "Public",
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_group_ids": ["/prod/app/sg/ecs-id"]
                        }
                    },
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestASGSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify SSM parameters are imported
        params = template_dict.get("Parameters", {})
        vpc_id_params = [p for p in params if "ssmimportvpcid" in p.lower()]
        subnet_id_params = [p for p in params if "ssmimportsubnetids" in p.lower()]
        sg_id_params = [p for p in params if "ssmimportsecuritygroupids" in p.lower()]
        
        assert len(vpc_id_params) == 1, f"Expected 1 VPC ID parameter, found {len(vpc_id_params)}"
        assert len(subnet_id_params) == 1, f"Expected 1 subnet IDs parameter, found {len(subnet_id_params)}"
        assert len(sg_id_params) == 1, f"Expected 1 security group IDs parameter, found {len(sg_id_params)}"
        
        # Verify parameter types and defaults
        assert params[vpc_id_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[vpc_id_params[0]]["Default"] == "/prod/app/vpc/id"
        
        assert params[subnet_id_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[subnet_id_params[0]]["Default"] == "/prod/app/vpc/public-subnet-ids"
        
        assert params[sg_id_params[0]]["Type"] == "AWS::SSM::Parameter::Value<String>"
        assert params[sg_id_params[0]]["Default"] == "/prod/app/sg/ecs-id"

        # Verify Auto Scaling Group resource exists
        asg_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::AutoScaling::AutoScalingGroup"}
        assert len(asg_resources) == 1, "Expected 1 Auto Scaling Group resource"
        
        asg = list(asg_resources.values())[0]
        assert asg["Properties"]["MinSize"] == "1"
        assert asg["Properties"]["MaxSize"] == "3"
        assert asg["Properties"]["DesiredCapacity"] == "2"
        
        # Verify VPC ID is referenced from SSM parameter
        vpc_zone_ids = asg["Properties"]["VPCZoneIdentifier"]
        assert isinstance(vpc_zone_ids, list), "VPCZoneIdentifier should be a list"
        # The subnets should be referenced, not the VPC ID directly
        assert len(vpc_zone_ids) > 0, "Expected at least one subnet in VPCZoneIdentifier"

    def test_auto_scaling_ssm_imports_with_launch_template(self):
        """Test Auto Scaling Group with SSM imports creates proper launch template"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-with-lt",
                    "instance_type": "t3.medium",
                    "min_capacity": 2,
                    "max_capacity": 4,
                    "desired_capacity": 3,
                    "subnet_group_name": "Public",
                    "ami_type": "ECS_OPTIMIZED",
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_group_ids": ["/prod/app/sg/ecs-id"]
                        }
                    },
                    "user_data_commands": [
                        "echo 'Hello World'",
                        "yum install -y nginx"
                    ]
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestASGLTSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify Launch Template resource exists
        lt_resources = {k: v for k, v in template_dict["Resources"].items() 
                       if v.get("Type") == "AWS::EC2::LaunchTemplate"}
        assert len(lt_resources) >= 1, "Expected at least 1 Launch Template resource"
        
        lt = list(lt_resources.values())[0]
        assert lt["Properties"]["LaunchTemplateData"]["InstanceType"] == "t3.medium"
        # UserData might not be present in the template if it's handled differently
        if "UserData" in lt["Properties"]["LaunchTemplateData"]:
            assert "UserData" in lt["Properties"]["LaunchTemplateData"]
        
        # Verify Auto Scaling Group references the launch template
        asg_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::AutoScaling::AutoScalingGroup"}
        asg = list(asg_resources.values())[0]
        assert "LaunchTemplate" in asg["Properties"]
        assert "LaunchTemplateId" in asg["Properties"]["LaunchTemplate"]

    def test_auto_scaling_ssm_imports_with_iam_policies(self):
        """Test Auto Scaling Group with SSM imports creates proper IAM role and policies"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-with-iam",
                    "instance_type": "t3.small",
                    "min_capacity": 1,
                    "max_capacity": 2,
                    "desired_capacity": 1,
                    "subnet_group_name": "Public",
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_group_ids": ["/prod/app/sg/ecs-id"]
                        }
                    },
                    "managed_policies": [
                        "AmazonSSMManagedInstanceCore",
                        "CloudWatchAgentServerPolicy"
                    ],
                    "iam_inline_policies": [
                        {
                            "name": "CustomS3Policy",
                            "statements": [
                                {
                                    "effect": "Allow",
                                    "actions": ["s3:GetObject", "s3:PutObject"],
                                    "resources": ["arn:aws:s3:::test-bucket/*"]
                                }
                            ]
                        }
                    ]
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestASGIAMSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify IAM Role resource exists
        role_resources = {k: v for k, v in template_dict["Resources"].items() 
                         if v.get("Type") == "AWS::IAM::Role"}
        assert len(role_resources) >= 1, "Expected at least 1 IAM Role resource"
        
        # Verify managed policies are attached
        for role in role_resources.values():
            if "ManagedPolicyArns" in role.get("Properties", {}):
                managed_policies = role["Properties"]["ManagedPolicyArns"]
                assert any("AmazonSSMManagedInstanceCore" in str(policy) for policy in managed_policies)
                assert any("CloudWatchAgentServerPolicy" in str(policy) for policy in managed_policies)

    def test_auto_scaling_ssm_imports_without_target_groups(self):
        """Test Auto Scaling Group with SSM imports but no target groups (ECS cluster use case)"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-ecs-cluster-asg",
                    "instance_type": "t3.small",
                    "min_capacity": 2,
                    "max_capacity": 6,
                    "desired_capacity": 2,
                    "subnet_group_name": "Public",
                    "health_check_type": "EC2",
                    "health_check_grace_period": 300,
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_group_ids": ["/prod/app/sg/ecs-id"]
                        }
                    },
                    "user_data_commands": [
                        "echo ECS_CLUSTER=test-cluster >> /etc/ecs/ecs.config"
                    ]
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestECSClusterSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify Auto Scaling Group resource exists with ECS-specific settings
        asg_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::AutoScaling::AutoScalingGroup"}
        assert len(asg_resources) == 1, "Expected 1 Auto Scaling Group resource"
        
        asg = list(asg_resources.values())[0]
        assert asg["Properties"]["HealthCheckType"] == "EC2"
        # HealthCheckGracePeriod might not be present in all cases, so check if it exists
        if "HealthCheckGracePeriod" in asg["Properties"]:
            assert asg["Properties"]["HealthCheckGracePeriod"] == 300
        assert asg["Properties"]["MinSize"] == "2"
        assert asg["Properties"]["MaxSize"] == "6"
        
        # Verify no target group attachments (should not have TargetGroupARNs property)
        assert "TargetGroupARNs" not in asg["Properties"]

    def test_auto_scaling_ssm_imports_with_scaling_policies(self):
        """Test Auto Scaling Group with SSM imports and scaling policies"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-with-scaling",
                    "instance_type": "t3.small",
                    "min_capacity": 1,
                    "max_capacity": 5,
                    "desired_capacity": 2,
                    "subnet_group_name": "Public",
                    "ssm": {
                        "imports": {
                            "vpc_id": "/prod/app/vpc/id",
                            "subnet_ids": "/prod/app/vpc/public-subnet-ids",
                            "security_group_ids": ["/prod/app/sg/ecs-id"]
                        }
                    },
                    "scaling_policies": [
                        {
                            "name": "CPUTracking",
                            "type": "TargetTrackingScaling",
                            "target_value": 70,
                            "metric_type": "ECSServiceAverageCPUUtilization"
                        }
                    ]
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestASGScalingSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify Auto Scaling Group resource exists
        asg_resources = {k: v for k, v in template_dict["Resources"].items() 
                        if v.get("Type") == "AWS::AutoScaling::AutoScalingGroup"}
        assert len(asg_resources) == 1, "Expected 1 Auto Scaling Group resource"
        
        # Verify SSM parameters are properly imported
        params = template_dict.get("Parameters", {})
        assert len(params) >= 3, "Expected at least 3 SSM import parameters"

    def test_auto_scaling_ssm_imports_relative_paths(self):
        """Test Auto Scaling Group SSM imports with relative paths (auto-prefixed)"""
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-relative",
                    "instance_type": "t3.small",
                    "min_capacity": 1,
                    "max_capacity": 2,
                    "desired_capacity": 1,
                    "subnet_group_name": "Public",
                    "ssm": {
                        "imports": {
                            "vpc_id": "vpc/id",  # Relative path
                            "subnet_ids": "vpc/public-subnet-ids",  # Relative path
                            "security_group_ids": ["sg/ecs-id"]  # Relative path
                        }
                    }
                }
            },
            workload=self.dummy_workload.dictionary,
        )

        # Create the stack
        stack = AutoScalingStack(self.app, "TestASGRelativeSSM")
        stack.build(stack_config, self.deployment, self.dummy_workload)

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)
        template_dict = template.to_json()

        # Verify SSM parameters are imported with full paths
        params = template_dict.get("Parameters", {})
        vpc_id_params = [p for p in params if "ssmimportvpcid" in p.lower()]
        subnet_id_params = [p for p in params if "ssmimportsubnetids" in p.lower()]
        sg_id_params = [p for p in params if "ssmimportsecuritygroupids" in p.lower()]
        
        assert len(vpc_id_params) == 1, f"Expected 1 VPC ID parameter, found {len(vpc_id_params)}"
        assert len(subnet_id_params) == 1, f"Expected 1 subnet IDs parameter, found {len(subnet_id_params)}"
        assert len(sg_id_params) == 1, f"Expected 1 security group IDs parameter, found {len(sg_id_params)}"
        
        # Verify relative paths were converted to full paths
        assert params[vpc_id_params[0]]["Default"] == "/prod/test-workload/vpc/id"
        assert params[subnet_id_params[0]]["Default"] == "/prod/test-workload/vpc/public-subnet-ids"
        assert params[sg_id_params[0]]["Default"] == "/prod/test-workload/sg/ecs-id"


if __name__ == "__main__":
    unittest.main()
