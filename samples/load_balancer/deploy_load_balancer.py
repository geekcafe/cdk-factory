#!/usr/bin/env python3
"""
Sample script to deploy a load balancer stack using CDK-Factory
"""

import os
import aws_cdk as cdk
from aws_cdk import App, Stack, Environment
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.stack_library.load_balancer.load_balancer_stack import LoadBalancerStack


class LoadBalancerSampleStack(Stack):
    """
    Sample stack that demonstrates how to use the LoadBalancerStack
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
        config_file = self.node.try_get_context("config_file") or "config_min.json"
        
        # Load configuration from file if specified
        import json
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), config_file)
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Create load balancer stack
        stack_config = StackConfig(config_data)
        load_balancer_stack = LoadBalancerStack(self, "LoadBalancerStack")
        load_balancer_stack.build(stack_config, deployment, workload)


app = App()
LoadBalancerSampleStack(app, "LoadBalancerSampleStack",
    env=Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION")
    )
)

app.synth()
