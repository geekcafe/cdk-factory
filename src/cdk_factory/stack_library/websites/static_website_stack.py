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

@register_stack("cdn_stack")
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

        # Note: Stack dependencies are handled by pipeline_factory, not here
        # Dependencies are resolved after all stacks are created so we have stack objects

    def __get_s3_website_bucket(
        self, stack_config: StackConfig, deployment: DeploymentConfig
    ) -> s3.IBucket:
        """
        Get or create S3 bucket based on configuration.
        
        Supports:
        - Creating new bucket (default)
        - Importing existing bucket by name
        - Importing existing bucket by ARN
        """
        bucket_config = stack_config.dictionary.get("bucket", {})
        create_bucket = bucket_config.get("create", True)
        
        if create_bucket:
            # Default behavior - create new bucket
            logger.info("Creating new S3 bucket for website")
            construct = S3BucketConstruct(
                self,
                id=deployment.build_resource_name("Website-Bucket"),
                stack_config=stack_config,
                deployment=deployment,
            )
            return construct.bucket
        else:
            # Import existing bucket
            bucket_name = bucket_config.get("name")
            bucket_arn = bucket_config.get("import_arn")
            
            if bucket_name:
                logger.info(f"Importing existing S3 bucket by name: {bucket_name}")
                return s3.Bucket.from_bucket_name(
                    self,
                    deployment.build_resource_name("ImportedBucket"),
                    bucket_name
                )
            elif bucket_arn:
                logger.info(f"Importing existing S3 bucket by ARN: {bucket_arn}")
                return s3.Bucket.from_bucket_arn(
                    self,
                    deployment.build_resource_name("ImportedBucket"),
                    bucket_arn
                )
            else:
                raise ValueError(
                    "When bucket.create=false, must provide either bucket.name or bucket.import_arn"
                )

    def __get_website_assets_path(
        self, stack_config: StackConfig, workload: WorkloadConfig
    ) -> Optional[str]:
        """
        Get the path to website assets.
        
        Returns None if assets deployment is disabled or assets config not provided.
        Raises ValueError if assets deployment is enabled but path not found.
        """
        assets_config = stack_config.dictionary.get("assets")
        
        # If no assets config provided, skip asset deployment
        if not assets_config:
            logger.info("No assets configuration found - skipping asset path resolution")
            return None
        
        # Check if deployment is explicitly disabled
        deploy_assets = assets_config.get("deploy", True)
        if not deploy_assets:
            logger.info("Asset deployment disabled - skipping asset path resolution")
            return None
        
        # Get path from assets config or fallback to legacy src.path
        source = assets_config.get("path") or stack_config.dictionary.get("src", {}).get("path")
        
        if not source:
            raise ValueError(
                "assets.path or src.path is required when assets.deploy=true (default)"
            )
        
        for base in workload.paths:
            if base is None:
                continue
            candidate = Path(os.path.join(str(Path(base)), source)).resolve()

            if candidate.exists():
                return str(candidate)
        raise ValueError(f"Could not find the source path for static site: {source}")

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
        # Get configuration for assets and CloudFront
        assets_config = stack_config.dictionary.get("assets")
        cloudfront_config = stack_config.dictionary.get("cloudfront", {})
        
        # If assets config not provided, default to no deployment (CDN-only mode)
        if assets_config:
            deploy_assets = assets_config.get("deploy", True)
            enable_versioning = assets_config.get("enable_versioning", True)
        else:
            deploy_assets = False
            enable_versioning = False
        
        invalidate_on_deploy = cloudfront_config.get("invalidate_on_deploy", deploy_assets)
        restrict_to_known_hosts = cloudfront_config.get("restrict_to_known_hosts", True)
        
        # Determine version/path for CloudFront origin
        version = None  # Default to no subdirectory (bucket root)
        assets_path = None
        
        if deploy_assets:
            assets_path = self.__get_website_assets_path(stack_config, workload)
            if enable_versioning and assets_path:
                version = self.__get_version_number(assets_path)
                logger.info(f"👉 WEBSITE VERSION NUMBER: {version}")
                logger.info(f"👉 CloudFront origin path: /{version}")
            else:
                logger.info("👉 Asset versioning disabled - CloudFront serving from bucket root")
        else:
            logger.info("👉 Asset deployment disabled - CloudFront serving from bucket root")

        # Build CloudFront distribution kwargs
        cf_kwargs = {
            "scope": self,
            "id": deployment.build_resource_name("CloudFrontDistribution"),
            "source_bucket": bucket,
            "aliases": aliases,
            "certificate": certificate,
            "restrict_to_known_hosts": restrict_to_known_hosts,
            "stack_config": stack_config,
        }
        
        # Only set source_bucket_sub_directory if we have a version
        if version:
            cf_kwargs["source_bucket_sub_directory"] = version
        
        cloudfront_distribution = CloudFrontDistributionConstruct(**cf_kwargs)

        # Deploy website assets to S3 if configured
        if deploy_assets and assets_path:
            logger.info(f"Deploying assets from {assets_path} to S3")
            
            deployment_kwargs = {
                "scope": self,
                "id": deployment.build_resource_name("static-website-distribution"),
                "destination_bucket": bucket,
                "sources": [aws_s3_deployment.Source.asset(assets_path)],
                "memory_limit": int(deployment.config.get("distribution_lambda_memory_limit", 1024)),
            }
            
            # Add versioning if enabled
            if enable_versioning:
                deployment_kwargs["destination_key_prefix"] = version
            
            # Add CloudFront invalidation if enabled
            if invalidate_on_deploy and cloudfront_distribution.distribution:
                logger.info("CloudFront invalidation enabled - deployment will take ~5 minutes")
                deployment_kwargs["distribution"] = cloudfront_distribution.distribution
                deployment_kwargs["distribution_paths"] = ["/*"]
            else:
                logger.info("CloudFront invalidation disabled")
            
            aws_s3_deployment.BucketDeployment(**deployment_kwargs)
        else:
            logger.info("Skipping asset deployment - using existing bucket content")

        if hosted_zone and cloudfront_distribution.distribution:
            self.__setup_route53_records(
                deployment,
                hosted_zone=hosted_zone,
                aliases=aliases,
                distribution=cloudfront_distribution.distribution,
            )
        
        # Export SSM parameters if configured
        self.__export_ssm_parameters(
            stack_config=stack_config,
            bucket=bucket,
            cloudfront_distribution=cloudfront_distribution,
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

    def __export_ssm_parameters(
        self,
        stack_config: StackConfig,
        bucket: s3.IBucket,
        cloudfront_distribution: CloudFrontDistributionConstruct,
    ) -> None:
        """
        Export stack outputs to SSM Parameter Store if ssm_exports is configured.
        
        Args:
            stack_config: Stack configuration containing ssm_exports
            bucket: The S3 bucket
            cloudfront_distribution: The CloudFront distribution construct
        """
        ssm_exports = stack_config.dictionary.get("ssm", {}).get("exports", {})
        
        if not ssm_exports:
            logger.debug("No SSM exports configured for this stack")
            return
        
        # Export bucket name if configured
        if "bucket_name" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportBucketName",
                value=bucket.bucket_name,
                parameter_name=ssm_exports["bucket_name"],
                description=f"S3 bucket name for {stack_config.name}",
            )
        
        if "bucket_arn" in ssm_exports:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportBucketArn",
                value=bucket.bucket_arn,
                parameter_name=ssm_exports["bucket_arn"],
                description=f"S3 bucket ARN for {stack_config.name}",
            )

        # Export CloudFront domain if configured
        if "cloudfront_domain" in ssm_exports and cloudfront_distribution.distribution:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportCloudFrontDomain",
                value=cloudfront_distribution.dns_name,
                parameter_name=ssm_exports["cloudfront_domain"],
                description=f"CloudFront domain name for {stack_config.name}",
            )
        
        # Export CloudFront distribution ID if configured
        if "cloudfront_distribution_id" in ssm_exports and cloudfront_distribution.distribution:
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportCloudFrontDistributionId",
                value=cloudfront_distribution.distribution_id,
                parameter_name=ssm_exports["cloudfront_distribution_id"],
                description=f"CloudFront distribution ID for {stack_config.name}",
            )
        
        # Export DNS alias (first alias) if configured
        if "dns_alias" in ssm_exports and cloudfront_distribution.aliases:
            # Export the first alias (primary domain)
            primary_alias = cloudfront_distribution.aliases[0] if isinstance(cloudfront_distribution.aliases, list) else cloudfront_distribution.aliases
            self.export_ssm_parameter(
                scope=self,
                id="SsmExportDnsAlias",
                value=primary_alias,
                parameter_name=ssm_exports["dns_alias"],
                description=f"Primary DNS alias for {stack_config.name}",
            )
        
        logger.info(f"Exported {len(ssm_exports)} SSM parameters for stack {stack_config.name}")

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
