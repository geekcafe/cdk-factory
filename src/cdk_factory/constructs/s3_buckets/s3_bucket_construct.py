"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_cdk import aws_s3 as s3
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.resource_types import ResourceTypes

logger = Logger(__name__)


class S3BucketConstruct(Construct):
    """S3 Bucket Construct"""

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        *,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.bucket_config = S3BucketConfig(stack_config.dictionary.get("bucket", {}))
        self.deployment = deployment
        bucket_name = deployment.build_resource_name(
            self.bucket_config.name, ResourceTypes.S3_BUCKET
        )

        bucket: s3.IBucket
        if self.bucket_config.exists:
            logger.info("using an existing bucket")
            bucket = s3.Bucket.from_bucket_name(
                self,
                id=bucket_name,
                bucket_name=bucket_name,
            )

            # this should get us a bucket that we can now modify
            bucket = s3.Bucket.from_bucket_attributes(
                self,
                id=f"{bucket_name}-attr",
                bucket_arn=bucket.bucket_arn,
            )

        else:
            logger.debug("creating a new bucket")

            bucket = s3.Bucket(
                self,
                id=bucket_name,
                bucket_name=f"{bucket_name}",
                public_read_access=self.bucket_config.public_read_access,
                access_control=self.bucket_config.access_control,
                block_public_access=self.bucket_config.block_public_access,
                encryption=self.bucket_config.encryption,
                enforce_ssl=self.bucket_config.enforce_ssl,
                versioned=self.bucket_config.versioned,
                auto_delete_objects=self.bucket_config.auto_delete_objects,
                removal_policy=self.bucket_config.removal_policy,
                # TODO: add the other rules to the config
                ######################################################
                # don't do this if you plan to do a cloudfront distribution
                # it breaks the cloudfront distribution - it's configured in cloudfront instead
                # website_index_document="index.html",
            )

            # bucket.replication_role_arn

        self.bucket: s3.IBucket = bucket

    def is_versioned(self) -> bool:
        """returns if this bucket is configured for versioning"""
        return self.bucket_config.versioned

    def verify_replication_ready(self) -> bool:
        """Determines if the bucket is configured correctly for replications"""
        if not self.is_versioned():
            raise RuntimeError(
                "Bucket is not versioned.  Versioning is required for replication."
            )

        return True

        
