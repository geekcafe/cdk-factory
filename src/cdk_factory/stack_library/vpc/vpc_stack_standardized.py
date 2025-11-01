"""
VPC Stack Pattern for CDK-Factory (Standardized SSM Version)
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
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="VpcStackStandardized")


@register_stack("vpc_library_module")
@register_stack("vpc_stack")
class VpcStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for AWS VPC with standardized SSM integration.
    
    This version uses the StandardizedSsmMixin to provide consistent SSM parameter
    handling across all CDK Factory modules.
    
    Key Features:
    - Standardized SSM import/export patterns
    - Template variable resolution
    - Comprehensive validation
    - Clear error handling
    - Backward compatibility
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        # Initialize parent classes properly
        super().__init__(scope, id, **kwargs)
        
        # Initialize module attributes
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

        # Setup standardized SSM integration
        self.setup_standardized_ssm_integration(
            scope=self,
            config=self.vpc_config,
            resource_type="vpc",
            resource_name=vpc_name,
            deployment=deployment,
            workload=workload
        )

        # Process SSM imports using standardized method
        self.process_standardized_ssm_imports()

        # Import any required resources from SSM
        imported_resources = self.get_all_ssm_imports()
        
        if imported_resources:
            logger.info(f"Imported resources from SSM: {list(imported_resources.keys())}")

        # Create the VPC
        self.vpc = self._create_vpc(vpc_name)

        # Add outputs
        self._add_outputs(vpc_name)
        
        # Export SSM parameters
        self._export_ssm_parameters()

        logger.info(f"VPC {vpc_name} built successfully")

    def _create_vpc(self, vpc_name: str) -> ec2.Vpc:
        """Create a VPC with the specified configuration"""
        # Configure subnet configuration
        subnet_configuration = self._get_subnet_configuration()

        # Configure NAT gateways
        nat_gateway_count = self.vpc_config.nat_gateways.get("count", 1)

        # Build VPC properties
        vpc_props = {
            "vpc_name": vpc_name,
            "cidr": self.vpc_config.cidr,
            "nat_gateways": nat_gateway_count,
            "subnet_configuration": subnet_configuration,
            "enable_dns_hostnames": self.vpc_config.enable_dns_hostnames,
            "enable_dns_support": self.vpc_config.enable_dns_support,
            "max_azs": self.vpc_config.max_azs,  # Use max_azs instead of explicit availability_zones
            "gateway_endpoints": (
                {
                    "S3": ec2.GatewayVpcEndpointOptions(
                        service=ec2.GatewayVpcEndpointAwsService.S3
                    )
                }
                if self.vpc_config.enable_s3_endpoint
                else None
            ),
        }
        
        # Create the VPC
        vpc = ec2.Vpc(self, vpc_name, **vpc_props)

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
        if self.vpc_config.subnets.get("public", {}).get("enabled", True):
            public_config = self.vpc_config.subnets["public"]
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.public_subnet_name,
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=public_config.get("cidr_mask", 24),
                    map_public_ip_on_launch=public_config.get("map_public_ip", True),
                )
            )
        
        # Private subnets
        if self.vpc_config.subnets.get("private", {}).get("enabled", True):
            private_config = self.vpc_config.subnets["private"]
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.private_subnet_name,
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=private_config.get("cidr_mask", 24),
                )
            )
        
        # Isolated subnets
        if self.vpc_config.subnets.get("isolated", {}).get("enabled", False):
            isolated_config = self.vpc_config.subnets["isolated"]
            subnet_configs.append(
                ec2.SubnetConfiguration(
                    name=self.vpc_config.isolated_subnet_name,
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=isolated_config.get("cidr_mask", 24),
                )
            )
        
        return subnet_configs

    def _add_interface_endpoints(self, vpc: ec2.Vpc, endpoints: List[str]) -> None:
        """Add VPC interface endpoints"""
        endpoint_services = {
            "ecr.api": ec2.InterfaceVpcEndpointAwsService.ECR,
            "ecr.dkr": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            "ec2": ec2.InterfaceVpcEndpointAwsService.EC2,
            "ecs": ec2.InterfaceVpcEndpointAwsService.ECS,
            "lambda": ec2.InterfaceVpcEndpointAwsService.LAMBDA,
            "secretsmanager": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            "ssm": ec2.InterfaceVpcEndpointAwsService.SSM,
            "kms": ec2.InterfaceVpcEndpointAwsService.KMS,
        }
        
        for endpoint_name in endpoints:
            if endpoint_name in endpoint_services:
                vpc.add_interface_endpoint(
                    f"{endpoint_name}-endpoint",
                    service=endpoint_services[endpoint_name],
                    subnets=ec2.SubnetSelection(
                        subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                    ),
                )
                logger.info(f"Added interface endpoint: {endpoint_name}")
            else:
                logger.warning(f"Unknown interface endpoint: {endpoint_name}")

    def _add_outputs(self, vpc_name: str) -> None:
        """Add CloudFormation outputs for the VPC"""
        if not self.vpc:
            return
            
        # VPC outputs
        cdk.CfnOutput(
            self,
            f"{vpc_name}-VpcId",
            value=self.vpc.vpc_id,
            description=f"VPC ID for {vpc_name}",
            export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-vpc-id",
        )
        
        # Subnet outputs
        public_subnet_ids = [subnet.subnet_id for subnet in self.vpc.public_subnets]
        if public_subnet_ids:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-PublicSubnetIds",
                value=",".join(public_subnet_ids),
                description=f"Public subnet IDs for {vpc_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-public-subnet-ids",
            )
        
        private_subnet_ids = [subnet.subnet_id for subnet in self.vpc.private_subnets]
        if private_subnet_ids:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-PrivateSubnetIds",
                value=",".join(private_subnet_ids),
                description=f"Private subnet IDs for {vpc_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-private-subnet-ids",
            )
        
        isolated_subnet_ids = [subnet.subnet_id for subnet in self.vpc.isolated_subnets]
        if isolated_subnet_ids:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-IsolatedSubnetIds",
                value=",".join(isolated_subnet_ids),
                description=f"Isolated subnet IDs for {vpc_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-isolated-subnet-ids",
            )
        
        # Route table outputs - simplified to avoid route table access issues
        # Skip route table outputs for now as they're causing CDK API issues
        # public_route_table_ids = []
        # if self.vpc.public_subnets:
        #     for subnet in self.vpc.public_subnets:
        #         # Access route table through the subnet's route table association
        #         for association in subnet.node.children:
        #             if hasattr(association, 'route_table_id') and association.route_table_id:
        #                 public_route_table_ids.append(association.route_table_id)
        # 
        # if public_route_table_ids:
        #     cdk.CfnOutput(
        #         self,
        #         f"{vpc_name}-PublicRouteTableIds",
        #         value=",".join(public_route_table_ids),
        #         description=f"Public route table IDs for {vpc_name}",
        #         export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-public-route-table-ids",
        #     )
        # 
        # private_route_table_ids = []
        # if self.vpc.private_subnets:
        #     for subnet in self.vpc.private_subnets:
        #         # Access route table through the subnet's route table association
        #         for association in subnet.node.children:
        #             if hasattr(association, 'route_table_id') and association.route_table_id:
        #                 private_route_table_ids.append(association.route_table_id)
        # 
        # if private_route_table_ids:
        #     cdk.CfnOutput(
        #         self,
        #         f"{vpc_name}-PrivateRouteTableIds",
        #         value=",".join(private_route_table_ids),
        #         description=f"Private route table IDs for {vpc_name}",
        #         export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-private-route-table-ids",
        #     )
        
        # Internet Gateway output
        if hasattr(self.vpc, 'internet_gateway_id') and self.vpc.internet_gateway_id:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-InternetGatewayId",
                value=self.vpc.internet_gateway_id,
                description=f"Internet Gateway ID for {vpc_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-internet-gateway-id",
            )
        
        # NAT Gateway outputs - simplified to avoid None values
        nat_gateway_ids = []
        for subnet in self.vpc.public_subnets:
            if hasattr(subnet, 'node') and subnet.node:
                for child in subnet.node.children:
                    if hasattr(child, 'nat_gateway_id') and child.nat_gateway_id:
                        nat_gateway_ids.append(child.nat_gateway_id)
        
        if nat_gateway_ids:
            cdk.CfnOutput(
                self,
                f"{vpc_name}-NatGatewayIds",
                value=",".join(nat_gateway_ids),
                description=f"NAT Gateway IDs for {vpc_name}",
                export_name=f"{self.deployment.workload_name}-{self.deployment.environment}-nat-gateway-ids",
            )

    def _export_ssm_parameters(self) -> None:
        """Export SSM parameters using standardized approach"""
        if not self.vpc:
            logger.warning("No VPC to export")
            return

        # Prepare resource values for export
        resource_values = {
            "vpc_id": self.vpc.vpc_id,
            "public_subnet_ids": ",".join([subnet.subnet_id for subnet in self.vpc.public_subnets]) if self.vpc.public_subnets else "",
            "private_subnet_ids": ",".join([subnet.subnet_id for subnet in self.vpc.private_subnets]) if self.vpc.private_subnets else "",
            "isolated_subnet_ids": ",".join([subnet.subnet_id for subnet in self.vpc.isolated_subnets]) if self.vpc.isolated_subnets else "",
        }
        
        # Add route table IDs if available - commented out due to CDK API issues
        # public_route_table_ids = []
        # if self.vpc.public_subnets:
        #     for subnet in self.vpc.public_subnets:
        #         # Access route table through the subnet's route table association
        #         for association in subnet.node.children:
        #             if hasattr(association, 'route_table_id') and association.route_table_id:
        #                 public_route_table_ids.append(association.route_table_id)
        # 
        # if public_route_table_ids:
        #     resource_values["public_route_table_ids"] = public_route_table_ids
        # 
        # private_route_table_ids = []
        # if self.vpc.private_subnets:
        #     for subnet in self.vpc.private_subnets:
        #         # Access route table through the subnet's route table association
        #         for association in subnet.node.children:
        #             if hasattr(association, 'route_table_id') and association.route_table_id:
        #                 private_route_table_ids.append(association.route_table_id)
        # 
        # if private_route_table_ids:
        #     resource_values["private_route_table_ids"] = private_route_table_ids
        
        # Add NAT Gateway IDs if available - simplified to avoid None values
        nat_gateway_ids = []
        for subnet in self.vpc.public_subnets:
            if hasattr(subnet, 'node') and subnet.node:
                for child in subnet.node.children:
                    if hasattr(child, 'nat_gateway_id') and child.nat_gateway_id:
                        nat_gateway_ids.append(child.nat_gateway_id)
        if nat_gateway_ids:
            resource_values["nat_gateway_ids"] = ",".join(nat_gateway_ids)
        
        # Add Internet Gateway ID if available
        if hasattr(self.vpc, 'internet_gateway_id') and self.vpc.internet_gateway_id:
            resource_values["internet_gateway_id"] = self.vpc.internet_gateway_id

        # Export using standardized SSM mixin
        exported_params = self.export_standardized_ssm_parameters(resource_values)
        
        logger.info(f"Exported SSM parameters: {exported_params}")

    # Backward compatibility methods
    def auto_export_resources(self, resource_values: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, str]:
        """Backward compatibility method for existing modules."""
        return self.export_standardized_ssm_parameters(resource_values)

    def auto_import_resources(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Backward compatibility method for existing modules."""
        return self.get_all_ssm_imports()


# Backward compatibility alias
VpcStackStandardized = VpcStack
