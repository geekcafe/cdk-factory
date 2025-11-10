"""
ACM (AWS Certificate Manager) Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.acm import AcmConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="AcmStack")


@register_stack("acm_stack")
@register_stack("certificate_stack")
@register_stack("certificate_library_module")
class AcmStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for AWS Certificate Manager.
    Supports creating ACM certificates with DNS validation via Route53.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.acm_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.certificate = None
        self.hosted_zone = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the ACM Certificate stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the ACM Certificate stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        self.acm_config = AcmConfig(
            stack_config.dictionary.get("certificate", {}), deployment
        )
        
        cert_name = deployment.build_resource_name(self.acm_config.name)

        # Get or import hosted zone for DNS validation
        if self.acm_config.hosted_zone_id:
            self.hosted_zone = self._get_hosted_zone()
        
        # Create the certificate
        self.certificate = self._create_certificate(cert_name)

        # Export certificate ARN to SSM
        self._export_certificate_arn(cert_name)

        # Add outputs
        self._add_outputs(cert_name)

    def _get_hosted_zone(self) -> route53.IHostedZone:
        """Get the Route53 hosted zone for DNS validation"""
        if self.acm_config.hosted_zone_id:
            return route53.HostedZone.from_hosted_zone_attributes(
                self,
                "HostedZone",
                hosted_zone_id=self.acm_config.hosted_zone_id,
                zone_name=self.acm_config.domain_name,
            )
        else:
            raise ValueError(
                "hosted_zone_id is required for DNS validation. "
                "Provide it in the certificate configuration."
            )

    def _create_certificate(self, cert_name: str) -> acm.Certificate:
        """Create an ACM certificate with DNS validation"""
        
        # Prepare certificate properties
        cert_props = {
            "domain_name": self.acm_config.domain_name,
        }
        
        # Add DNS validation if hosted zone is available
        if self.hosted_zone:
            cert_props["validation"] = acm.CertificateValidation.from_dns(
                self.hosted_zone
            )
        
        # Add subject alternative names if provided
        if self.acm_config.subject_alternative_names:
            cert_props["subject_alternative_names"] = (
                self.acm_config.subject_alternative_names
            )

        certificate = acm.Certificate(
            self,
            cert_name,
            **cert_props
        )

        # Add tags
        for key, value in self.acm_config.tags.items():
            cdk.Tags.of(certificate).add(key, value)

        logger.info(f"Created certificate for domain: {self.acm_config.domain_name}")
        
        return certificate

    def _export_certificate_arn(self, cert_name: str) -> None:
        """Export certificate ARN to SSM Parameter Store"""
        ssm_exports = self.acm_config.ssm_exports
        
        if not ssm_exports:
            logger.debug("No SSM exports configured for certificate")
            return
        
        # Export certificate ARN
        if "certificate_arn" in ssm_exports:
            param_name = ssm_exports["certificate_arn"]
            if not param_name.startswith("/"):
                param_name = f"/{param_name}"
            
            self.export_ssm_parameter(
                scope=self,
                id=f"{cert_name}-cert-arn-param",
                value=self.certificate.certificate_arn,
                parameter_name=param_name,
                description=f"Certificate ARN for {self.acm_config.domain_name}",
            )
            logger.info(f"Exported certificate ARN to SSM: {param_name}")

    def _add_outputs(self, cert_name: str) -> None:
        """Add CloudFormation outputs"""
        if not self.certificate:
            return
        # Certificate ARN output
        cdk.CfnOutput(
            self,
            "CertificateArn",
            value=self.certificate.certificate_arn,
            description=f"Certificate ARN for {self.acm_config.domain_name}",
        )
        # Domain name output
        cdk.CfnOutput(
            self,
            "DomainName",
            value=self.acm_config.domain_name,
            description="Primary domain name for the certificate",
        )

        return

       