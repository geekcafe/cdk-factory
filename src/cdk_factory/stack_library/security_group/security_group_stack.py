"""
Security Group Stack Pattern for CDK-Factory
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
from cdk_factory.configurations.resources.security_group import SecurityGroupConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.vpc_provider_mixin import VPCProviderMixin
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="SecurityGroupStack")


@register_stack("security_group_library_module")
@register_stack("security_group_stack")
class SecurityGroupStack(IStack, VPCProviderMixin, StandardizedSsmMixin):
    """
    Reusable stack for AWS Security Groups.
    Supports creating security groups with customizable rules.
    """

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

        self.sg_config = SecurityGroupConfig(
            stack_config.dictionary.get("security_group", {}), deployment
        )
        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        # Security group recreation would cause network disruption, so construct ID must be stable
        stable_sg_id = f"{deployment.workload_name}-{deployment.environment}-security-group"
        sg_name = deployment.build_resource_name(self.sg_config.name)

        # Create or import security group
        if self.sg_config.existing_security_group_id:
            self.security_group = self._import_existing_security_group(sg_name)
        else:
            self.security_group = self._create_security_group(sg_name, stable_sg_id)

        # Add ingress and egress rules
        self._add_ingress_rules()
        self._add_egress_rules()
        self._add_peer_security_group_rules()

        # Add outputs
        self._add_outputs(sg_name)

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the Security Group using centralized VPC provider mixin."""
        if self._vpc:
            return self._vpc
        
        # Use the centralized VPC resolution from VPCProviderMixin
        self._vpc = self.resolve_vpc(
            config=self.sg_config,
            deployment=self.deployment,
            workload=self.workload
        )
        return self._vpc

    def _create_security_group(self, sg_name: str, stable_sg_id: str) -> ec2.SecurityGroup:
        """Create a new security group"""
        security_group = ec2.SecurityGroup(
            self,
            stable_sg_id,
            vpc=self.vpc,
            security_group_name=sg_name,
            description=self.sg_config.description,
            allow_all_outbound=self.sg_config.allow_all_outbound,
        )

        # Add tags
        for key, value in self.sg_config.tags.items():
            cdk.Tags.of(security_group).add(key, value)

        return security_group

    def _import_existing_security_group(self, sg_name: str) -> ec2.ISecurityGroup:
        """Import an existing security group"""
        return ec2.SecurityGroup.from_security_group_id(
            self,
            sg_name,
            security_group_id=self.sg_config.existing_security_group_id,
            allow_all_outbound=self.sg_config.allow_all_outbound,
        )

    def _add_ingress_rules(self) -> None:
        """Add ingress rules to the security group"""
        # Skip if using imported security group
        if isinstance(self.security_group, ec2.SecurityGroup):
            for i, rule in enumerate(self.sg_config.ingress_rules):
                port = rule.get("port")
                from_port = rule.get("from_port", port)
                to_port = rule.get("to_port", port)
                protocol = rule.get("protocol", "tcp")
                description = rule.get("description", f"Ingress rule {i+1}")

                # Get protocol object
                protocol_obj = self._get_protocol(protocol)

                # Handle CIDR ranges
                cidr_ranges = rule.get("cidr_ranges", [])
                for cidr in cidr_ranges:
                    self.security_group.add_ingress_rule(
                        ec2.Peer.ipv4(cidr),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

                # Handle IPv6 CIDR ranges
                ipv6_cidr_ranges = rule.get("ipv6_cidr_ranges", [])
                for cidr in ipv6_cidr_ranges:
                    self.security_group.add_ingress_rule(
                        ec2.Peer.ipv6(cidr),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

                # Handle prefix lists
                prefix_lists = rule.get("prefix_lists", [])
                for prefix_list_id in prefix_lists:
                    self.security_group.add_ingress_rule(
                        ec2.Peer.prefix_list(prefix_list_id),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

    def _add_egress_rules(self) -> None:
        """Add egress rules to the security group"""
        # Skip if using imported security group or if allow_all_outbound is true
        if (
            isinstance(self.security_group, ec2.SecurityGroup)
            and not self.sg_config.allow_all_outbound
        ):
            for i, rule in enumerate(self.sg_config.egress_rules):
                port = rule.get("port")
                from_port = rule.get("from_port", port)
                to_port = rule.get("to_port", port)
                protocol = rule.get("protocol", "tcp")
                description = rule.get("description", f"Egress rule {i+1}")

                # Get protocol object
                protocol_obj = self._get_protocol(protocol)

                # Handle CIDR ranges
                cidr_ranges = rule.get("cidr_ranges", [])
                for cidr in cidr_ranges:
                    self.security_group.add_egress_rule(
                        ec2.Peer.ipv4(cidr),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

                # Handle IPv6 CIDR ranges
                ipv6_cidr_ranges = rule.get("ipv6_cidr_ranges", [])
                for cidr in ipv6_cidr_ranges:
                    self.security_group.add_egress_rule(
                        ec2.Peer.ipv6(cidr),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

                # Handle prefix lists
                prefix_lists = rule.get("prefix_lists", [])
                for prefix_list_id in prefix_lists:
                    self.security_group.add_egress_rule(
                        ec2.Peer.prefix_list(prefix_list_id),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

    def _add_peer_security_group_rules(self) -> None:
        """Add peer security group rules"""
        # Skip if using imported security group
        if isinstance(self.security_group, ec2.SecurityGroup):
            for i, rule in enumerate(self.sg_config.peer_security_groups):
                sg_id = rule.get("security_group_id")
                if not sg_id:
                    continue

                peer_sg = ec2.SecurityGroup.from_security_group_id(
                    self, f"PeerSG-{i+1}", security_group_id=sg_id
                )

                # Add ingress rules
                ingress_rules = rule.get("ingress_rules", [])
                for j, ingress in enumerate(ingress_rules):
                    port = ingress.get("port")
                    from_port = ingress.get("from_port", port)
                    to_port = ingress.get("to_port", port)
                    protocol = ingress.get("protocol", "tcp")
                    description = ingress.get(
                        "description", f"Peer ingress rule {i+1}-{j+1}"
                    )

                    # Get protocol object
                    protocol_obj = self._get_protocol(protocol)

                    self.security_group.add_ingress_rule(
                        ec2.Peer.security_group_id(peer_sg.security_group_id),
                        ec2.Port(
                            protocol=protocol_obj,
                            from_port=from_port,
                            to_port=to_port,
                            string_representation=description,
                        ),
                        description=description,
                    )

                # Add egress rules
                egress_rules = rule.get("egress_rules", [])
                for j, egress in enumerate(egress_rules):
                    port = egress.get("port")
                    from_port = egress.get("from_port", port)
                    to_port = egress.get("to_port", port)
                    protocol = egress.get("protocol", "tcp")
                    description = egress.get(
                        "description", f"Peer egress rule {i+1}-{j+1}"
                    )

                    # Get protocol object
                    protocol_obj = self._get_protocol(protocol)

                    if not self.sg_config.allow_all_outbound:
                        self.security_group.add_egress_rule(
                            ec2.Peer.security_group_id(peer_sg.security_group_id),
                            ec2.Port(
                                protocol=protocol_obj,
                                from_port=from_port,
                                to_port=to_port,
                                string_representation=description,
                            ),
                            description=description,
                        )

    def _get_protocol(self, protocol_str: str) -> ec2.Protocol:
        """
        Convert string protocol to ec2.Protocol

        In test mode, always returns TCP to avoid mocking issues
        In normal mode, tries to map the protocol string to a Protocol enum value
        """
        if self._test_mode:
            # In test mode, always use TCP protocol to avoid mocking issues
            return ec2.Protocol.TCP

        # Handle special case for all protocols
        if protocol_str == "-1" or protocol_str.lower() == "all":
            return ec2.Protocol.ALL

        protocol_str = protocol_str.lower()
        # Protocol is a class with static properties in CDK
        if hasattr(ec2.Protocol, protocol_str.upper()):
            return getattr(ec2.Protocol, protocol_str.upper())
        else:
            # For custom protocols, create a new Protocol instance
            return ec2.Protocol(protocol_str)

    def set_test_mode(self, enabled: bool = True) -> None:
        """
        Enable or disable test mode

        In test mode, protocol handling is simplified to avoid mocking issues
        """
        self._test_mode = enabled

    def _add_outputs(self, sg_name: str) -> None:
        self._export_cfn_outputs(sg_name)
        self._export_ssm_parameters(sg_name)

    def _export_cfn_outputs(self, sg_name: str) -> None:
        """Add CloudFormation outputs for the Security Group"""
        return

    def _export_ssm_parameters(self, sg_name: str) -> None:
        """Add SSM parameters for the Security Group"""
        if not self.security_group:
            return

        # Create a dictionary of Load Balancer resources to export
        sg_resources = {
            "sg_id": self.security_group.security_group_id,
            "security_group_id": self.security_group.security_group_id,
        }

        # Use the new clearer method for exporting resources to SSM
        self.export_resource_to_ssm(
            scope=self,
            resource_values=sg_resources,
            config=self.sg_config,
            resource_name=sg_name,
        )
