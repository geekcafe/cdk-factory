#!/usr/bin/env python3
"""
Modular Component Test
This script demonstrates how to use individual stack library components.
"""

import os
import aws_cdk as cdk
from aws_cdk import App, Stack, Environment
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig, WorkloadFactory

# Import individual stack library modules
from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from cdk_factory.stack_library.security_group.security_group_stack import SecurityGroupStack
from cdk_factory.stack_library.rds.rds_stack import RdsStack


class VpcOnlyStack(Stack):
    """
    Example stack that only deploys a VPC
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get deployment configuration
        deployment_name = self.node.try_get_context("deployment_name") or "dev"
        deployment = DeploymentConfig({"name": deployment_name})
        
        # Create workload configuration
        workload = WorkloadConfig({"name": "vpc-only"})
        workload_factory = WorkloadFactory(self, workload, deployment)
        
        # Create VPC
        vpc_config = {
            "name": "simple-vpc",
            "cidr": "10.0.0.0/16",
            "max_azs": 2,
            "public_subnets": True,
            "private_subnets": True,
            "tags": {
                "Component": "VPC-Only",
                "Environment": deployment_name
            }
        }
        vpc_stack_config = StackConfig({"vpc": vpc_config})
        vpc_stack = VpcStack(self, "VpcStack")
        vpc_stack.build(vpc_stack_config, deployment, workload)


class SecurityGroupOnlyStack(Stack):
    """
    Example stack that only deploys security groups
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get deployment configuration
        deployment_name = self.node.try_get_context("deployment_name") or "dev"
        deployment = DeploymentConfig({"name": deployment_name})
        
        # Create workload configuration
        workload = WorkloadConfig({"name": "sg-only"})
        workload_factory = WorkloadFactory(self, workload, deployment)
        
        # Get VPC ID from context
        vpc_id = self.node.try_get_context("vpc_id")
        if not vpc_id:
            raise ValueError("vpc_id context parameter is required")
        
        # Create Security Group
        sg_config = {
            "name": "web-sg",
            "description": "Web server security group",
            "vpc_id": vpc_id,
            "allow_all_outbound": True,
            "ingress_rules": [
                {
                    "description": "Allow HTTP from anywhere",
                    "port": 80,
                    "cidr_ranges": ["0.0.0.0/0"]
                },
                {
                    "description": "Allow HTTPS from anywhere",
                    "port": 443,
                    "cidr_ranges": ["0.0.0.0/0"]
                },
                {
                    "description": "Allow SSH from anywhere",
                    "port": 22,
                    "cidr_ranges": ["0.0.0.0/0"]
                }
            ],
            "tags": {
                "Component": "SG-Only",
                "Environment": deployment_name
            }
        }
        sg_stack_config = StackConfig({"security_group": sg_config})
        sg_stack = SecurityGroupStack(self, "SecurityGroupStack")
        sg_stack.build(sg_stack_config, deployment, workload)


class DatabaseOnlyStack(Stack):
    """
    Example stack that only deploys an RDS instance
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get deployment configuration
        deployment_name = self.node.try_get_context("deployment_name") or "dev"
        deployment = DeploymentConfig({"name": deployment_name})
        
        # Create workload configuration
        workload = WorkloadConfig({"name": "db-only"})
        workload_factory = WorkloadFactory(self, workload, deployment)
        
        # Get context parameters
        vpc_id = self.node.try_get_context("vpc_id")
        security_group_id = self.node.try_get_context("security_group_id")
        db_name = self.node.try_get_context("db_name") or "testdb"
        db_username = self.node.try_get_context("db_username") or "admin"
        
        if not vpc_id or not security_group_id:
            raise ValueError("vpc_id and security_group_id context parameters are required")
        
        # Create RDS Instance
        rds_config = {
            "name": "simple-db",
            "engine": "postgres",
            "engine_version": "14",
            "instance_class": "t3.micro",
            "database_name": db_name,
            "username": db_username,
            "secret_name": f"{deployment_name}-{db_name}-credentials",
            "allocated_storage": 20,
            "storage_encrypted": True,
            "multi_az": False,
            "subnet_group_name": "isolated",
            "security_group_ids": [security_group_id],
            "deletion_protection": False,
            "backup_retention": 7,
            "removal_policy": "destroy",
            "tags": {
                "Component": "DB-Only",
                "Environment": deployment_name
            }
        }
        rds_stack_config = StackConfig({"rds": rds_config})
        rds_stack = RdsStack(self, "RdsStack")
        rds_stack.build(rds_stack_config, deployment, workload)


app = App()

# Deploy the stacks based on context parameter
stack_type = app.node.try_get_context("stack_type") or "vpc"

if stack_type == "vpc":
    VpcOnlyStack(app, "VpcOnlyStack",
        env=Environment(
            account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
            region=os.environ.get("CDK_DEFAULT_REGION")
        )
    )
elif stack_type == "sg":
    SecurityGroupOnlyStack(app, "SecurityGroupOnlyStack",
        env=Environment(
            account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
            region=os.environ.get("CDK_DEFAULT_REGION")
        )
    )
elif stack_type == "db":
    DatabaseOnlyStack(app, "DatabaseOnlyStack",
        env=Environment(
            account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
            region=os.environ.get("CDK_DEFAULT_REGION")
        )
    )
else:
    raise ValueError(f"Unsupported stack_type: {stack_type}")

app.synth()
