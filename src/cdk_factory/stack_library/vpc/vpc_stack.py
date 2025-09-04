"""
VPC Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.vpc import VpcConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="VpcStack")


@register_stack("vpc_library_module")
@register_stack("vpc_stack")
class VpcStack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS VPC.
    Supports creating VPCs with customizable CIDR blocks, subnets, and networking components.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.vpc_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.vpc = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the VPC stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the VPC stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.vpc_config = VpcConfig(stack_config.dictionary.get("vpc", {}), deployment)
        vpc_name = deployment.build_resource_name(self.vpc_config.name)

        # Setup enhanced SSM integration
        self.setup_enhanced_ssm_integration(self, self.vpc_config)

        # Import any required resources from SSM
        imported_resources = self.auto_import_resources({
            "deployment_name": deployment.name,
            "environment": deployment.environment,
            "workload_name": workload.name
        })
        
        if imported_resources:
            logger.info(f"Imported resources from SSM: {list(imported_resources.keys())}")

        # Create the VPC
        self.vpc = self._create_vpc(vpc_name)

        # Add outputs
        self._add_outputs(vpc_name)

    def _create_vpc(self, vpc_name: str) -> ec2.Vpc:
        """Create a VPC with the specified configuration"""
        # Configure subnet configuration
        subnet_configuration = self._get_subnet_configuration()

        # Configure NAT gateways
        nat_gateway_count = self.vpc_config.nat_gateways.get("count", 1)

        # Create the VPC
        vpc = ec2.Vpc(
            self,
            vpc_name,
            vpc_name=vpc_name,
            cidr=self.vpc_config.cidr,
            max_azs=self.vpc_config.max_azs,
            nat_gateways=nat_gateway_count,
            subnet_configuration=subnet_configuration,
            enable_dns_hostnames=self.vpc_config.enable_dns_hostnames,
            enable_dns_support=self.vpc_config.enable_dns_support,
            gateway_endpoints=(
                {
                    "S3": ec2.GatewayVpcEndpointOptions(
                        service=ec2.GatewayVpcEndpointAwsService.S3
                    )
                }
                if self.vpc_config.enable_s3_endpoint
                else None
            ),
        )

        # Add interface endpoints if specified
        if self.vpc_config.enable_interface_endpoints:
            self._add_interface_endpoints(vpc, self.vpc_config.interface_endpoints)

        # Add tags if specified
        for key, value in self.vpc_config.tags.items():
            cdk.Tags.of(vpc).add(key, value)

        return vpc

    def _get_subnet_configuration(self) -> List[ec2.SubnetConfiguration]:
        """Configure the subnets for the VPC"""
        subnet_configs = []

        # Public subnets
        if self.vpc_config.public_subnets:
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.public_subnet_name,
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=self.vpc_config.public_subnet_mask,
                )
            )

        # Private subnets
        if self.vpc_config.private_subnets:
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.private_subnet_name,
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=self.vpc_config.private_subnet_mask,
                )
            )

        # Isolated subnets
        if self.vpc_config.isolated_subnets:
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.isolated_subnet_name,
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=self.vpc_config.isolated_subnet_mask,
                )
            )

        return subnet_configs

    def _get_nat_gateway_configuration(self) -> Dict[str, Any]:
        """Configure NAT gateways for the VPC"""
        return self.vpc_config.nat_gateways

    def _add_interface_endpoints(self, vpc: ec2.Vpc, endpoints: List[str]) -> None:
        """Add interface endpoints to the VPC"""
        # Common interface endpoints
        endpoint_services = {
            "ecr.api": ec2.InterfaceVpcEndpointAwsService.ECR,
            "ecr.dkr": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            "logs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            "ssm": ec2.InterfaceVpcEndpointAwsService.SSM,
            "secretsmanager": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            "lambda": ec2.InterfaceVpcEndpointAwsService.LAMBDA_,
            "sts": ec2.InterfaceVpcEndpointAwsService.STS,
        }

        # Add specified endpoints
        for endpoint in endpoints:
            if endpoint in endpoint_services:
                vpc.add_interface_endpoint(
                    f"{endpoint}-endpoint", service=endpoint_services[endpoint]
                )
            else:
                logger.warning(f"Unsupported interface endpoint: {endpoint}")

    def _add_outputs(self, vpc_name: str) -> None:
        """Add CloudFormation outputs for the VPC"""
        if self.vpc:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-id",
                value=self.vpc.vpc_id,
                export_name=f"{self.deployment.build_resource_name(vpc_name)}-id",
            )

            cdk.CfnOutput(
                self,
                f"{vpc_name}-public-subnets",
                value=",".join(
                    [subnet.subnet_id for subnet in self.vpc.public_subnets]
                ),
                export_name=f"{self.deployment.build_resource_name(vpc_name)}-public-subnets",
            )

            if self.vpc.private_subnets:
                cdk.CfnOutput(
                    self,
                    f"{vpc_name}-private-subnets",
                    value=",".join(
                        [subnet.subnet_id for subnet in self.vpc.private_subnets]
                    ),
                    export_name=f"{self.deployment.build_resource_name(vpc_name)}-private-subnets",
                )

            if hasattr(self.vpc, "isolated_subnets") and self.vpc.isolated_subnets:
                cdk.CfnOutput(
                    self,
                    f"{vpc_name}-isolated-subnets",
                    value=",".join(
                        [subnet.subnet_id for subnet in self.vpc.isolated_subnets]
                    ),
                    export_name=f"{self.deployment.build_resource_name(vpc_name)}-isolated-subnets",
                )

            # Export SSM parameters if configured
            self._export_ssm_parameters(vpc_name)

    def _export_ssm_parameters(self, vpc_name: str) -> None:
        """Export VPC resources to SSM Parameter Store using enhanced auto-export"""
        if not self.vpc:
            return

        # Create a dictionary of VPC resources to export
        vpc_resources = {
            "vpc_id": self.vpc.vpc_id,
            "vpc_cidr": self.vpc.vpc_cidr_block,
        }

        # Add subnet IDs as comma-separated lists
        if self.vpc.public_subnets:
            vpc_resources["public_subnet_ids"] = ",".join(
                [subnet.subnet_id for subnet in self.vpc.public_subnets]
            )

        if self.vpc.private_subnets:
            vpc_resources["private_subnet_ids"] = ",".join(
                [subnet.subnet_id for subnet in self.vpc.private_subnets]
            )

        if hasattr(self.vpc, "isolated_subnets") and self.vpc.isolated_subnets:
            vpc_resources["isolated_subnet_ids"] = ",".join(
                [subnet.subnet_id for subnet in self.vpc.isolated_subnets]
            )

        # Use enhanced auto-export with context
        context = {
            "deployment_name": self.deployment.name,
            "environment": self.deployment.environment,
            "workload_name": self.workload.name
        }
        
        exported_params = self.auto_export_resources(vpc_resources, context)
        
        if exported_params:
            logger.info(f"Auto-exported VPC resources to SSM: {list(exported_params.keys())}")
        else:
            # Fall back to legacy method for backward compatibility
            self.export_resource_to_ssm(
                scope=self,
                resource_values=vpc_resources,
                config=self.vpc_config,
                resource_name=vpc_name,
                resource_type="vpc",
                context=context
            )
