from typing import Any, List, Mapping

from aws_cdk import Duration
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct
from cdk_factory.configurations.stack import StackConfig


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

    def __setup(self):
        """
        Any setup / init logic goes here
        """
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
        origin: origins.S3Origin | cloudfront.IOrigin
        if self.use_oac:
            origin = origins.S3BucketOrigin.with_origin_access_control(
                self.source_bucket,
                origin_path=f"/{self.source_bucket_sub_directory}",
                origin_access_levels=[
                    cloudfront.AccessLevel.READ,
                    cloudfront.AccessLevel.LIST,
                ],
            )
        else:
            origin = origins.S3Origin(
                self.source_bucket,
                origin_path=f"/{self.source_bucket_sub_directory}",
                origin_access_identity=self.oai,
            )

        distribution = cloudfront.Distribution(
            self,
            "cloudfront-dist",
            domain_names=self.aliases,
            comment="CloudFront Distribution generated via the CDK Factory",
            certificate=self.certificate,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=self.__get_function_associations(),
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

        if self.restrict_to_known_hosts and self.aliases:
            function_associations.append(
                cloudfront.FunctionAssociation(
                    function=self.__get_cloudfront_host_restrictions(
                        hosts=self.aliases
                    ),
                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                )
            )

        return function_associations

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
            id=f"CloudFrontBucketPolicy-{self.source_bucket.bucket_name}",
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
