#!/usr/bin/env python3
"""
Sample script to deploy an Auto Scaling Group stack using CDK-Factory
"""

import os
import aws_cdk as cdk
from aws_cdk import App, Stack, Environment
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.stack_library.auto_scaling.auto_scaling_stack_standardized import AutoScalingStack
from cdk_factory.stack_library.security_group.security_group_stack import SecurityGroupStack


class AutoScalingSampleStack(Stack):
    """
    Sample stack that demonstrates how to use the AutoScalingStack
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get deployment configuration
        deployment_name = self.node.try_get_context("deployment_name") or "dev"
        deployment = DeploymentConfig({"name": deployment_name})

        # Create workload configuration
        workload = WorkloadConfig({
            "name": "sample",
            "vpc_id": self.node.try_get_context("vpc_id")
        })

        # Get context parameters
        config_file = self.node.try_get_context("config_file") or "auto_scaling_sample.json"
        
        # Load configuration from file if specified
        import json
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), config_file)
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Create security group for the Auto Scaling Group if needed
        # This is optional if you already have security groups defined
        security_group_config = {
            "security_group": {
                "name": "asg-sg",
                "description": "Security group for Auto Scaling Group",
                "vpc_id": workload.vpc_id,
                "ingress_rules": [
                    {
                        "description": "Allow HTTP",
                        "port": 80,
                        "cidr_ranges": ["0.0.0.0/0"]
                    },
                    {
                        "description": "Allow HTTPS",
                        "port": 443,
                        "cidr_ranges": ["0.0.0.0/0"]
                    },
                    {
                        "description": "Allow application port",
                        "port": 8080,
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ],
                "egress_rules": [
                    {
                        "description": "Allow all outbound traffic",
                        "port": 0,
                        "protocol": "-1",
                        "cidr_ranges": ["0.0.0.0/0"]
                    }
                ]
            }
        }
        
        # Create security group stack
        sg_stack_config = StackConfig(security_group_config)
        security_group_stack = SecurityGroupStack(self, "SecurityGroupStack")
        security_group_stack.build(sg_stack_config, deployment, workload)
        
        # Get the security group ID and update the auto scaling config
        sg_id = security_group_stack.security_group.security_group_id
        
        # Update the security group ID in the config
        if "auto_scaling" in config_data and "security_group_ids" in config_data["auto_scaling"]:
            for i, sg in enumerate(config_data["auto_scaling"]["security_group_ids"]):
                if sg == "${SECURITY_GROUP_ID}":
                    config_data["auto_scaling"]["security_group_ids"][i] = sg_id
        
        # Create auto scaling stack
        stack_config = StackConfig(config_data)
        auto_scaling_stack = AutoScalingStack(self, "AutoScalingStack")
        auto_scaling_stack.build(stack_config, deployment, workload)


app = App()
AutoScalingSampleStack(app, "AutoScalingSampleStack",
    env=Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION")
    )
)

app.synth()
