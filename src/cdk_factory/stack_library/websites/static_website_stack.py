"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import aws_cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment
from aws_lambda_powertools import Logger

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.cloudfront.cloudfront_distribution_construct import (
    CloudFrontDistributionConstruct,
)
from cdk_factory.constructs.s3_buckets.s3_bucket_construct import S3BucketConstruct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("website_library_module")
@register_stack("static_website_stack")
class StaticWebSiteStack(IStack):
    """
    A static website stack.
    """

    def __init__(
        self,
        scope,
        id,  # pylint: disable=redefined-builtin
        **kwargs,
    ):  # pylint: disable=useless-parent-delegation
        super().__init__(scope, id, **kwargs)

    def build(
        self,
        *,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        logger.info("Building static website stack")

        bucket = self.__get_s3_website_bucket(stack_config, deployment)

        # Use DNS aliases from environment settings if available; fallback to global config.
        dns: dict = stack_config.dictionary.get("dns", {})
        aliases: List[str] = dns.get("aliases", [])

        cert: dict = stack_config.dictionary.get("cert", {})

        certificate: Optional[acm.Certificate] = None
        hosted_zone: Optional[route53.IHostedZone] = None
        if dns.get("hosted_zone_id"):
            if not aliases or not isinstance(aliases, list) or len(aliases) == 0:
                raise ValueError(
                    "DNS aliases are required and must be a non-empty list when "
                    "hosted_zone_id is specified"
                )

            hosted_zone = self.__get_hosted_zone(
                hosted_zone_id=dns.get("hosted_zone_id", ""),
                hosted_zone_name=dns.get("hosted_zone_name", ""),
                deployment=deployment,
            )

            cert_domain_name = cert.get("domain_name")
            if cert_domain_name:
                certificate = acm.Certificate(
                    self,
                    id=deployment.build_resource_name("SiteCertificateWildPlus"),
                    domain_name=cert_domain_name,
                    validation=acm.CertificateValidation.from_dns(hosted_zone),
                    subject_alternative_names=cert.get("alternate_names"),
                )

        self.__setup_cloudfront_distribution(
            stack_config=stack_config,
            deployment=deployment,
            workload=workload,
            bucket=bucket,
            aliases=aliases,
            certificate=certificate,
            hosted_zone=hosted_zone,
        )

        if stack_config.dependencies:
            for dependency in stack_config.dependencies:
                self.add_dependency(deployment.build_resource_name(dependency))

    def __get_s3_website_bucket(
        self, stack_config: StackConfig, deployment: DeploymentConfig
    ) -> s3.IBucket:
        construct = S3BucketConstruct(
            self,
            id=deployment.build_resource_name("Website-Bucket"),
            stack_config=stack_config,
            deployment=deployment,
        )
        return construct.bucket

    def __get_website_assets_path(
        self, stack_config: StackConfig, workload: WorkloadConfig
    ) -> str:
        source = stack_config.dictionary.get("src", {}).get("path")
        for base in workload.paths:
            candidate = Path(os.path.join(Path(base), source)).resolve()

            if candidate.exists():
                return str(candidate)
        raise ValueError(f"Could not find the source path: {source}")

    def __setup_cloudfront_distribution(
        self,
        *,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
        bucket: s3.IBucket,
        aliases: List[str],
        certificate: Optional[acm.Certificate] = None,
        hosted_zone: Optional[route53.IHostedZone] = None,
    ) -> None:
        assets_path = self.__get_website_assets_path(stack_config, workload)
        version = self.__get_version_number(assets_path)
        logger.info(f"👉 WEBSITE VERSION NUMBER: {version}")

        cloudfront_distribution = CloudFrontDistributionConstruct(
            scope=self,
            id=deployment.build_resource_name("CloudFrontDistribution"),
            source_bucket=bucket,
            aliases=aliases,
            source_bucket_sub_directory=version,
            certificate=certificate,
            stack_config=stack_config,
        )

        # Deploy website assets to S3 under a versioned key prefix.
        aws_s3_deployment.BucketDeployment(
            self,
            id=deployment.build_resource_name("static-website-distribution"),
            destination_bucket=bucket,
            sources=[aws_s3_deployment.Source.asset(assets_path)],
            destination_key_prefix=version,
            # the next lines will force an invalidation of the CloudFront distribution
            # and the deployment will take ~5 minutes to complete
            distribution=cloudfront_distribution.distribution,  # Invalidation triggered here
            distribution_paths=["/*"],  # Invalidate all paths
            memory_limit=int(
                deployment.config.get("distribution_lambda_memory_limit", 1024)
            ),
        )

        if hosted_zone and cloudfront_distribution.distribution:
            self.__setup_route53_records(
                deployment,
                hosted_zone=hosted_zone,
                aliases=aliases,
                distribution=cloudfront_distribution.distribution,
            )

    def __setup_route53_records(
        self,
        deployment: DeploymentConfig,
        hosted_zone: route53.IHostedZone,
        aliases: List[str],
        distribution: aws_cdk.aws_cloudfront.IDistribution,
    ):
        for alias in aliases:
            route53.ARecord(
                self,
                id=deployment.build_resource_name(f"{alias}-alias"),
                zone=hosted_zone,
                record_name=alias,
                target=route53.RecordTarget.from_alias(
                    aws_cdk.aws_route53_targets.CloudFrontTarget(distribution)
                ),
            )

    def __get_hosted_zone(
        self, hosted_zone_id: str, hosted_zone_name: str, deployment: DeploymentConfig
    ) -> route53.IHostedZone:
        if not hosted_zone_id or not hosted_zone_name:
            raise ValueError("Both hosted zone id and hosted zone name are required")
        return route53.HostedZone.from_hosted_zone_attributes(
            self,
            deployment.build_resource_name("HostedZone"),
            hosted_zone_id=hosted_zone_id,
            zone_name=hosted_zone_name,
        )

    def __get_version_number(self, assets_path: str) -> str:
        version = "0.0.1.ckd.factory"

        # look for a version file
        version_file = os.path.join(Path(assets_path), "version.txt")
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as file:
                version = file.read().strip()
        else:
            message = f"No version file found at {version_file}. Using default version: {version}"
            logger.warning(message)

        return version
