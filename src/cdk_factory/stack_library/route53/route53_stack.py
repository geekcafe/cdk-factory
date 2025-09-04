"""
Route53 Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.route53 import Route53Config
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="Route53Stack")


@register_stack("route53_library_module")
@register_stack("route53_stack")
class Route53Stack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS Route53.
    Supports creating hosted zones, DNS records, and certificate validation.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.route53_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.hosted_zone = None
        self.certificate = None
        self.records = {}

    def build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Build the Route53 stack"""
        self._build(stack_config, deployment, workload)

    def _build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Internal build method for the Route53 stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.route53_config = Route53Config(stack_config.dictionary.get("route53", {}), deployment)
        
        # Get or create hosted zone
        self.hosted_zone = self._get_or_create_hosted_zone()
        
        # Create certificate if needed
        if self.route53_config.create_certificate:
            self.certificate = self._create_certificate()
            
        # Create DNS records
        self._create_dns_records()
        
        # Add outputs
        self._add_outputs()

    def _get_or_create_hosted_zone(self) -> route53.IHostedZone:
        """Get an existing hosted zone or create a new one"""
        if self.route53_config.existing_hosted_zone_id:
            # Import existing hosted zone
            return route53.HostedZone.from_hosted_zone_attributes(
                self,
                "ImportedHostedZone",
                hosted_zone_id=self.route53_config.existing_hosted_zone_id,
                zone_name=self.route53_config.domain_name
            )
        elif self.route53_config.create_hosted_zone:
            # Create new hosted zone
            return route53.PublicHostedZone(
                self,
                "HostedZone",
                zone_name=self.route53_config.domain_name,
                comment=f"Hosted zone for {self.route53_config.domain_name}"
            )
        else:
            # Look up hosted zone by name
            return route53.HostedZone.from_lookup(
                self,
                "LookedUpHostedZone",
                domain_name=self.route53_config.domain_name
            )

    def _create_certificate(self) -> acm.Certificate:
        """Create an ACM certificate with DNS validation"""
        certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=self.route53_config.domain_name,
            validation=acm.CertificateValidation.from_dns(self.hosted_zone),
            subject_alternative_names=self.route53_config.subject_alternative_names
        )
        
        return certificate

    def _create_dns_records(self) -> None:
        """Create DNS records based on configuration"""
        # Create alias records
        for alias_record in self.route53_config.aliases:
            record_name = alias_record.get("name", "")
            target_type = alias_record.get("target_type", "")
            target_value = alias_record.get("target_value", "")
            
            if not record_name or not target_type or not target_value:
                continue
                
            # Determine the alias target
            alias_target = None
            if target_type == "alb":
                # Get the ALB from the workload if available
                if hasattr(self.workload, "load_balancer"):
                    alb = self.workload.load_balancer
                    alias_target = route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb))
                else:
                    # Try to get ALB from target value
                    alb = elbv2.ApplicationLoadBalancer.from_lookup(
                        self,
                        f"ALB-{record_name}",
                        load_balancer_arn=target_value
                    )
                    alias_target = route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb))
            elif target_type == "cloudfront":
                # For CloudFront, we would need the distribution
                # This is a simplified implementation
                pass
                
            if alias_target:
                record = route53.ARecord(
                    self,
                    f"AliasRecord-{record_name}",
                    zone=self.hosted_zone,
                    record_name=record_name,
                    target=alias_target
                )
                self.records[record_name] = record
                
        # Create CNAME records
        for cname_record in self.route53_config.cname_records:
            record_name = cname_record.get("name", "")
            target_domain = cname_record.get("target_domain", "")
            ttl = cname_record.get("ttl", 300)
            
            if not record_name or not target_domain:
                continue
                
            record = route53.CnameRecord(
                self,
                f"CnameRecord-{record_name}",
                zone=self.hosted_zone,
                record_name=record_name,
                domain_name=target_domain,
                ttl=cdk.Duration.seconds(ttl)
            )
            self.records[record_name] = record

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for the Route53 resources"""
        # Hosted Zone ID
        if self.hosted_zone:
            cdk.CfnOutput(
                self,
                "HostedZoneId",
                value=self.hosted_zone.hosted_zone_id,
                export_name=f"{self.deployment.build_resource_name('hosted-zone')}-id"
            )
            
            # Hosted Zone Name Servers
            if hasattr(self.hosted_zone, "name_servers") and self.hosted_zone.name_servers:
                cdk.CfnOutput(
                    self,
                    "NameServers",
                    value=",".join(self.hosted_zone.name_servers),
                    export_name=f"{self.deployment.build_resource_name('hosted-zone')}-name-servers"
                )
        
        # Certificate ARN
        if self.certificate:
            cdk.CfnOutput(
                self,
                "CertificateArn",
                value=self.certificate.certificate_arn,
                export_name=f"{self.deployment.build_resource_name('certificate')}-arn"
            )
            
        # Record names
        for name, record in self.records.items():
            cdk.CfnOutput(
                self,
                f"Record-{name}",
                value=name,
                export_name=f"{self.deployment.build_resource_name('record')}-{name}"
            )
