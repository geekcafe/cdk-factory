"""
CloudFront Stack for ALB and Custom Origins
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import logging
from typing import Dict, List, Any, Optional

from aws_cdk import (
    Duration,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_ssm as ssm,
    CfnOutput,
)
from constructs import Construct

from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.resources.cloudfront import CloudFrontConfig

logger = logging.getLogger(__name__)


@register_stack("cloudfront_library_module")
class CloudFrontStack(IStack):
    """
    CloudFront Distribution Stack with support for:
    - Custom origins (ALB, API Gateway, etc.)
    - S3 origins
    - Lambda@Edge associations
    - Cache and origin request policies
    - ACM certificates
    - Custom error responses
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.stack_config = None
        self.deployment = None
        self.cf_config = None

        # Resources
        self.distribution: Optional[cloudfront.Distribution] = None
        self.certificate: Optional[acm.ICertificate] = None
        self.origins_map: Dict[str, cloudfront.IOrigin] = {}

        # SSM imported values
        self.ssm_imported_values: Dict[str, str] = {}

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
        vpc=None,
        target_groups=None,
        security_groups=None,
        shared=None,
    ):
        """Build the CloudFront distribution"""

        self.stack_config = stack_config
        self.deployment = deployment

        # CloudFront config
        cloudfront_dict = stack_config.dictionary.get("cloudfront", {})
        self.cf_config = CloudFrontConfig(cloudfront_dict, deployment)

        logger.info(f"Building CloudFront distribution: {self.cf_config.name}")

        # Process SSM imports first
        self._process_ssm_imports()

        # Create certificate if needed
        if self.cf_config.certificate and self.cf_config.aliases:
            self._create_certificate()

        # Create origins
        self._create_origins()

        # Create distribution
        self._create_distribution()

        # Export SSM parameters
        self._export_ssm_parameters()

        # Create CloudFormation outputs
        self._create_outputs()

        return self

    def _process_ssm_imports(self) -> None:
        """
        Process SSM imports from configuration.
        Follows the same pattern as API Gateway stack - imports SSM parameters as CDK tokens.
        """
        ssm_imports = self.cf_config.ssm_imports

        if not ssm_imports:
            logger.debug("No SSM imports configured for CloudFront")
            return

        logger.info(f"Processing {len(ssm_imports)} SSM imports for CloudFront")

        for param_key, param_path in ssm_imports.items():
            try:
                # Ensure parameter path starts with /
                if not param_path.startswith("/"):
                    param_path = f"/{param_path}"

                # Create unique construct ID from parameter path
                construct_id = f"ssm-import-{param_key}-{hash(param_path) % 10000}"

                # Import SSM parameter - this creates a CDK token that resolves at deployment time
                param = ssm.StringParameter.from_string_parameter_name(
                    self, construct_id, param_path
                )

                # Store the token value for use in configuration
                self.ssm_imported_values[param_key] = param.string_value
                logger.info(f"Imported SSM parameter: {param_key} from {param_path}")

            except Exception as e:
                logger.error(
                    f"Failed to import SSM parameter {param_key} from {param_path}: {e}"
                )
                raise

    def _create_certificate(self) -> None:
        """Create or import ACM certificate for CloudFront (must be in us-east-1)"""
        cert_config = self.cf_config.certificate

        if not cert_config:
            return

        # Check if certificate ARN is provided
        cert_arn = self.resolve_ssm_value(self, cert_config.get("arn"), "CertificateARN")
        if cert_arn:
            self.certificate = acm.Certificate.from_certificate_arn(
                self, "Certificate", certificate_arn=cert_arn
            )
            logger.info(f"Using existing certificate: {cert_arn}")
            return

        # Check if we should import from SSM
        ssm_param = cert_config.get("ssm_parameter")
        if ssm_param:
            cert_arn = ssm.StringParameter.value_from_lookup(self, ssm_param)
            self.certificate = acm.Certificate.from_certificate_arn(
                self, "Certificate", certificate_arn=cert_arn
            )
            logger.info(f"Using certificate from SSM: {ssm_param}")
            return

        # Create new certificate from domain name
        domain_name = cert_config.get("domain_name")
        if domain_name and self.cf_config.aliases:
            # CloudFront certificates must be in us-east-1
            if self.region != "us-east-1":
                logger.warning(
                    f"Certificate creation requested but stack is in {self.region}. "
                    "CloudFront certificates must be created in us-east-1"
                )
                return

            # Create the certificate
            # Get hosted zone from SSM imports
            hosted_zone_id = cert_config.get("hosted_zone_id")
            hosted_zone = route53.HostedZone.from_hosted_zone_id(
                self, "HostedZone", hosted_zone_id
            )

            self.certificate = acm.Certificate(
                self,
                "Certificate",
                domain_name=domain_name,
                subject_alternative_names=self.cf_config.aliases,
                validation=acm.CertificateValidation.from_dns(hosted_zone=hosted_zone),
            )
            logger.info(f"Created new ACM certificate for domain: {domain_name}")
            return

        logger.warning(
            "No certificate ARN or domain name provided - CloudFront will use default certificate"
        )

    def _create_origins(self) -> None:
        """Create CloudFront origins (custom, S3, etc.)"""
        origins_config = self.cf_config.origins

        if not origins_config:
            raise ValueError(
                "At least one origin is required for CloudFront distribution"
            )

        for origin_config in origins_config:
            origin_id = origin_config.get("id")
            origin_type = origin_config.get("type", "custom")

            if not origin_id:
                raise ValueError("Origin ID is required")

            if origin_type == "custom":
                origin = self._create_custom_origin(origin_config)
            elif origin_type == "s3":
                origin = self._create_s3_origin(origin_config)
            else:
                raise ValueError(f"Unsupported origin type: {origin_type}")

            self.origins_map[origin_id] = origin
            logger.info(f"Created {origin_type} origin: {origin_id}")

    def _create_custom_origin(self, config: Dict[str, Any]) -> cloudfront.IOrigin:
        """Create custom origin (ALB, API Gateway, etc.)"""
        domain_name = self.resolve_ssm_value(
            self, config.get("domain_name"), config.get("domain_name")
        )
        origin_id = config.get("id")

        if not domain_name:
            raise ValueError("domain_name is required for custom origin")

        # # Check if domain name is a placeholder from ssm_imports
        # if domain_name.startswith("{{") and domain_name.endswith("}}"):
        #     placeholder_key = domain_name[2:-2]  # Remove {{ and }}
        #     if placeholder_key in self.ssm_imported_values:
        #         domain_name = self.ssm_imported_values[placeholder_key]
        #         logger.info(f"Resolved domain from SSM import: {placeholder_key}")
        #     else:
        #         logger.warning(f"Placeholder {domain_name} not found in SSM imports")

        # # Legacy support: Check if domain name is an SSM parameter reference
        # elif domain_name.startswith("{{ssm:") and domain_name.endswith("}}"):
        #     # Extract SSM parameter name
        #     ssm_param = domain_name[6:-2]  # Remove {{ssm: and }}
        #     domain_name = ssm.StringParameter.value_from_lookup(self, ssm_param)
        #     logger.info(f"Resolved domain from SSM lookup {ssm_param}: {domain_name}")

        # Build custom headers (e.g., X-Origin-Secret)
        custom_headers = {}
        custom_headers_config = config.get("custom_headers", {})

        for header_name, header_value in custom_headers_config.items():
            # Check if value is from Secrets Manager
            if isinstance(header_value, str) and header_value.startswith("{{secrets:"):
                # For now, just log a warning - Secrets Manager integration needs IAM permissions
                logger.warning(
                    f"Secrets Manager references not yet supported in custom headers: {header_value}"
                )
                continue

            custom_headers[header_name] = header_value

        # Protocol policy
        protocol_policy_str = config.get("protocol_policy", "https-only")
        protocol_policy_map = {
            "http-only": cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            "https-only": cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
            "match-viewer": cloudfront.OriginProtocolPolicy.MATCH_VIEWER,
        }
        protocol_policy = protocol_policy_map.get(
            protocol_policy_str, cloudfront.OriginProtocolPolicy.HTTPS_ONLY
        )

        # SSL protocols
        origin_ssl_protocols_list = config.get("origin_ssl_protocols", ["TLSv1.2"])
        ssl_protocols = (
            [cloudfront.OriginSslPolicy.TLS_V1_2]
            if "TLSv1.2" in origin_ssl_protocols_list
            else []
        )

        # Create custom origin with explicit origin ID
        return origins.HttpOrigin(
            domain_name,
            origin_id=origin_id,
            protocol_policy=protocol_policy,
            origin_ssl_protocols=ssl_protocols,
            http_port=config.get("http_port", 80),
            https_port=config.get("https_port", 443),
            origin_path=config.get("origin_path", ""),
            connection_attempts=config.get("connection_attempts", 3),
            connection_timeout=Duration.seconds(config.get("connection_timeout", 10)),
            read_timeout=Duration.seconds(config.get("response_timeout", 30)),
            keepalive_timeout=Duration.seconds(config.get("keepalive_timeout", 5)),
            custom_headers=custom_headers if custom_headers else None,
        )

    def _create_s3_origin(self, config: Dict[str, Any]) -> cloudfront.IOrigin:
        """Create S3 origin"""
        # Support both 'bucket_name' and 'domain_name' for S3 origins
        bucket_name = self.resolve_ssm_value(
            self, config.get("bucket_name") or config.get("domain_name"), 
            config.get("bucket_name") or config.get("domain_name")
        )

        origin_path = config.get("origin_path", "")

        if not bucket_name:
            raise ValueError("S3 origin requires 'bucket_name' or 'domain_name' configuration")

        # For S3 origins, we need to import the bucket by name
        bucket = s3.Bucket.from_bucket_name(
            self,
            id=f"S3OriginBucket-{config.get('id', 'unknown')}",
            bucket_name=bucket_name,
        )

        # Create S3 origin with OAC (Origin Access Control) for security
        origin = origins.S3BucketOrigin.with_origin_access_control(
            bucket,
            origin_path=origin_path,
            origin_access_levels=[
                cloudfront.AccessLevel.READ,
                cloudfront.AccessLevel.LIST,
            ],
        )

        return origin

    def _create_distribution(self) -> None:
        """Create CloudFront distribution"""

        # Get default origin
        default_behavior_config = self.cf_config.default_cache_behavior
        target_origin_id = default_behavior_config.get("target_origin_id")

        if not target_origin_id or target_origin_id not in self.origins_map:
            raise ValueError(f"Default cache behavior must reference a valid origin ID")

        default_origin = self.origins_map[target_origin_id]

        # Build default behavior
        default_behavior = self._build_cache_behavior(
            default_behavior_config, default_origin
        )

        # Build additional behaviors
        additional_behaviors = {}
        for behavior_config in self.cf_config.cache_behaviors:
            path_pattern = behavior_config.get("path_pattern")
            origin_id = behavior_config.get("target_origin_id")

            if not path_pattern or not origin_id or origin_id not in self.origins_map:
                logger.warning(f"Invalid cache behavior config, skipping")
                continue

            behavior = self._build_cache_behavior_options(behavior_config)
            additional_behaviors[path_pattern] = behavior

        # Build error responses
        error_responses = []
        for error_config in self.cf_config.custom_error_responses:
            error_code = error_config.get("error_code")
            if error_code:
                error_responses.append(
                    cloudfront.ErrorResponse(
                        http_status=error_code,
                        response_http_status=error_config.get("response_http_status"),
                        response_page_path=error_config.get("response_page_path"),
                        ttl=Duration.seconds(
                            error_config.get("error_caching_min_ttl", 10)
                        ),
                    )
                )

        # HTTP version
        http_version_map = {
            "http1_1": cloudfront.HttpVersion.HTTP1_1,
            "http2": cloudfront.HttpVersion.HTTP2,
        }
        # Try to use HTTP2_AND_3 and HTTP3 if available in the CDK version
        try:
            http_version_map["http2_and_3"] = cloudfront.HttpVersion.HTTP2_AND_3
            http_version_map["http3"] = cloudfront.HttpVersion.HTTP3
            default_version = cloudfront.HttpVersion.HTTP2_AND_3
        except AttributeError:
            # Fall back to HTTP2 if HTTP2_AND_3/HTTP3 not available in this CDK version
            default_version = cloudfront.HttpVersion.HTTP2

        http_version = http_version_map.get(
            self.cf_config.http_version.lower(), default_version
        )

        # Price class
        price_class_map = {
            "PriceClass_100": cloudfront.PriceClass.PRICE_CLASS_100,
            "PriceClass_200": cloudfront.PriceClass.PRICE_CLASS_200,
            "PriceClass_All": cloudfront.PriceClass.PRICE_CLASS_ALL,
        }
        price_class = price_class_map.get(
            self.cf_config.price_class, cloudfront.PriceClass.PRICE_CLASS_100
        )

        # Create distribution
        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment=self.cf_config.comment or f"{self.cf_config.name} distribution",
            enabled=self.cf_config.enabled,
            domain_names=self.cf_config.aliases if self.cf_config.aliases else None,
            certificate=self.certificate,
            default_behavior=default_behavior,
            additional_behaviors=additional_behaviors if additional_behaviors else None,
            error_responses=error_responses if error_responses else None,
            http_version=http_version,
            price_class=price_class,
            default_root_object=self.cf_config.default_root_object,
            web_acl_id=self.cf_config.waf_web_acl_id,
        )

        logger.info(
            f"Created CloudFront distribution: {self.distribution.distribution_id}"
        )

    def _build_cache_behavior(
        self, config: Dict[str, Any], origin: cloudfront.IOrigin
    ) -> cloudfront.BehaviorOptions:
        """Build cache behavior with origin"""

        # Viewer protocol policy
        viewer_protocol_str = config.get("viewer_protocol_policy", "redirect-to-https")
        viewer_protocol_map = {
            "allow-all": cloudfront.ViewerProtocolPolicy.ALLOW_ALL,
            "redirect-to-https": cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            "https-only": cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
        }
        viewer_protocol_policy = viewer_protocol_map.get(
            viewer_protocol_str, cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
        )

        # Allowed methods
        allowed_methods_str = config.get("allowed_methods", ["GET", "HEAD"])
        if (
            "DELETE" in allowed_methods_str
            or "PUT" in allowed_methods_str
            or "PATCH" in allowed_methods_str
            or "POST" in allowed_methods_str
        ):
            allowed_methods = cloudfront.AllowedMethods.ALLOW_ALL
        elif "OPTIONS" in allowed_methods_str:
            allowed_methods = cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS
        else:
            allowed_methods = cloudfront.AllowedMethods.ALLOW_GET_HEAD

        # Cached methods
        cached_methods_str = config.get("cached_methods", ["GET", "HEAD"])
        if "OPTIONS" in cached_methods_str:
            cached_methods = cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS
        else:
            cached_methods = cloudfront.CachedMethods.CACHE_GET_HEAD

        # Cache policy
        cache_policy = self._build_cache_policy(config.get("cache_policy", {}))

        # Origin request policy
        origin_request_policy = self._build_origin_request_policy(
            config.get("origin_request_policy", {})
        )

        # Lambda@Edge associations
        edge_lambdas = self._build_lambda_edge_associations(
            config.get("lambda_edge_associations", [])
        )

        return cloudfront.BehaviorOptions(
            origin=origin,
            viewer_protocol_policy=viewer_protocol_policy,
            allowed_methods=allowed_methods,
            cached_methods=cached_methods,
            cache_policy=cache_policy,
            origin_request_policy=origin_request_policy,
            compress=config.get("compress", True),
            edge_lambdas=edge_lambdas if edge_lambdas else None,
        )

    def _build_cache_behavior_options(self, config: Dict[str, Any]) -> cloudfront.BehaviorOptions:
        """Build cache behavior options for additional behaviors"""
        # Get the origin for this behavior
        origin_id = config.get("target_origin_id")
        if not origin_id or origin_id not in self.origins_map:
            raise ValueError(f"Invalid target_origin_id for cache behavior: {origin_id}")
        
        origin = self.origins_map[origin_id]
        
        # Reuse the main cache behavior building logic
        return self._build_cache_behavior(config, origin)

    def _build_cache_policy(
        self, config: Dict[str, Any]
    ) -> Optional[cloudfront.ICachePolicy]:
        """Build or reference cache policy"""
        if not config:
            # Use managed caching disabled policy for dynamic content
            return cloudfront.CachePolicy.CACHING_DISABLED

        policy_name = config.get("name")

        # Check for managed policies
        managed_policies = {
            "CachingOptimized": cloudfront.CachePolicy.CACHING_OPTIMIZED,
            "CachingDisabled": cloudfront.CachePolicy.CACHING_DISABLED,
            "CachingOptimizedForUncompressedObjects": cloudfront.CachePolicy.CACHING_OPTIMIZED_FOR_UNCOMPRESSED_OBJECTS,
        }

        if policy_name in managed_policies:
            return managed_policies[policy_name]

        # Create custom cache policy
        return cloudfront.CachePolicy(
            self,
            f"CachePolicy-{policy_name}",
            cache_policy_name=policy_name,
            comment=config.get("comment", ""),
            default_ttl=Duration.seconds(config.get("default_ttl", 0)),
            min_ttl=Duration.seconds(config.get("min_ttl", 0)),
            max_ttl=Duration.seconds(config.get("max_ttl", 31536000)),
            enable_accept_encoding_gzip=config.get("enable_accept_encoding_gzip", True),
            enable_accept_encoding_brotli=config.get(
                "enable_accept_encoding_brotli", True
            ),
            header_behavior=self._build_cache_header_behavior(
                config.get("headers_config", {})
            ),
            query_string_behavior=self._build_cache_query_string_behavior(
                config.get("query_strings_config", {})
            ),
            cookie_behavior=self._build_cache_cookie_behavior(
                config.get("cookies_config", {})
            ),
        )

    def _build_origin_request_policy(
        self, config: Dict[str, Any]
    ) -> Optional[cloudfront.IOriginRequestPolicy]:
        """Build or reference origin request policy"""
        if not config:
            # Use managed all viewer policy
            return cloudfront.OriginRequestPolicy.ALL_VIEWER

        policy_name = config.get("name")

        # Check for managed policies
        managed_policies = {
            "AllViewer": cloudfront.OriginRequestPolicy.ALL_VIEWER,
            "AllViewerExceptHostHeader": cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            "AllViewerAndCloudFrontHeaders2022": cloudfront.OriginRequestPolicy.ALL_VIEWER_AND_CLOUDFRONT_2022,
            "CORS-CustomOrigin": cloudfront.OriginRequestPolicy.CORS_CUSTOM_ORIGIN,
            "CORS-S3Origin": cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
        }

        if policy_name in managed_policies:
            return managed_policies[policy_name]

        # Create custom origin request policy
        return cloudfront.OriginRequestPolicy(
            self,
            f"OriginRequestPolicy-{policy_name}",
            origin_request_policy_name=policy_name,
            comment=config.get("comment", ""),
            header_behavior=self._build_origin_header_behavior(
                config.get("headers_config", {})
            ),
            query_string_behavior=self._build_origin_query_string_behavior(
                config.get("query_strings_config", {})
            ),
            cookie_behavior=self._build_origin_cookie_behavior(
                config.get("cookies_config", {})
            ),
        )

    def _build_cache_header_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.CacheHeaderBehavior:
        """Build cache header behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.CacheHeaderBehavior.none()
        elif behavior == "whitelist":
            headers = config.get("headers", [])
            return cloudfront.CacheHeaderBehavior.allow_list(*headers)
        else:
            return cloudfront.CacheHeaderBehavior.none()

    def _build_cache_query_string_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.CacheQueryStringBehavior:
        """Build cache query string behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.CacheQueryStringBehavior.none()
        elif behavior == "all":
            return cloudfront.CacheQueryStringBehavior.all()
        elif behavior == "whitelist":
            query_strings = config.get("query_strings", [])
            return cloudfront.CacheQueryStringBehavior.allow_list(*query_strings)
        elif behavior == "allExcept":
            query_strings = config.get("query_strings", [])
            return cloudfront.CacheQueryStringBehavior.deny_list(*query_strings)
        else:
            return cloudfront.CacheQueryStringBehavior.none()

    def _build_cache_cookie_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.CacheCookieBehavior:
        """Build cache cookie behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.CacheCookieBehavior.none()
        elif behavior == "all":
            return cloudfront.CacheCookieBehavior.all()
        elif behavior == "whitelist":
            cookies = config.get("cookies", [])
            return cloudfront.CacheCookieBehavior.allow_list(*cookies)
        elif behavior == "allExcept":
            cookies = config.get("cookies", [])
            return cloudfront.CacheCookieBehavior.deny_list(*cookies)
        else:
            return cloudfront.CacheCookieBehavior.none()

    def _build_origin_header_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.OriginRequestHeaderBehavior:
        """Build origin request header behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.OriginRequestHeaderBehavior.none()
        elif behavior == "all":
            return cloudfront.OriginRequestHeaderBehavior.all()
        elif behavior == "whitelist":
            headers = config.get("headers", [])
            return cloudfront.OriginRequestHeaderBehavior.allow_list(*headers)
        elif behavior == "allViewerAndWhitelistCloudFront":
            # For now, just forward all headers - this matches the intent
            return cloudfront.OriginRequestHeaderBehavior.all()
        else:
            return cloudfront.OriginRequestHeaderBehavior.none()

    def _build_origin_query_string_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.OriginRequestQueryStringBehavior:
        """Build origin request query string behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.OriginRequestQueryStringBehavior.none()
        elif behavior == "all":
            return cloudfront.OriginRequestQueryStringBehavior.all()
        elif behavior == "whitelist":
            query_strings = config.get("query_strings", [])
            return cloudfront.OriginRequestQueryStringBehavior.allow_list(
                *query_strings
            )
        elif behavior == "allExcept":
            query_strings = config.get("query_strings", [])
            return cloudfront.OriginRequestQueryStringBehavior.deny_list(*query_strings)
        else:
            return cloudfront.OriginRequestQueryStringBehavior.none()

    def _build_origin_cookie_behavior(
        self, config: Dict[str, Any]
    ) -> cloudfront.OriginRequestCookieBehavior:
        """Build origin request cookie behavior"""
        behavior = config.get("behavior", "none")

        if behavior == "none":
            return cloudfront.OriginRequestCookieBehavior.none()
        elif behavior == "all":
            return cloudfront.OriginRequestCookieBehavior.all()
        elif behavior == "whitelist":
            cookies = config.get("cookies", [])
            return cloudfront.OriginRequestCookieBehavior.allow_list(*cookies)
        else:
            return cloudfront.OriginRequestCookieBehavior.none()

    def _build_lambda_edge_associations(
        self, associations: List[Dict[str, Any]]
    ) -> Optional[List[cloudfront.EdgeLambda]]:
        """Build Lambda@Edge associations"""
        if not associations:
            return None

        edge_lambdas = []

        for assoc in associations:
            event_type_str = assoc.get("event_type", "origin-request")
            lambda_arn = assoc.get("lambda_arn")

            if not lambda_arn:
                continue

            # Check if ARN is a placeholder from ssm_imports
            if lambda_arn.startswith("{{") and lambda_arn.endswith("}}"):
                placeholder_key = lambda_arn[2:-2]  # Remove {{ and }}
                if placeholder_key in self.ssm_imported_values:
                    lambda_arn = self.ssm_imported_values[placeholder_key]
                    logger.info(
                        f"Resolved Lambda ARN from SSM import: {placeholder_key}"
                    )
                else:
                    logger.warning(f"Placeholder {lambda_arn} not found in SSM imports")

            # Legacy support: Check if ARN is an SSM parameter reference
            elif lambda_arn.startswith("{{ssm:") and lambda_arn.endswith("}}"):
                ssm_param = lambda_arn[6:-2]
                lambda_arn = ssm.StringParameter.value_from_lookup(self, ssm_param)
                logger.info(f"Resolved Lambda ARN from SSM lookup {ssm_param}")

            # Map event type
            event_type_map = {
                "viewer-request": cloudfront.LambdaEdgeEventType.VIEWER_REQUEST,
                "origin-request": cloudfront.LambdaEdgeEventType.ORIGIN_REQUEST,
                "origin-response": cloudfront.LambdaEdgeEventType.ORIGIN_RESPONSE,
                "viewer-response": cloudfront.LambdaEdgeEventType.VIEWER_RESPONSE,
            }

            event_type = event_type_map.get(
                event_type_str, cloudfront.LambdaEdgeEventType.ORIGIN_REQUEST
            )

            # Import Lambda version
            lambda_version = _lambda.Version.from_version_arn(
                self, f"LambdaEdge-{event_type_str}", version_arn=lambda_arn
            )

            edge_lambdas.append(
                cloudfront.EdgeLambda(
                    function_version=lambda_version,
                    event_type=event_type,
                    include_body=assoc.get("include_body", False),
                )
            )

        return edge_lambdas if edge_lambdas else None

    def _export_ssm_parameters(self) -> None:
        """Export distribution info to SSM Parameter Store"""
        ssm_exports = self.cf_config.ssm_exports

        if not ssm_exports:
            return

        if "distribution_id" in ssm_exports:
            param_name = ssm_exports["distribution_id"]
            if not param_name.startswith("/"):
                param_name = f"/{param_name}"
            ssm.StringParameter(
                self,
                "DistributionIdParam",
                parameter_name=param_name,
                string_value=self.distribution.distribution_id,
                description=f"CloudFront Distribution ID for {self.cf_config.name}",
            )

        if "distribution_domain" in ssm_exports:
            param_name = ssm_exports["distribution_domain"]
            if not param_name.startswith("/"):
                param_name = f"/{param_name}"
            ssm.StringParameter(
                self,
                "DistributionDomainParam",
                parameter_name=param_name,
                string_value=self.distribution.distribution_domain_name,
                description=f"CloudFront Distribution Domain for {self.cf_config.name}",
            )

        if "distribution_arn" in ssm_exports:
            param_name = ssm_exports["distribution_arn"]
            if not param_name.startswith("/"):
                param_name = f"/{param_name}"
            ssm.StringParameter(
                self,
                "DistributionArnParam",
                parameter_name=param_name,
                string_value=f"arn:aws:cloudfront::{self.account}:distribution/{self.distribution.distribution_id}",
                description=f"CloudFront Distribution ARN for {self.cf_config.name}",
            )

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "DistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront Distribution ID",
        )

        CfnOutput(
            self,
            "DistributionDomain",
            value=self.distribution.distribution_domain_name,
            description="CloudFront Distribution Domain Name",
        )

        if self.cf_config.aliases:
            CfnOutput(
                self,
                "DistributionAliases",
                value=",".join(self.cf_config.aliases),
                description="CloudFront Distribution Aliases",
            )
