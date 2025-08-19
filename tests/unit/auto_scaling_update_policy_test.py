"""
Test for the Auto Scaling Stack update policy functionality
with minimal mocking to catch integration issues.
"""

import json
import unittest

import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestAutoScalingUpdatePolicy(unittest.TestCase):
    """Test Auto Scaling stack update policy with minimal mocking"""

    def setUp(self):
        """Set up test resources"""
        # Create a CDK app
        self.app = App()
        
        # Create a basic workload config
        self.workload_config = WorkloadConfig(
            {
                "workload": {"name": "test-workload", "devops": {"name": "test-devops"}},
                "vpc": {
                    "id": "vpc-12345",
                    "cidr": "10.0.0.0/16",
                    "subnets": {
                        "private": ["subnet-1", "subnet-2"],
                        "public": ["subnet-3", "subnet-4"],
                    },
                },
            }
        )
        
        # Create a deployment config
        self.deployment_config = DeploymentConfig(
            workload=self.workload_config.dictionary,
            deployment={"name": "test-deployment"},
        )

    def test_update_policy_applied_correctly(self):
        """Test that update policy is correctly applied to the CloudFormation template"""
        # Create stack configuration with update policy
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg",
                    "instance_type": "t3.micro",
                    "min_capacity": 1,
                    "max_capacity": 3,
                    "desired_capacity": 2,
                    "ami_type": "amazon-linux-2023",
                    "subnet_group_name": "private",
                    "security_group_ids": ["sg-12345"],
                    "vpc_id": "vpc-12345",
                    "update_policy": {
                        "min_instances_in_service": 1,
                        "max_batch_size": 2,
                        "pause_time": 300,
                    },
                }
            },
            workload=self.workload_config.dictionary,
        )
        
        # Create the stack
        stack = AutoScalingStack(
            self.app,
            "TestAutoScalingUpdatePolicy",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack - this will create all resources
        stack.build(stack_config, self.deployment_config, self.workload_config)
        
        # Synthesize the stack to CloudFormation
        template = Template.from_stack(stack)
        
        # Get the template as a dictionary for easier inspection
        template_dict = template.to_json()
        
        # Find the AutoScalingGroup resource
        asg_resources = [
            resource for resource_id, resource in template_dict["Resources"].items()
            if resource["Type"] == "AWS::AutoScaling::AutoScalingGroup"
        ]
        
        # Verify we have exactly one ASG
        self.assertEqual(len(asg_resources), 1, "Expected exactly one AutoScalingGroup resource")
        
        # Get the ASG resource
        asg_resource = asg_resources[0]
        
        # Verify the update policy exists and is correctly configured
        self.assertIn("UpdatePolicy", asg_resource, "UpdatePolicy is missing from the ASG resource")
        
        update_policy = asg_resource["UpdatePolicy"]
        self.assertIn("AutoScalingRollingUpdate", update_policy, 
                     "AutoScalingRollingUpdate is missing from the UpdatePolicy")
        
        rolling_update = update_policy["AutoScalingRollingUpdate"]
        self.assertEqual(rolling_update["MinInstancesInService"], 1)
        self.assertEqual(rolling_update["MaxBatchSize"], 2)
        self.assertEqual(rolling_update["PauseTime"], "PT5M")  # 300 seconds = 5 minutes

    def test_update_policy_with_custom_values(self):
        """Test that custom update policy values are correctly applied"""
        # Create stack configuration with custom update policy values
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-custom",
                    "instance_type": "t3.micro",
                    "min_capacity": 2,
                    "max_capacity": 10,
                    "desired_capacity": 4,
                    "ami_type": "amazon-linux-2023",
                    "subnet_group_name": "private",
                    "security_group_ids": ["sg-12345"],
                    "vpc_id": "vpc-12345",
                    "update_policy": {
                        "min_instances_in_service": 2,
                        "max_batch_size": 3,
                        "pause_time": 600,
                    },
                }
            },
            workload=self.workload_config.dictionary,
        )
        
        # Create the stack
        stack = AutoScalingStack(
            self.app,
            "TestAutoScalingCustomUpdatePolicy",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack
        stack.build(stack_config, self.deployment_config, self.workload_config)
        
        # Synthesize the stack to CloudFormation
        template = Template.from_stack(stack)
        
        # Get the template as a dictionary
        template_dict = template.to_json()
        
        # Find the AutoScalingGroup resource
        asg_resources = [
            resource for resource_id, resource in template_dict["Resources"].items()
            if resource["Type"] == "AWS::AutoScaling::AutoScalingGroup"
        ]
        
        # Verify we have exactly one ASG
        self.assertEqual(len(asg_resources), 1, "Expected exactly one AutoScalingGroup resource")
        
        # Get the ASG resource
        asg_resource = asg_resources[0]
        
        # Verify the update policy exists and is correctly configured with custom values
        self.assertIn("UpdatePolicy", asg_resource, "UpdatePolicy is missing from the ASG resource")
        
        update_policy = asg_resource["UpdatePolicy"]
        self.assertIn("AutoScalingRollingUpdate", update_policy, 
                     "AutoScalingRollingUpdate is missing from the UpdatePolicy")
        
        rolling_update = update_policy["AutoScalingRollingUpdate"]
        self.assertEqual(rolling_update["MinInstancesInService"], 2)
        self.assertEqual(rolling_update["MaxBatchSize"], 3)
        self.assertEqual(rolling_update["PauseTime"], "PT10M")  # 600 seconds = 10 minutes

    def test_no_update_policy(self):
        """Test that when no update policy is specified, none is applied"""
        # Create stack configuration without update policy
        stack_config = StackConfig(
            {
                "auto_scaling": {
                    "name": "test-asg-no-policy",
                    "instance_type": "t3.micro",
                    "min_capacity": 1,
                    "max_capacity": 3,
                    "desired_capacity": 2,
                    "ami_type": "amazon-linux-2023",
                    "subnet_group_name": "private",
                    "security_group_ids": ["sg-12345"],
                    "vpc_id": "vpc-12345",
                    # No update_policy specified
                }
            },
            workload=self.workload_config.dictionary,
        )
        
        # Create the stack
        stack = AutoScalingStack(
            self.app,
            "TestAutoScalingNoUpdatePolicy",
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack
        stack.build(stack_config, self.deployment_config, self.workload_config)
        
        # Synthesize the stack to CloudFormation
        template = Template.from_stack(stack)
        
        # Get the template as a dictionary
        template_dict = template.to_json()
        
        # Find the AutoScalingGroup resource
        asg_resources = [
            resource for resource_id, resource in template_dict["Resources"].items()
            if resource["Type"] == "AWS::AutoScaling::AutoScalingGroup"
        ]
        
        # Verify we have exactly one ASG
        self.assertEqual(len(asg_resources), 1, "Expected exactly one AutoScalingGroup resource")
        
        # Get the ASG resource
        asg_resource = asg_resources[0]
        
        # Verify that our custom AutoScalingRollingUpdate is not present when not configured
        # Note: CDK may still add default UpdatePolicy settings like AutoScalingScheduledAction
        update_policy = asg_resource.get("UpdatePolicy", {})
        self.assertNotIn("AutoScalingRollingUpdate", update_policy,
                        "AutoScalingRollingUpdate should not be present when not specified in config")


if __name__ == "__main__":
    unittest.main()
