#!/usr/bin/env python3
"""
Sample script demonstrating SSM parameter sharing between stacks.
This script shows how to deploy VPC and API Gateway stacks with SSM parameter sharing.
"""

import os
import json
import aws_cdk as cdk
from aws_lambda_powertools import Logger

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from cdk_factory.stack_library.cognito.cognito_stack import CognitoStack
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SSMParameterSharingDemo")

def load_config(config_path):
    """Load configuration from JSON file"""
    with open(config_path, 'r') as f:
        return json.load(f)

def main():
    """Main function to deploy stacks with SSM parameter sharing"""
    # Load configuration
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')
    config = load_config(config_path)
    
    # Create CDK app
    app = cdk.App()
    
    # Create deployment config
    deployment_config = DeploymentConfig(config.get('deployment', {}))
    
    # Create workload config (empty for this example)
    workload_config = WorkloadConfig({})
    
    # Deploy VPC stack first
    vpc_stack_config = StackConfig(config.get('stacks', {}).get('vpc', {}))
    vpc_stack = VpcStack(
        app, 
        f"{deployment_config.name}-{vpc_stack_config.name}",
        env=cdk.Environment(
            account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
            region=deployment_config.region
        )
    )
    vpc_stack.build(vpc_stack_config, deployment_config, workload_config)
    
    # Deploy Cognito stack next
    cognito_stack_config = StackConfig(config.get('stacks', {}).get('cognito', {}))
    cognito_stack = CognitoStack(
        app, 
        f"{deployment_config.name}-{cognito_stack_config.name}",
        env=cdk.Environment(
            account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
            region=deployment_config.region
        )
    )
    cognito_stack.build(cognito_stack_config, deployment_config, workload_config)
    
    # Deploy API Gateway stack last, consuming SSM parameters from VPC and Cognito
    api_stack_config = StackConfig(config.get('stacks', {}).get('api_gateway', {}))
    api_stack = ApiGatewayStack(
        app, 
        f"{deployment_config.name}-{api_stack_config.name}",
        env=cdk.Environment(
            account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
            region=deployment_config.region
        )
    )
    api_stack.build(api_stack_config, deployment_config, workload_config)
    
    # Note: No explicit dependencies between stacks are needed when using SSM parameters
    # Each stack will read from SSM at deployment time
    
    # Synthesize the CloudFormation templates
    app.synth()

if __name__ == '__main__':
    main()
