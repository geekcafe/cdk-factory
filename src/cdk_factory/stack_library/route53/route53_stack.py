"""
Route53 Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import (
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    Duration,
    CfnOutput,
)
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.route53 import Route53Config
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig


logger = Logger(service="Route53Stack")


@register_stack("route53_library_module")
@register_stack("route53_stack")
class Route53Stack(IStack, StandardizedSsmMixin):
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
        self._local_cache = {}  # Cache for reusing distributions
        self._missing_configurations = []

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
        
        # Create certificate if needed (DEPRECATED - use dedicated ACM stack)
        if self.route53_config.create_certificate:
            logger.warning(
                "Creating certificates in Route53Stack is deprecated. "
                "Please use the dedicated 'acm_stack' module for certificate management. "
                "This feature will be maintained for backward compatibility."
            )
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
        # self._create_dns_records_old()
        self._create_dns_records_new()

    
    def _get_or_create_cloudfront_distribution(self, distribution_domain: str, distribution_id: str) -> cloudfront.Distribution:
        """Get or create a CloudFront distribution, reusing if already created"""
        # Create a unique cache key from distribution domain and ID
        cache_key = f"{distribution_domain}-{distribution_id}"
        
        if cache_key not in self._local_cache:
            # Create the distribution construct with a unique ID
            unique_id = f"CF-{distribution_domain.replace('.', '-').replace('*', 'wildcard')}-{hash(cache_key) % 10000}"
            distribution = cloudfront.Distribution.from_distribution_attributes(
                self, unique_id,
                domain_name=distribution_domain,
                distribution_id=distribution_id
            )
            self._local_cache[cache_key] = distribution
            logger.info(f"Created CloudFront distribution construct for {distribution_domain}")
        
        return self._local_cache[cache_key]
    
    def _get_or_create_alb_target(self, record_name: str, target_value: str, load_balancer_zone_id: str, security_group_id: str, load_balancer_dns_name: str) -> targets.LoadBalancerTarget:
        """Get or create a CloudFront distribution, reusing if already created"""
        # Create a unique cache key from distribution domain and ID
        cache_key = f"{record_name}-alb"
        
        if cache_key not in self._local_cache:
            # Create the distribution construct with a unique ID
            target = targets.LoadBalancerTarget(
                elbv2.ApplicationLoadBalancer.from_application_load_balancer_attributes(
                    self, f"ALB-{record_name}",
                    load_balancer_arn=target_value,
                    load_balancer_canonical_hosted_zone_id=load_balancer_zone_id,
                    security_group_id=security_group_id,
                    load_balancer_dns_name=load_balancer_dns_name,
                    
                )
            )
            self._local_cache[cache_key] = target
            logger.info(f"Created ALB target construct for ALB-{record_name}")
        
        return self._local_cache[cache_key]

    def _create_dns_records_new(self) -> None:
        """Create DNS records based on configuration - generic implementation"""
        
        

        for record in self.route53_config.records:
            t = record.get("type")
            record_name = self._get_resolved_value(config=record, key="name", record_type=t)
            record_type = self._get_resolved_value(config=record, key="type", record_type=t)
            
            
            
            # Handle alias records
            if "alias" in record:
                alias_config = record["alias"]
                
                target_type = self._get_resolved_value(config=alias_config, key="target_type", record_type=record_type)
                target_value = self._get_resolved_value(config=alias_config, key="target_value", record_type=record_type)
                
                
                
                
                # Create appropriate target based on type
                alias_target = None
                if target_type == "cloudfront":
                    # CloudFront distribution target
                    distribution_domain = target_value
                    distribution_id = self._get_resolved_value(config=alias_config, key="distribution_id", record_type=record_type)
                    
                    
                    # Get or create the distribution (reuses if already created)
                    distribution = self._get_or_create_cloudfront_distribution(distribution_domain, distribution_id)
                    alias_target = route53.RecordTarget.from_alias(
                        targets.CloudFrontTarget(distribution)
                    )
                elif target_type == "loadbalancer" or target_type == "alb" or target_type == "elbv2":
                    # ALB alias target using imported load balancer attributes

                    security_group_id=self._get_resolved_value(config=alias_config, key="security_group_id", record_type=record_type)                
                    load_balancer_dns_name = self._get_resolved_value(config=alias_config, key="load_balancer_dns_name", record_type=record_type)                
                    load_balancer_zone_id = self._get_resolved_value(config=alias_config, key="load_balancer_zone_id", record_type=record_type)
                    
                    
                    
                    target = self._get_or_create_alb_target(record_name, target_value, load_balancer_zone_id, security_group_id, load_balancer_dns_name)
                            
                    alias_target = route53.RecordTarget.from_alias(target)
                
                else:
                    message = f"Unsupported alias target type: {target_type}"
                    logger.warning(message)
                    missing_configurations.append(message)
                    continue
                
                route_53_record = None
                id = f"AliasRecord-{record_name}-{record_type}"
                print(f"creating record {id}")
                if record_type == "A":
                    route_53_record = route53.ARecord(
                        self,
                        id,
                        zone=self.hosted_zone,
                    record_name=record_name,
                    target=alias_target,
                    ttl=cdk.Duration.seconds(record.get("ttl", 300))
                )
                elif record_type == "AAAA":
                    route_53_record = route53.AaaaRecord(
                        self,
                        id,
                        zone=self.hosted_zone,
                        record_name=record_name,
                        target=alias_target,
                        ttl=cdk.Duration.seconds(record.get("ttl", 300))
                    )
                
            # Handle standard records with values
            elif "values" in record:
                values = record["values"]
                if not isinstance(values, list):
                    values = [values]
                
                # Handle SSM parameter references in values
                processed_values = []
                for value in values:
                    if "{{ssm:" in str(value) and "}}" in str(value):
                        # Extract SSM parameter path from template like {{ssm:/path/to/parameter}}
                        ssm_path = str(value).split("{{ssm:")[1].split("}}")[0]
                        resolved_value = self.get_ssm_imported_value(ssm_path)
                        processed_values.append(resolved_value)
                    else:
                        processed_values.append(value)
                
                values = processed_values
                ttl = record.get("ttl", 300)
                
                # Create standard record based on type
                if record_type == "A":
                    route53.ARecord(
                        self,
                        f"Record-{record_name}",
                        zone=self.hosted_zone,
                        record_name=record_name,
                        target=route53.RecordTarget.from_ip_addresses(*values),
                        ttl=cdk.Duration.seconds(ttl)
                    )
                elif record_type == "AAAA":
                    route53.AaaaRecord(
                        self,
                        f"Record-{record_name}",
                        zone=self.hosted_zone,
                        record_name=record_name,
                        target=route53.RecordTarget.from_ip_addresses(*values),
                        ttl=cdk.Duration.seconds(ttl)
                    )
                elif record_type == "CNAME":
                    route53.CnameRecord(
                        self,
                        f"Record-{record_name}",
                        zone=self.hosted_zone,
                        record_name=record_name,
                        domain_name=values[0],  # CNAME only supports single value
                        ttl=cdk.Duration.seconds(ttl)
                    )
                elif record_type == "MX":
                    # MX records need special handling for preference values
                    mx_targets = []
                    for value in values:
                        if isinstance(value, str) and " " in value:
                            preference, domain = value.split(" ", 1)
                            mx_targets.append(route53.MxRecordValue(
                                domain_name=domain.strip(),
                                preference=int(preference.strip())
                            ))
                        else:
                            logger.warning(f"Invalid MX record format: {value}")
                    
                    if mx_targets:
                        route53.MxRecord(
                            self,
                            f"Record-{record_name}",
                            zone=self.hosted_zone,
                            record_name=record_name,
                            values=mx_targets,
                            ttl=cdk.Duration.seconds(ttl)
                        )
                elif record_type == "TXT":
                    route53.TxtRecord(
                        self,
                        f"Record-{record_name}",
                        zone=self.hosted_zone,
                        record_name=record_name,
                        values=values,
                        ttl=cdk.Duration.seconds(ttl)
                    )
                elif record_type == "NS":
                    route53.NsRecord(
                        self,
                        f"Record-{record_name}",
                        zone=self.hosted_zone,
                        record_name=record_name,
                        values=values,
                        ttl=cdk.Duration.seconds(ttl)
                    )
                else:
                    message = f"Unsupported record type: {record_type}"
                    logger.warning(message)
                    self._missing_configurations.append(message)
                    continue
            
            else:
                message = f"Record missing 'alias' or 'values' configuration: {record}"
                logger.warning(message)
                self._missing_configurations.append(message)
                continue

        if self._missing_configurations and len(self._missing_configurations) > 0:
            # print all missing configurations
            print("Missing configurations:")
            for message in self._missing_configurations:
                print(message)
            
            messages = "\n".join(self._missing_configurations)
            raise ValueError(f"Missing Configurations:\n{messages}")

    def _get_resolved_value(self, *, config: dict, key: str, required: bool = True, record_type: str = ""   ) -> str:
        
        value = config.get(key, "")
        x = str(value).replace("{", "").replace("}", "").replace(":", "")
        unique_id = f"{key}-id-{record_type}-{x}"

        if unique_id in self._local_cache:
            return self._local_cache[unique_id]
        
        
        
        # Handle SSM parameter references in target_value                
        value = self.resolve_ssm_value(self, value, unique_id=unique_id)

        if required and not value:
            self._missing_configurations.append(f"Missing required value for key: {key}")

        self._local_cache[unique_id] = value


        return value

    

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for the Route53 resources"""
        # Hosted Zone ID
        return