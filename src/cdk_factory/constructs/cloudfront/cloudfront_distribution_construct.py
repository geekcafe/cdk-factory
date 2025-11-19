from typing import Any, List, Mapping, Optional

import aws_cdk as cdk
from aws_cdk import Duration
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.configurations.stack import StackConfig

logger = Logger(__name__)


class CloudFrontDistributionConstruct(Construct):
    """
    CloudFrontDistributionConstruct is a construct that creates a CloudFront distribution for the given bucket.
    """

    AWS_HOSTED_ZONE_ID: str = "Z2FDTNDATAQYW2"

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        source_bucket: s3.IBucket,
        aliases: List[str] | None,
        source_bucket_sub_directory: str | None = None,
        certificate: acm.Certificate | None = None,
        restrict_to_known_hosts: bool = True,
        stack_config: StackConfig | None = None,
    ):
        super().__init__(scope=scope, id=id)
        self.source_bucket: s3.IBucket = source_bucket
        self.distribution: cloudfront.Distribution
        self.oai: cloudfront.OriginAccessIdentity
        self.aliases = aliases
        self.source_bucket_sub_directory = source_bucket_sub_directory
        self.certificate = certificate
        self.restrict_to_known_hosts = restrict_to_known_hosts
        self.use_oac: bool = True
        self.stack_config = stack_config
        self.__setup()
        self.create()

    @property
    def dns_name(self) -> str:
        """
        Get the domain name of the codl

        Returns:
            str: domain name
        """
        return self.distribution.distribution_domain_name

    @property
    def distribution_id(self) -> str:
        """
        Get the distribution id

        Returns:
            str: distribution id
        """
        return self.distribution.distribution_id

    @property
    def hosted_zone_id(self) -> str:
        """
        Gets the AWS Hosted Zone ID for the distribution.
        As of know, this value does not change

        Returns:
            str: hosted zone id
        """
        return CloudFrontDistributionConstruct.AWS_HOSTED_ZONE_ID

    def __validate_function_associations(self):
        """
        Validate CloudFront function association configuration.
        Provides clear error messages for common misconfigurations.
        
        CloudFront limits:
        - 1 CloudFront Function (JavaScript) per event type
        - 1 Lambda@Edge (Python/Node) per event type
        - Different types CAN coexist at same event type
        """
        if not self.stack_config or not isinstance(self.stack_config, StackConfig):
            return  # No config to validate
        
        cloudfront_config = self.stack_config.dictionary.get("cloudfront", {})
        
        # Get configuration flags
        enable_url_rewrite = cloudfront_config.get("enable_url_rewrite", False)
        enable_ip_gating = cloudfront_config.get("enable_ip_gating", False)
        restrict_to_known_hosts = cloudfront_config.get("restrict_to_known_hosts", self.restrict_to_known_hosts)
        
        # Count CloudFront Functions at viewer-request
        cloudfront_functions_at_viewer_request = 0
        if enable_url_rewrite:
            cloudfront_functions_at_viewer_request += 1
        if restrict_to_known_hosts and self.aliases:
            cloudfront_functions_at_viewer_request += 1
        
        # Note: Multiple CloudFront Functions are OK - we combine them automatically
        if cloudfront_functions_at_viewer_request > 1:
            logger.info(
                f"Multiple CloudFront Functions at viewer-request detected. "
                f"Will combine into single function. "
                f"Features: enable_url_rewrite={enable_url_rewrite}, "
                f"restrict_to_known_hosts={restrict_to_known_hosts}"
            )
        
        # Check for manual Lambda@Edge associations that might conflict
        lambda_edge_associations = cloudfront_config.get("lambda_edge_associations", [])
        manual_viewer_request = any(
            assoc.get("event_type") == "viewer-request" 
            for assoc in lambda_edge_associations
        )
        
        # ERROR: Manual Lambda@Edge + enable_ip_gating both at viewer-request
        if enable_ip_gating and manual_viewer_request:
            raise ValueError(
                "Configuration conflict: Cannot use both 'enable_ip_gating: true' "
                "and manual 'lambda_edge_associations' with 'event_type: viewer-request'. "
                "\n\nSolution 1 (Recommended): Use only 'enable_ip_gating: true' "
                "and remove manual lambda_edge_associations."
                "\n\nSolution 2: Use only manual lambda_edge_associations "
                "and set 'enable_ip_gating: false'."
                "\n\nCurrent config:"
                f"\n  enable_ip_gating: {enable_ip_gating}"
                f"\n  lambda_edge_associations with viewer-request: {manual_viewer_request}"
            )
        
        # WARNING: Both Lambda@Edge IP gating and CloudFront Functions enabled
        # This is VALID but might indicate misconfiguration
        if enable_ip_gating and cloudfront_functions_at_viewer_request > 0:
            features = []
            if enable_url_rewrite:
                features.append("URL rewrite")
            if restrict_to_known_hosts:
                features.append("Host restrictions")
            
            logger.info(
                f"✓ CloudFront configuration at viewer-request:"
                f"\n  - CloudFront Function: {', '.join(features)}"
                f"\n  - Lambda@Edge: IP gating"
                f"\nThis is valid: CloudFront Functions and Lambda@Edge can coexist "
                f"at the same event type."
            )

    def __setup(self):
        """
        Any setup / init logic goes here
        """
        # Validate CloudFront function association configuration
        self.__validate_function_associations()
        
        self.oai = cloudfront.OriginAccessIdentity(
            self, "OAI", comment="OAI for accessing S3 bucket content securely"
        )

        if isinstance(self.aliases, list):
            if len(self.aliases) == 0:
                self.aliases = None

        if self.aliases and not isinstance(self.aliases, list):
            raise ValueError("Aliases must be a list of strings or None")

    def create(self) -> cloudfront.Distribution:
        """
        Create the distribution

        Returns:
            cloudfront.Distribution: the distribution object
        """
        # print(f"cloudfront dist {self.aliases}")
        # print(f"cert: {self.certificate}")
        
        # Prepare origin_path - only set if we have a subdirectory
        origin_kwargs = {}
        if self.source_bucket_sub_directory:
            origin_kwargs["origin_path"] = f"/{self.source_bucket_sub_directory}"
        
        origin: origins.S3Origin | cloudfront.IOrigin
        if self.use_oac:
            origin = origins.S3BucketOrigin.with_origin_access_control(
                self.source_bucket,
                **origin_kwargs,
                origin_access_levels=[
                    cloudfront.AccessLevel.READ,
                    cloudfront.AccessLevel.LIST,
                ],
            )
        else:
            origin = origins.S3Origin(
                self.source_bucket,
                **origin_kwargs,
                origin_access_identity=self.oai,
            )

        # Get comment from config, or use default
        comment = "CloudFront Distribution generated via the CDK Factory"
        if self.stack_config and isinstance(self.stack_config, StackConfig):
            cloudfront_config = self.stack_config.dictionary.get("cloudfront", {})
            comment = cloudfront_config.get("comment", comment)
        
        distribution = cloudfront.Distribution(
            self,
            "cloudfront-dist",
            domain_names=self.aliases,
            comment=comment,
            certificate=self.certificate,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=self.__get_function_associations(),
                edge_lambdas=self.__get_lambda_edge_associations(),
            ),
            default_root_object="index.html",
            error_responses=self._error_responses(),
        )

        self.__update_bucket_policy(distribution)

        self.distribution = distribution

        return distribution

    def _error_responses(self) -> List[cloudfront.ErrorResponse]:
        """
        Get the error responses for the distribution

        Returns:
            List[cloudfront.ErrorResponse]: list of error responses
        """
        error_responses = []

        if self.stack_config and isinstance(self.stack_config, StackConfig):
            cloudfront_error_responses = self.stack_config.dictionary.get(
                "cloudfront", {}
            ).get("error_responses", [])

            for error_response in cloudfront_error_responses:

                http_status = error_response.get("http_status")
                response_page_path = error_response.get("response_page_path")
                response_http_status = error_response.get("response_http_status")
                ttl = Duration.seconds(int(error_response.get("ttl", 0)))

                if (
                    not http_status
                    or not response_page_path
                    or not response_http_status
                ):
                    raise ValueError(
                        "http_status, response_page_path, and response_http_status are required "
                        "in stack.cloudfront.error_responses. Check your stack config"
                    )
                error_responses.append(
                    cloudfront.ErrorResponse(
                        http_status=int(http_status),
                        response_page_path=response_page_path,
                        response_http_status=int(response_http_status),
                        ttl=ttl,
                    )
                )

        return error_responses

    def __get_function_associations(self) -> List[cloudfront.FunctionAssociation]:
        """
        Get the function associations for the distribution

        Returns:
            List[cloudfront.FunctionAssociation]: list of function associations
        """
        function_associations = []

        # Check if URL rewrite is enabled for SPA/static site routing
        enable_url_rewrite = False
        if self.stack_config and isinstance(self.stack_config, StackConfig):
            cloudfront_config = self.stack_config.dictionary.get("cloudfront", {})
            enable_url_rewrite = cloudfront_config.get("enable_url_rewrite", False)
        
        # CloudFront only allows ONE function per event type
        # If both URL rewrite and host restrictions are needed, combine them
        if enable_url_rewrite and self.restrict_to_known_hosts and self.aliases:
            function_associations.append(
                cloudfront.FunctionAssociation(
                    function=self.__get_combined_function(hosts=self.aliases),
                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                )
            )
        elif enable_url_rewrite:
            function_associations.append(
                cloudfront.FunctionAssociation(
                    function=self.__get_url_rewrite_function(),
                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                )
            )
        elif self.restrict_to_known_hosts and self.aliases:
            function_associations.append(
                cloudfront.FunctionAssociation(
                    function=self.__get_cloudfront_host_restrictions(
                        hosts=self.aliases
                    ),
                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                )
            )

        return function_associations

    def __get_lambda_edge_associations(self) -> Optional[List[cloudfront.EdgeLambda]]:
        """
        Get the Lambda@Edge associations for the distribution from config.
        
        Supports two configuration methods:
        1. Convenience flag: "enable_ip_gating": true
           - Automatically adds Lambda@Edge IP gating function
           - Uses auto-derived SSM parameter path: /{env}/{workload}/lambda-edge/version-arn
        
        2. Manual configuration: "lambda_edge_associations": [...]
           - Full control over Lambda@Edge associations
           - Can specify custom ARNs, event types, etc.
        
        Returns:
            List[cloudfront.EdgeLambda] or None: list of Lambda@Edge associations
        """
        edge_lambdas = []
        
        if self.stack_config and isinstance(self.stack_config, StackConfig):
            cloudfront_config = self.stack_config.dictionary.get("cloudfront", {})
            
            # Check for convenience IP gating flag
            enable_ip_gating = cloudfront_config.get("enable_ip_gating", False)
            if enable_ip_gating:
                logger.info("IP gating enabled via convenience flag - adding Lambda@Edge association")
                
                # Extract environment and workload name from config
                # Architecture: One workload deployment = One environment
                workload_dict = self.stack_config.workload
                
                # CRITICAL: Environment must be at workload level - no defaults!
                # Defaulting to "dev" is dangerous and can cause cross-environment contamination
                # Try workload["environment"] first (STANDARD), then workload["deployment"]["environment"] (legacy)
                environment = workload_dict.get("environment")
                if not environment:
                    # Backward compatibility: try deployment.environment
                    environment = workload_dict.get("deployment", {}).get("environment")
                
                if not environment:
                    raise ValueError(
                        "Environment must be explicitly specified at workload level. "
                        "Cannot default to 'dev' as this may cause cross-environment resource contamination. "
                        "Best practice: Add 'environment' to your workload config:\n"
                        '  {\"workload\": {\"name\": \"...\", \"environment\": \"dev|prod\"}}\n'
                        "Legacy: 'deployment.environment' is also supported for backward compatibility."
                    )
                
                workload_name = workload_dict.get("name")
                if not workload_name:
                    raise ValueError(
                        "Workload name must be specified in configuration. "
                        "Please set 'name' in your workload config."
                    )
                
                # Auto-derive SSM parameter path or use override
                default_ssm_path = f"/{environment}/{workload_name}/lambda-edge/version-arn"
                ip_gate_ssm_path = cloudfront_config.get("ip_gate_function_ssm_path", default_ssm_path)
                
                logger.info(f"Using IP gate Lambda ARN from SSM: {ip_gate_ssm_path}")
                
                # Add the IP gating Lambda@Edge association
                # MUST use viewer-request to run BEFORE cache check!
                lambda_edge_associations = [{
                    "event_type": "viewer-request",
                    "lambda_arn": f"{{{{ssm:{ip_gate_ssm_path}}}}}",
                    "include_body": False
                }]
            else:
                # Use manual configuration
                lambda_edge_associations = cloudfront_config.get("lambda_edge_associations", [])
            
            for association in lambda_edge_associations:
                event_type_str = association.get("event_type", "origin-request")
                lambda_arn = association.get("lambda_arn")
                include_body = association.get("include_body", False)
                
                if not lambda_arn:
                    continue  # Skip if no ARN provided
                
                # Check if ARN is an SSM parameter reference
                if lambda_arn.startswith("{{ssm:") and lambda_arn.endswith("}}"):
                    ssm_param_path = lambda_arn[6:-2]  # Extract parameter path
                    logger.info(f"Importing Lambda ARN from SSM parameter: {ssm_param_path}")
                    
                    # CRITICAL: Import SSM parameter using CloudFormation parameter type
                    # This ensures CloudFormation validates the parameter EXISTS at deployment time
                    # If the parameter is missing, CloudFormation will FAIL the deployment
                    # This prevents accidentally using wrong/missing Lambda@Edge functions
                    
                    # Create CloudFormation parameter that resolves SSM value
                    cfn_param = cdk.CfnParameter(
                        self,
                        f"lambda-edge-arn-{hash(ssm_param_path) % 10000}-param",
                        type="AWS::SSM::Parameter::Value<String>",
                        default=ssm_param_path,
                        description=f"Lambda@Edge function ARN from SSM: {ssm_param_path}"
                    )
                    lambda_arn = cfn_param.value_as_string
                    logger.info(f"Lambda ARN will be resolved from SSM (validated at deploy): {ssm_param_path}")
                
                # Map event type string to CloudFront enum
                event_type_map = {
                    "viewer-request": cloudfront.LambdaEdgeEventType.VIEWER_REQUEST,
                    "origin-request": cloudfront.LambdaEdgeEventType.ORIGIN_REQUEST,
                    "origin-response": cloudfront.LambdaEdgeEventType.ORIGIN_RESPONSE,
                    "viewer-response": cloudfront.LambdaEdgeEventType.VIEWER_RESPONSE,
                }
                
                event_type = event_type_map.get(event_type_str, cloudfront.LambdaEdgeEventType.ORIGIN_REQUEST)
                
                # Import the Lambda function version by ARN
                lambda_version = _lambda.Version.from_version_arn(
                    self,
                    f"LambdaEdge-{event_type_str}",
                    version_arn=lambda_arn
                )
                
                edge_lambdas.append(
                    cloudfront.EdgeLambda(
                        function_version=lambda_version,
                        event_type=event_type,
                        include_body=include_body
                    )
                )
        
        return edge_lambdas if edge_lambdas else None

    def __get_combined_function(self, hosts: List[str]) -> cloudfront.Function:
        """
        Creates a combined CloudFront function that does both URL rewriting and host restrictions.
        This is necessary because CloudFront only allows one function per event type.
        
        Args:
            hosts: List of allowed hostnames
            
        Returns:
            cloudfront.Function: Combined function
        """
        allowed_hosts = "[" + ", ".join(f"'{host}'" for host in hosts) + "]"
        
        function_code = f"""
        function handler(event) {{
            var request = event.request;
            var allowedHosts = {allowed_hosts};
            var hostHeader = request.headers.host.value;
            
            // Check host restrictions first
            if (allowedHosts.indexOf(hostHeader) === -1) {{
                return {{ statusCode: 403, statusDescription: 'Forbidden' }};
            }}
            
            // Then do URL rewrite
            var uri = request.uri;
            
            // If URI doesn't have a file extension and doesn't end with /
            if (!uri.includes('.') && !uri.endsWith('/')) {{
                request.uri = uri + '/index.html';
            }}
            // If URI ends with / but not index.html
            else if (uri.endsWith('/') && !uri.endsWith('index.html')) {{
                request.uri = uri + 'index.html';
            }}
            // If URI is exactly /
            else if (uri === '/') {{
                request.uri = '/index.html';
            }}
            
            return request;
        }}
        """

        combined_function = cloudfront.Function(
            self,
            "CombinedFunction",
            comment="Combined URL rewrite and host restrictions for static site routing",
            code=cloudfront.FunctionCode.from_inline(function_code),
        )
        return combined_function

    def __get_url_rewrite_function(self) -> cloudfront.Function:
        """
        Creates a CloudFront function that rewrites URLs for SPA/static site routing.
        This enables clean URLs by routing /about to /about/index.html
        
        Returns:
            cloudfront.Function: URL rewrite function for static site routing
        """
        function_code = """
        function handler(event) {
            var request = event.request;
            var uri = request.uri;
            
            // If URI doesn't have a file extension and doesn't end with /
            if (!uri.includes('.') && !uri.endsWith('/')) {
                request.uri = uri + '/index.html';
            }
            // If URI ends with / but not index.html
            else if (uri.endsWith('/') && !uri.endsWith('index.html')) {
                request.uri = uri + 'index.html';
            }
            // If URI is exactly /
            else if (uri === '/') {
                request.uri = '/index.html';
            }
            
            return request;
        }
        """

        url_rewrite_function = cloudfront.Function(
            self,
            "UrlRewriteFunction",
            comment="Rewrites clean URLs to /folder/index.html for static site routing",
            code=cloudfront.FunctionCode.from_inline(function_code),
        )
        return url_rewrite_function

    def __get_cloudfront_host_restrictions(
        self, hosts: List[str]
    ) -> cloudfront.Function:
        allowed_hosts = "[" + ", ".join(f"'{host}'" for host in hosts) + "]"

        # Create the inline function code with the dynamic allowedHosts.
        function_code = f"""
        function handler(event) {{
            var request = event.request;
            var allowedHosts = {allowed_hosts};
            var hostHeader = request.headers.host.value;
            
            // If the Host header is not in the allowed list, return a 403.
            if (allowedHosts.indexOf(hostHeader) === -1) {{
                return {{ statusCode: 403, statusDescription: 'Forbidden' }};
            }}
            return request;
        }}
        """

        restrict_function = cloudfront.Function(
            self,
            "RestrictHostHeaderFunction",
            code=cloudfront.FunctionCode.from_inline(function_code),
        )
        return restrict_function

    def __update_bucket_policy(self, distribution: cloudfront.Distribution):
        """
        Update the bucket policy to allow access to the distribution
        """
        bucket_policy = s3.BucketPolicy(
            self,
            id="CloudFrontBucketPolicy",
            bucket=self.source_bucket,
        )

        if self.use_oac:
            bucket_policy.document.add_statements(
                self.__get_policy_statement_for_oac(distribution=distribution)
            )
        else:
            bucket_policy.document.add_statements(self.__get_policy_statement_for_oai())

    def __get_policy_statement_for_oai(self) -> iam.PolicyStatement:
        """
        get the policy statement for the OAI

        Returns:
            iam.PolicyStatement: policy statement for the OAI
        """

        principals = [
            iam.CanonicalUserPrincipal(
                self.oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )
        ]
        statement = self.__build_policy_s(principals=principals)

        return statement

    def __get_policy_statement_for_oac(
        self, distribution: cloudfront.Distribution
    ) -> iam.PolicyStatement:
        """
        get the policy statement for the OAC

        Returns:
            iam.PolicyStatement: policy statement for the OAC
        """
        conditions = {"StringEquals": {"AWS:SourceArn": distribution.distribution_arn}}
        principals = [iam.ServicePrincipal("cloudfront.amazonaws.com")]
        statement = self.__build_policy_s(conditions=conditions, principals=principals)
        # statement.principals.append(iam.ServicePrincipal("cloudfront.amazonaws.com"))

        return statement

    def __build_policy_s(
        self, conditions: Mapping[str, Any] | None = None, principals: Any | None = None
    ) -> iam.PolicyStatement:
        """
        Get the base policy statement for the bucket policy

        Returns:
            iam.PolicyStatement: base policy statement
        """
        statement = iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[
                self.source_bucket.arn_for_objects("*"),
                self.source_bucket.bucket_arn,
            ],
            conditions=conditions,
            principals=principals,
        )

        return statement
