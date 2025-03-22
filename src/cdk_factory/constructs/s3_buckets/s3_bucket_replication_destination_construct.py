"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List

from aws_cdk import aws_iam, aws_s3
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.s3_buckets.s3_bucket_construct import S3BucketConstruct

logger = Logger(__name__)


class S3BucketReplicationDestinationConstruct(Construct):
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
        c = S3BucketConstruct(
            self, "bucket", stack_config=stack_config, deployment=deployment, **kwargs
        )
        self.bucket: aws_s3.IBucket = c.bucket

        c.verify_replication_ready()

    def add_replication_permissions(self, source_accounts: List[str] | str) -> None:
        """
        Adds the policies to allow external accounts to replicate to this bucket
        """

        if isinstance(source_accounts, str):
            source_accounts = [source_accounts]

        for account in source_accounts:
            self.bucket.add_to_resource_policy(
                aws_iam.PolicyStatement(
                    sid=f"SourceAccessToReplicateIntoBucket-{account}",
                    effect=aws_iam.Effect.ALLOW,
                    principals=[aws_iam.AccountPrincipal(account_id=account)],
                    actions=[
                        "s3:ReplicateObject",
                        "s3:ReplicateDelete",
                        "s3:ReplicateTags",
                        "s3:GetObjectVersionTagging",
                        "s3:ObjectOwnerOverrideToBucketOwner",
                    ],
                    resources=[self.bucket.arn_for_objects("*")],
                )
            )

            self.bucket.add_to_resource_policy(
                aws_iam.PolicyStatement(
                    sid=f"SourceAccessToVersioning-{account}",
                    effect=aws_iam.Effect.ALLOW,
                    principals=[aws_iam.AccountPrincipal(account_id=account)],
                    actions=["s3:GetBucketVersioning", "s3:PutBucketVersioning"],
                    resources=[self.bucket.bucket_arn],
                )
            )
