"""
Load Balancer Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_certificatemanager as acm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.load_balancer import LoadBalancerConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="LoadBalancerStack")


@register_stack("alb_library_module")
@register_stack("alb_stack")
@register_stack("load_balancer_library_module")
@register_stack("load_balancer_stack")
class LoadBalancerStack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS Load Balancers.
    Supports creating Application and Network Load Balancers with customizable configurations.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.lb_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.load_balancer = None
        self.target_groups = {}
        self.listeners = {}
        self._vpc = None
        self._hosted_zone = None
        self._record_names = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the Load Balancer stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the Load Balancer stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        self.ssl_certificate = None
        self.lb_config = LoadBalancerConfig(
            stack_config.dictionary.get("load_balancer", {}), deployment
        )
        lb_name = deployment.build_resource_name(self.lb_config.name)

        self._prep_dns()

        # set up SSL certificate if configured
        self._setup_ssl_certificate()

        # Create the Load Balancer
        self.load_balancer = self._create_load_balancer(lb_name)

        # Create target groups
        self._create_target_groups(lb_name)

        # Create listeners
        self._create_listeners(lb_name)

        # Setup DNS if configured
        self._setup_dns(lb_name)

        # Add outputs
        self._add_outputs(lb_name)

    def _create_load_balancer(self, lb_name: str) -> elbv2.ILoadBalancerV2:
        """Create a Load Balancer with the specified configuration"""

        # Configure security groups if applicable
        security_groups = (
            self._get_security_groups()
            if self.lb_config.type == "APPLICATION"
            else None
        )

        # Get subnets
        subnets = self._get_subnets()

        # Create the Load Balancer based on type
        if self.lb_config.type == "APPLICATION":
            load_balancer = elbv2.ApplicationLoadBalancer(
                self,
                lb_name,
                load_balancer_name=lb_name,
                vpc=self.vpc,
                internet_facing=self.lb_config.internet_facing,
                security_group=(
                    security_groups[0]
                    if security_groups and len(security_groups) > 0
                    else None
                ),
                deletion_protection=self.lb_config.deletion_protection,
                idle_timeout=cdk.Duration.seconds(self.lb_config.idle_timeout),
                http2_enabled=self.lb_config.http2_enabled,
                vpc_subnets=ec2.SubnetSelection(subnets=subnets) if subnets else None,
            )
        else:  # NETWORK
            load_balancer = elbv2.NetworkLoadBalancer(
                self,
                lb_name,
                load_balancer_name=lb_name,
                vpc=self.vpc,
                internet_facing=self.lb_config.internet_facing,
                deletion_protection=self.lb_config.deletion_protection,
                vpc_subnets=ec2.SubnetSelection(subnets=subnets) if subnets else None,
            )

        # Add tags
        for key, value in self.lb_config.tags.items():
            cdk.Tags.of(load_balancer).add(key, value)

        return load_balancer

    @property
    def vpc(self) -> ec2.IVpc:
        """Get the VPC for the Load Balancer"""
        if self._vpc:
            return self._vpc

        elif self.lb_config.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.lb_config.vpc_id)
        elif self.workload.vpc_id:
            self._vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=self.workload.vpc_id)
        else:
            # Use default VPC if not provided
            raise ValueError(
                "VPC is not defined in the configuration.  "
                "You can provide it a the load_balancer.vpc_id in the configuration "
                "or a top level workload.vpc_id in the workload configuration."
            )

        return self._vpc

    def _get_security_groups(self) -> List[ec2.ISecurityGroup]:
        """Get security groups for the Load Balancer"""
        security_groups = []
        for sg_id in self.lb_config.security_groups:
            security_groups.append(
                ec2.SecurityGroup.from_security_group_id(
                    self, f"SecurityGroup-{sg_id}", sg_id
                )
            )
        return security_groups

    def _get_subnets(self) -> List[ec2.ISubnet]:
        """Get subnets for the Load Balancer"""
        subnets = []
        for subnet_id in self.lb_config.subnets:
            subnets.append(
                ec2.Subnet.from_subnet_id(self, f"Subnet-{subnet_id}", subnet_id)
            )
        return subnets

    def _create_target_groups(self, lb_name: str) -> None:
        """Create target groups for the Load Balancer"""

        for idx, tg_config in enumerate(self.lb_config.target_groups):
            tg_name = tg_config.get("name", f"tg-{idx}")
            tg_id = f"{lb_name}-{tg_name}"

            # Configure health check
            health_check = self._configure_health_check(
                tg_config.get("health_check", {})
            )

            # Create target group based on load balancer type
            if self.lb_config.type == "APPLICATION":
                target_group = elbv2.ApplicationTargetGroup(
                    self,
                    tg_id,
                    target_group_name=tg_id[:32],  # Ensure name is within AWS limits
                    vpc=self.vpc,
                    port=tg_config.get("port", 80),
                    protocol=elbv2.ApplicationProtocol(
                        tg_config.get("protocol", "HTTP")
                    ),
                    target_type=elbv2.TargetType(
                        str(tg_config.get("target_type", "INSTANCE")).upper()
                    ),
                    health_check=health_check,
                )
            else:  # NETWORK
                target_group = elbv2.NetworkTargetGroup(
                    self,
                    tg_id,
                    target_group_name=tg_id[:32],  # Ensure name is within AWS limits
                    vpc=self.vpc,
                    port=tg_config.get("port", 80),
                    protocol=elbv2.Protocol(tg_config.get("protocol", "TCP")),
                    target_type=elbv2.TargetType(
                        str(tg_config.get("target_type", "INSTANCE")).upper()
                    ),
                    health_check=health_check,
                )

            # Store target group for later use
            self.target_groups[tg_name] = target_group

    def _configure_health_check(
        self, health_check_config: Dict[str, Any]
    ) -> elbv2.HealthCheck:
        """Configure health check for target groups"""
        return elbv2.HealthCheck(
            path=health_check_config.get("path", "/"),
            port=str(health_check_config.get("port", "traffic-port")),
            healthy_threshold_count=health_check_config.get("healthy_threshold", 5),
            unhealthy_threshold_count=health_check_config.get("unhealthy_threshold", 2),
            timeout=cdk.Duration.seconds(health_check_config.get("timeout", 5)),
            interval=cdk.Duration.seconds(health_check_config.get("interval", 30)),
            healthy_http_codes=health_check_config.get("healthy_http_codes", "200"),
        )

    def _create_listeners(self, lb_name: str) -> None:
        """Create listeners for the Load Balancer"""
        for idx, listener_config in enumerate(self.lb_config.listeners):
            listener_name = listener_config.get("name", f"listener-{idx}")
            listener_id = f"{lb_name}-{listener_name}"
            port = listener_config.get("port", 80)
            protocol = listener_config.get("protocol", "HTTP")

            # Get target group for default action
            default_target_group_name = listener_config.get("default_target_group")
            default_target_group = (
                self.target_groups.get(default_target_group_name)
                if default_target_group_name
                else None
            )

            # Create listener based on load balancer type
            if self.lb_config.type == "APPLICATION":
                # Handle SSL certificates for HTTPS
                certificates = None
                if protocol.upper() == "HTTPS":
                    certificates = self._get_certificates()

                listener = elbv2.ApplicationListener(
                    self,
                    listener_id,
                    load_balancer=self.load_balancer,
                    port=port,
                    protocol=elbv2.ApplicationProtocol(protocol),
                    certificates=certificates,
                    ssl_policy=(
                        elbv2.SslPolicy(self.lb_config.ssl_policy)
                        if protocol.upper() == "HTTPS"
                        else None
                    ),
                    default_target_groups=(
                        [default_target_group] if default_target_group else None
                    ),
                    default_action=(
                        elbv2.ListenerAction.fixed_response(
                            status_code=404,
                            content_type="text/plain",
                            message_body="Not Found",
                        )
                        if not default_target_group
                        else None
                    ),
                )

                # Add rules if specified
                self._add_listener_rules(listener, listener_config.get("rules", []))

                # Add IP whitelist rules if enabled
                self._add_ip_whitelist_rules(listener, [default_target_group])

            else:  # NETWORK
                listener = elbv2.NetworkListener(
                    self,
                    listener_id,
                    load_balancer=self.load_balancer,
                    port=port,
                    protocol=elbv2.Protocol(protocol),
                    default_target_groups=(
                        [default_target_group] if default_target_group else None
                    ),
                )

            # Store listener for later use
            self.listeners[listener_name] = listener

    def _get_certificates(self) -> List[elbv2.ListenerCertificate]:
        """Get certificates for HTTPS listeners"""
        certificates = []
        for cert_arn in self.lb_config.certificate_arns:
            certificates.append(elbv2.ListenerCertificate.from_arn(cert_arn))

        if self.ssl_certificate:
            certificates.append(
                elbv2.ListenerCertificate.from_arn(self.ssl_certificate.certificate_arn)
            )

        return certificates

    def _add_listener_rules(
        self, listener: elbv2.ApplicationListener, rules: List[Dict[str, Any]]
    ) -> None:
        """Add rules to an Application Load Balancer listener"""
        for idx, rule_config in enumerate(rules):
            rule_id = f"{listener.node.id}-rule-{idx}"
            priority = rule_config.get("priority", 100 + idx)

            # Configure conditions
            conditions = []

            # Path patterns
            path_patterns = rule_config.get("path_patterns", [])
            if path_patterns:
                conditions.append(elbv2.ListenerCondition.path_patterns(path_patterns))

            # Host headers
            host_headers = rule_config.get("host_headers", [])
            if host_headers:
                conditions.append(elbv2.ListenerCondition.host_headers(host_headers))

            # HTTP headers
            http_headers = rule_config.get("http_headers", {})
            for header_name, header_values in http_headers.items():
                conditions.append(
                    elbv2.ListenerCondition.http_header(header_name, header_values)
                )

            # Query strings
            query_strings = rule_config.get("query_strings", [])
            if query_strings:
                query_string_conditions = []
                for qs in query_strings:
                    query_string_conditions.append(
                        elbv2.QueryStringCondition(
                            key=qs.get("key"), value=qs.get("value")
                        )
                    )
                conditions.append(
                    elbv2.ListenerCondition.query_strings(query_string_conditions)
                )

            # Configure actions
            target_group_name = rule_config.get("target_group")
            target_group = (
                self.target_groups.get(target_group_name) if target_group_name else None
            )

            if target_group:
                # Create rule with forward action
                elbv2.ApplicationListenerRule(
                    self,
                    rule_id,
                    listener=listener,
                    priority=priority,
                    conditions=conditions,
                    target_groups=[target_group],
                )

    def _add_ip_whitelist_rules(
        self,
        listener: elbv2.ApplicationListener,
        default_target_groups: List[elbv2.ApplicationTargetGroup],
    ) -> None:
        """Add IP whitelist rules to an Application Load Balancer listener"""
        if (
            not self.lb_config.ip_whitelist_enabled
            or not self.lb_config.ip_whitelist_cidrs
        ):
            return

        # For IP whitelisting, we need to create a rule that blocks all IPs except those in the whitelist
        # Since ALB doesn't support negation directly, we'll create a rule that matches all IPs
        # and blocks them, but we'll modify the listener's default action to only accept whitelisted IPs

        # Create a rule to allow whitelisted IPs to proceed to default target groups
        allow_rule_id = f"{listener.node.id}-ip-whitelist-allow"

        if default_target_groups:
            # Forward whitelisted IPs to the default target groups
            allow_action = elbv2.ListenerAction.forward(
                target_groups=default_target_groups
            )
        else:
            # If no default target groups, allow through to default action
            # This will use whatever the listener's default action was set to
            return  # Let the default action handle it

        # Create the allow rule for whitelisted IPs with high priority
        elbv2.ApplicationListenerRule(
            self,
            allow_rule_id,
            listener=listener,
            priority=1,  # High priority to evaluate first
            conditions=[
                elbv2.ListenerCondition.source_ips(self.lb_config.ip_whitelist_cidrs)
            ],
            action=allow_action,
        )

        # Create a catch-all rule to block non-whitelisted IPs
        block_rule_id = f"{listener.node.id}-ip-whitelist-block"

        # Configure the block action
        block_response = self.lb_config.ip_whitelist_block_response
        block_action = elbv2.ListenerAction.fixed_response(
            status_code=block_response.get("status_code", 403),
            content_type=block_response.get("content_type", "text/plain"),
            message_body=block_response.get("message_body", "Access Denied"),
        )

        # Create a rule that matches all other IPs (catch-all) and blocks them
        # This rule has lower priority so whitelisted IPs are processed first
        elbv2.ApplicationListenerRule(
            self,
            block_rule_id,
            listener=listener,
            priority=32000,  # Low priority catch-all rule
            conditions=[elbv2.ListenerCondition.source_ips(["0.0.0.0/0", "::/0"])],
            action=block_action,
        )

    def _prep_dns(self) -> None:
        """Prepares DNS records for the Load Balancer"""
        hosted_zone_config = self.lb_config.hosted_zone
        if not hosted_zone_config:
            return

        hosted_zone_id = hosted_zone_config.get("id")
        hosted_zone_name = hosted_zone_config.get("name")
        self._record_names = hosted_zone_config.get("record_names", [])

        if not hosted_zone_id or not hosted_zone_name or not self._record_names:
            return

        # Get the hosted zone
        self._hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "hosted-zone",
            hosted_zone_id=hosted_zone_id,
            zone_name=hosted_zone_name,
        )

    def _setup_dns(self, lb_name: str) -> None:
        """Setup DNS records for the Load Balancer"""
        if not self._hosted_zone or not self._record_names:
            return None

        # Create DNS records
        for record_name in self._record_names:
            # A Record
            route53.ARecord(
                self,
                f"{lb_name}-{record_name}-a-record",
                zone=self._hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    targets.LoadBalancerTarget(self.load_balancer)
                ),
            )

            # AAAA Record
            route53.AaaaRecord(
                self,
                f"{lb_name}-{record_name}-aaaa-record",
                zone=self._hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    targets.LoadBalancerTarget(self.load_balancer)
                ),
            )

    def _setup_ssl_certificate(self) -> None:
        """Setup SSL certificate for the Load Balancer"""
        if self.lb_config.ssl_cert_arn:
            self.ssl_certificate = acm.Certificate.from_certificate_arn(
                self,
                "LbCertificate",
                certificate_arn=self.lb_config.ssl_cert_arn,
            )
        elif self._record_names and self._hosted_zone:
            # there are more than one record name, so we need to add them as alt names
            # exclude the first record name from the alt names
            if len(self._record_names) > 1:
                alt_names = self._record_names[1:]
            else:
                alt_names = None

            self.ssl_certificate = acm.Certificate(
                self,
                id="LbCertificate",
                domain_name=self._record_names[0],
                validation=acm.CertificateValidation.from_dns(
                    hosted_zone=self._hosted_zone
                ),
                subject_alternative_names=alt_names,
            )

    def _add_outputs(self, lb_name: str) -> None:
        self._export_cfn_outputs(lb_name)
        self._export_ssm_parameters(lb_name)

    def _export_cfn_outputs(self, lb_name: str) -> None:
        """Add CloudFormation outputs for the Load Balancer"""
        if self.load_balancer:
            # Load Balancer DNS Name
            cdk.CfnOutput(
                self,
                f"{lb_name}-dns-name",
                value=self.load_balancer.load_balancer_dns_name,
                export_name=f"{self.deployment.build_resource_name(lb_name)}-dns-name",
            )

            # Load Balancer ARN
            cdk.CfnOutput(
                self,
                f"{lb_name}-arn",
                value=self.load_balancer.load_balancer_arn,
                export_name=f"{self.deployment.build_resource_name(lb_name)}-arn",
            )

            # Target Group ARNs
            for tg_name, target_group in self.target_groups.items():
                # Normalize target group name for consistent CloudFormation export naming
                normalized_tg_name = self.normalize_resource_name(
                    tg_name, for_export=True
                )
                cdk.CfnOutput(
                    self,
                    f"{lb_name}-{normalized_tg_name}-arn",
                    value=target_group.target_group_arn,
                    export_name=f"{self.deployment.build_resource_name(lb_name)}-{normalized_tg_name}-arn",
                )

    def _export_ssm_parameters(self, lb_name: str) -> None:
        """Export Load Balancer resources to SSM Parameter Store if configured"""
        if not self.load_balancer:
            return

        # Create a dictionary of Load Balancer resources to export
        lb_resources = {
            "alb_dns_name": self.load_balancer.load_balancer_dns_name,
            "alb_zone_id": self.load_balancer.load_balancer_canonical_hosted_zone_id,
            "alb_arn": self.load_balancer.load_balancer_arn,
        }

        # Export target group ARNs to SSM
        for tg_name, target_group in self.target_groups.items():
            # Do not normalize the ssm parameter name
            # attempting to normalize this is causing issues
            # some parameters are auto generated based on the resource name
            # in order to import them later, the names need to match
            lb_resources[f"target_group_{tg_name}_arn"] = target_group.target_group_arn

        # Use the new clearer method for exporting resources to SSM
        self.export_resource_to_ssm(
            scope=self,
            resource_values=lb_resources,
            config=self.lb_config,
            resource_name=lb_name,
        )

    def _export_cfn_outputs(self, lb_name: str) -> None:
        """Add CloudFormation outputs for the Load Balancer"""
        if self.load_balancer:
            # Load Balancer DNS Name
            cdk.CfnOutput(
                self,
                f"{lb_name}-dns-name",
                value=self.load_balancer.load_balancer_dns_name,
                export_name=f"{self.deployment.build_resource_name(lb_name)}-dns-name",
            )

            # Load Balancer ARN
            cdk.CfnOutput(
                self,
                f"{lb_name}-arn",
                value=self.load_balancer.load_balancer_arn,
                export_name=f"{self.deployment.build_resource_name(lb_name)}-arn",
            )

            # Target Group ARNs
            for tg_name, target_group in self.target_groups.items():
                # Normalize target group name for consistent CloudFormation export naming
                normalized_tg_name = self.normalize_resource_name(
                    tg_name, for_export=True
                )
                cdk.CfnOutput(
                    self,
                    f"{lb_name}-{normalized_tg_name}-arn",
                    value=target_group.target_group_arn,
                    export_name=f"{self.deployment.build_resource_name(lb_name)}-{normalized_tg_name}-arn",
                )
