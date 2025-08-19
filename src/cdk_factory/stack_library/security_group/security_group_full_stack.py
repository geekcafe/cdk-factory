from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.security_group_full_stack import (
    SecurityGroupFullStackConfig,
)
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SecurityGroupFullStack")


@register_stack("security_group_full_stack_library_module")
@register_stack("security_group_full_stack")
class SecurityGroupsStack(IStack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.sg_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.security_group = None
        # Flag to determine if we're in test mode
        self._test_mode = False
        self._vpc = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the Security Group stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the Security Group stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.sg_config = SecurityGroupFullStackConfig(
            config=stack_config.dictionary.get("security_group", {}),
            deployment=deployment,
        )

        env_name = self.deployment.environment

        # =========================================================
        # Security Groups
        # =========================================================

        # ALB SG (open to the world on 80/443)
        alb_sg = ec2.CfnSecurityGroup(
            self,
            "WebFleetAlbSecurityGroup",
            vpc_id=self.vpc.vpc_id,
            group_name=f"{env_name}-{self.workload.name}-alb-web-fleet-sg",
            group_description="Application Load Balancer Access",
            security_group_ingress=[
                ec2.CfnSecurityGroup.IngressProperty(
                    cidr_ip="0.0.0.0/0",
                    ip_protocol="tcp",
                    from_port=443,
                    to_port=443,
                    description="Open to the world",
                ),
                ec2.CfnSecurityGroup.IngressProperty(
                    cidr_ip="0.0.0.0/0",
                    ip_protocol="tcp",
                    from_port=80,
                    to_port=80,
                    description="Open to the world",
                ),
            ],
        )

        # Web fleet instances SG (no inline ingress; ALB access rule added below)
        web_fleet_sg = ec2.CfnSecurityGroup(
            self,
            "WebFleetInstancesSecurityGroup",
            vpc_id=self.vpc.vpc_id,
            group_name=f"{env_name}-{self.workload.name}-web-fleet-instances-sg",
            group_description="Application Load Balancer Access",
        )

        # MySQL DB SG (no inline ingress; web-to-db rule added below)
        mysql_sg = ec2.CfnSecurityGroup(
            self,
            "MySqlDbSecurityGroup",
            vpc_id=self.vpc.vpc_id,
            group_name=f"{env_name}-{self.workload.name}-mysql-db-sg",
            group_description="MySQL Security Group",
        )

        # -------- Ingress: ALB -> Web Fleet (all protocols/ports; "-1") --------
        ec2.CfnSecurityGroupIngress(
            self,
            "AlbAccessToWebFleet",
            group_id=web_fleet_sg.attr_group_id,
            ip_protocol="-1",
            source_security_group_id=alb_sg.attr_group_id,
            description="Access from the ALB",
        ).add_dependency(alb_sg)

        # -------- Ingress: Web Fleet -> MySQL (tcp/3306) --------
        ec2.CfnSecurityGroupIngress(
            self,
            "WebFleetAccessToMySql",
            group_id=mysql_sg.attr_group_id,
            ip_protocol="tcp",
            from_port=3306,
            to_port=3306,
            source_security_group_id=web_fleet_sg.attr_group_id,
            description="Database access for WebFleet",
        ).add_dependency(web_fleet_sg)

        # -------- Web Monitoring SG (Uptime Robot IPs for 80/443) --------
        monitoring_sg = ec2.CfnSecurityGroup(
            self,
            "WebMonitoringSecurityGroup",
            vpc_id=self.vpc.vpc_id,
            group_name=f"{env_name}-{self.workload.name}-web-monitoring-sg",
            group_description="Application Load Balancer Access",
        )

        uptime_robot_cidrs = [
            "52.70.84.165/32",
            "54.225.82.45/32",
            "167.99.209.234/32",
            "165.227.83.148/32",
            "208.115.199.16/28",
            "54.79.28.129/32",
            "69.162.124.224/28",
            "216.144.250.150/32",
            "104.131.107.63/32",
            "54.64.67.106/32",
            "159.203.30.41/32",
            "46.101.250.135/32",
            "159.89.8.111/32",
            "178.62.52.237/32",
            "216.245.221.80/28",
            "139.59.173.249/32",
            "138.197.150.151/32",
            "18.221.56.27/32",
            "54.67.10.127/32",
            "146.185.143.14/32",
            "46.137.190.132/32",
            "54.94.142.218/32",
            "128.199.195.156/32",
            "63.143.42.240/28",
            "34.233.66.117/32",
        ]

        # add ingress rules (both 443 and 80) for each CIDR
        for idx, cidr in enumerate(uptime_robot_cidrs, start=1):
            ec2.CfnSecurityGroupIngress(
                self,
                f"WebMonitoring443{idx}",
                group_id=monitoring_sg.attr_group_id,
                cidr_ip=cidr,
                ip_protocol="tcp",
                from_port=443,
                to_port=443,
                description="Uptime Robot",
            )
            ec2.CfnSecurityGroupIngress(
                self,
                f"WebMonitoring80{idx}",
                group_id=monitoring_sg.attr_group_id,
                cidr_ip=cidr,
                ip_protocol="tcp",
                from_port=80,
                to_port=80,
                description="Uptime Robot",
            )

        # =========================================================
        # Outputs (exports)
        # =========================================================
        cdk.CfnOutput(
            self,
            "WebFleetAlbSecurityGroupOut",
            value=alb_sg.ref,
            description="Web Fleet Application Load Balancer Security Group",
            export_name=f"{self.deployment.environment}-{self.workload.name}-WebFleetAlbSecurityGroup",
        )
        cdk.CfnOutput(
            self,
            "WebFleetInstancesSecurityGroupOut",
            value=web_fleet_sg.ref,
            description="Web Fleet Instances Security Group",
            export_name=f"{self.deployment.environment}-{self.workload.name}-WebFleetInstancesSecurityGroup",
        )
        cdk.CfnOutput(
            self,
            "MySqlDbSecurityGroupOut",
            value=mysql_sg.ref,
            description="MySql Security Group",
            export_name=f"{self.deployment.environment}-{self.workload.name}-MySqlDbSecurityGroup",
        )
        cdk.CfnOutput(
            self,
            "WebMonitoringSecurityGroupOut",
            value=monitoring_sg.ref,
            description="Web Fleet Application Load Balancer Security Group",
            export_name=f"{self.deployment.environment}-{self.workload.name}-WebMonitoringSecurityGroup",
        )

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the Security Group"""
        if self._vpc:
            return self._vpc
        if self.sg_config.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.sg_config.vpc_id)
        elif self.workload.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.workload.vpc_id)

        else:
            raise ValueError("VPC ID is not defined in the configuration.")

        return self._vpc
