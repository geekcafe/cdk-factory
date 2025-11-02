#!/usr/bin/env python3
"""
Modular Full Stack CDK Application
This is a modular implementation of the full_stack.py sample,
using the stack_library components for better reusability and maintainability.
"""

import os
import aws_cdk as cdk
from aws_cdk import App, Stack, Environment
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig, WorkloadFactory

# Import stack library modules
from cdk_factory.stack_library.vpc.vpc_stack import VpcStack
from cdk_factory.stack_library.security_group.security_group_stack import SecurityGroupStack
from cdk_factory.stack_library.rds.rds_stack import RdsStack
from cdk_factory.stack_library.auto_scaling.auto_scaling_stack import AutoScalingStack
from cdk_factory.stack_library.load_balancer.load_balancer_stack import LoadBalancerStack
from cdk_factory.stack_library.route53.route53_stack import Route53Stack


class ModularWebAppStack(Stack):
    """
    A modular implementation of the WebAppStack from full_stack.py
    using the stack_library components.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get deployment configuration
        deployment_name = self.node.try_get_context("deployment_name") or "dev"
        deployment = DeploymentConfig({"name": deployment_name})

        # Create workload configuration
        workload = WorkloadConfig({"name": "webapp"})
        workload_factory = WorkloadFactory(self, workload, deployment)

        # Get context parameters
        domain_name = self.node.try_get_context("domain_name") or "example.com"
        hosted_zone_id = self.node.try_get_context("hosted_zone_id")
        certificate_arn = self.node.try_get_context("certificate_arn")
        db_name = self.node.try_get_context("db_name") or "appdb"
        db_username = self.node.try_get_context("db_username") or "admin"
        container_image = self.node.try_get_context("container_image") or "nginx:latest"
        container_port = self.node.try_get_context("container_port") or 80

        # 1. Create VPC
        vpc_config = {
            "name": "app-vpc",
            "cidr": "10.0.0.0/16",
            "max_azs": 2,
            "nat_gateways": {"count": 1},
            "public_subnets": True,
            "private_subnets": True,
            "isolated_subnets": True,
            "enable_s3_endpoint": True,
            "enable_interface_endpoints": True,
            "interface_endpoints": ["ecr.api", "ecr.dkr", "logs", "ssm", "secretsmanager"],
            "tags": {
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        vpc_stack_config = StackConfig({"vpc": vpc_config})
        vpc_stack = VpcStack(self, "VpcStack")
        vpc_stack.build(vpc_stack_config, deployment, workload)
        workload.vpc = vpc_stack.vpc

        # 2. Create Security Groups
        # ALB Security Group
        alb_sg_config = {
            "name": "alb-sg",
            "description": "Security group for ALB",
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
                }
            ],
            "tags": {
                "Name": "alb-sg",
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        alb_sg_stack_config = StackConfig({"security_group": alb_sg_config})
        alb_sg_stack = SecurityGroupStack(self, "AlbSecurityGroupStack")
        alb_sg_stack.build(alb_sg_stack_config, deployment, workload)
        alb_sg = alb_sg_stack.security_group

        # App Security Group
        app_sg_config = {
            "name": "app-sg",
            "description": "Security group for application instances",
            "allow_all_outbound": True,
            "ingress_rules": [
                {
                    "description": "Allow HTTP from ALB",
                    "port": container_port,
                    "cidr_ranges": []
                },
                {
                    "description": "Allow SSH from anywhere",
                    "port": 22,
                    "cidr_ranges": ["0.0.0.0/0"]
                }
            ],
            "peer_security_groups": [
                {
                    "security_group_id": alb_sg.security_group_id,
                    "ingress_rules": [
                        {
                            "description": "Allow HTTP from ALB",
                            "port": container_port
                        }
                    ]
                }
            ],
            "tags": {
                "Name": "app-sg",
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        app_sg_stack_config = StackConfig({"security_group": app_sg_config})
        app_sg_stack = SecurityGroupStack(self, "AppSecurityGroupStack")
        app_sg_stack.build(app_sg_stack_config, deployment, workload)
        app_sg = app_sg_stack.security_group

        # DB Security Group
        db_sg_config = {
            "name": "db-sg",
            "description": "Security group for database",
            "allow_all_outbound": True,
            "ingress_rules": [],
            "peer_security_groups": [
                {
                    "security_group_id": app_sg.security_group_id,
                    "ingress_rules": [
                        {
                            "description": "Allow PostgreSQL from App",
                            "port": 5432
                        }
                    ]
                }
            ],
            "tags": {
                "Name": "db-sg",
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        db_sg_stack_config = StackConfig({"security_group": db_sg_config})
        db_sg_stack = SecurityGroupStack(self, "DbSecurityGroupStack")
        db_sg_stack.build(db_sg_stack_config, deployment, workload)
        db_sg = db_sg_stack.security_group

        # 3. Create RDS Instance
        rds_config = {
            "name": "app-db",
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
            "security_group_ids": [db_sg.security_group_id],
            "deletion_protection": False,
            "backup_retention": 7,
            "cloudwatch_logs_exports": ["postgresql"],
            "enable_performance_insights": True,
            "removal_policy": "snapshot",
            "tags": {
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        rds_stack_config = StackConfig({"rds": rds_config})
        rds_stack = RdsStack(self, "RdsStack")
        rds_stack.build(rds_stack_config, deployment, workload)
        db_instance = rds_stack.db_instance

        # 4. Create Auto Scaling Group
        auto_scaling_config = {
            "name": "app-asg",
            "instance_type": "t3.micro",
            "min_capacity": 2,
            "max_capacity": 4,
            "desired_capacity": 2,
            "subnet_group_name": "private",
            "security_group_ids": [app_sg.security_group_id],
            "health_check_type": "ELB",
            "health_check_grace_period": 300,
            "cooldown": 300,
            "termination_policies": ["DEFAULT"],
            "managed_policies": [
                "AmazonSSMManagedInstanceCore",
                "AmazonEC2ContainerRegistryReadOnly"
            ],
            "ami_type": "amazon-linux-2023",
            "detailed_monitoring": True,
            "block_devices": [
                {
                    "device_name": "/dev/xvda",
                    "volume_size": 30,
                    "volume_type": "gp3",
                    "delete_on_termination": True,
                    "encrypted": True
                }
            ],
            "container_config": {
                "ecr": {
                    "repo": "app",
                    "tag": "latest"
                },
                "database": {
                    "secret_arn": db_instance.secret.secret_arn if hasattr(db_instance, "secret") else ""
                },
                "port": container_port
            },
            "user_data_commands": [
                "yum update -y",
                "yum install -y docker jq",
                "systemctl enable --now docker"
            ],
            "scaling_policies": [
                {
                    "name": "cpu-scale-out",
                    "type": "target_tracking",
                    "metric_name": "CPUUtilization",
                    "target_value": 70,
                    "scale_out_cooldown": 300,
                    "scale_in_cooldown": 300
                }
            ],
            "tags": {
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }
        auto_scaling_stack_config = StackConfig({"auto_scaling": auto_scaling_config})
        auto_scaling_stack = AutoScalingStack(self, "AutoScalingStack")
        auto_scaling_stack.build(auto_scaling_stack_config, deployment, workload)
        auto_scaling_group = auto_scaling_stack.auto_scaling_group

        # 5. Create Load Balancer
        load_balancer_config = {
            "name": "app-alb",
            "type": "APPLICATION",
            "internet_facing": True,
            "vpc_id": vpc_stack.vpc.vpc_id,
            "security_groups": [alb_sg.security_group_id],
            "deletion_protection": False,
            "idle_timeout": 60,
            "http2_enabled": True,
            "target_groups": [
                {
                    "name": "app-tg",
                    "port": container_port,
                    "protocol": "HTTP",
                    "target_type": "instance",
                    "health_check": {
                        "path": "/",
                        "port": "traffic-port",
                        "healthy_threshold": 2,
                        "unhealthy_threshold": 2,
                        "timeout": 5,
                        "interval": 30,
                        "healthy_http_codes": "200-299"
                    }
                }
            ],
            "listeners": [
                {
                    "name": "http",
                    "port": 80,
                    "protocol": "HTTP",
                    "default_target_group": "app-tg"
                }
            ],
            "tags": {
                "Application": "WebApp",
                "Environment": deployment_name
            }
        }

        # Add HTTPS listener if certificate is provided
        if certificate_arn:
            load_balancer_config["certificate_arns"] = [certificate_arn]
            load_balancer_config["listeners"].append({
                "name": "https",
                "port": 443,
                "protocol": "HTTPS",
                "default_target_group": "app-tg",
                "ssl_policy": "ELBSecurityPolicy-TLS-1-2-Ext-2018-06"
            })

        load_balancer_stack_config = StackConfig({"load_balancer": load_balancer_config})
        load_balancer_stack = LoadBalancerStack(self, "LoadBalancerStack")
        load_balancer_stack.build(load_balancer_stack_config, deployment, workload)
        load_balancer = load_balancer_stack.load_balancer
        
        # Register ASG instances with target group
        target_group = load_balancer_stack.target_groups.get("app-tg")
        if target_group and auto_scaling_group:
            auto_scaling_group.attach_to_application_target_group(target_group)

        # 6. Create Route53 records if hosted zone is provided
        if hosted_zone_id and domain_name:
            route53_config = {
                "domain_name": domain_name,
                "existing_hosted_zone_id": hosted_zone_id,
                "create_hosted_zone": False,
                "create_certificate": False,
                "alias_records": [
                    {
                        "name": f"app.{domain_name}",
                        "target_type": "alb",
                        "target_value": load_balancer.load_balancer_arn
                    }
                ],
                "tags": {
                    "Application": "WebApp",
                    "Environment": deployment_name
                }
            }
            route53_stack_config = StackConfig({"route53": route53_config})
            route53_stack = Route53Stack(self, "Route53Stack")
            route53_stack.build(route53_stack_config, deployment, workload)


app = App()
ModularWebAppStack(app, "ModularWebAppStack",
    env=Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION")
    )
)

app.synth()
