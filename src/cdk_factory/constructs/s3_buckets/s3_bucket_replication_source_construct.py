"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Optional, cast

from aws_cdk import aws_iam, aws_s3
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.s3_buckets.s3_bucket_construct import S3BucketConstruct

logger = Logger(__name__)


class S3BucketReplicationSourceConstruct(Construct):
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
            self,
            "source-bucket",
            stack_config=stack_config,
            deployment=deployment,
            **kwargs,
        )

        c.verify_replication_ready()

        self.source_bucket: aws_s3.IBucket = c.bucket

    def add_replication_permissions(
        self, destination_bucket_name: str, destination_account: Optional[str] = None
    ) -> None:
        """
        Adds the permission to allow
        """
        destination_bucket = aws_s3.Bucket.from_bucket_arn(
            self,
            "DestinationBucket",
            bucket_arn=f"arn:aws:s3:::{destination_bucket_name}",
        )

        replication_role = aws_iam.Role(
            self,
            "ReplicationRole",
            assumed_by=aws_iam.ServicePrincipal("s3.amazonaws.com"),
            path="/service-role/",
        )

        replication_role.add_to_policy(
            aws_iam.PolicyStatement(
                resources=[self.source_bucket.bucket_arn],
                actions=["s3:GetReplicationConfiguration", "s3:ListBucket"],
            )
        )

        replication_role.add_to_policy(
            aws_iam.PolicyStatement(
                resources=[self.source_bucket.arn_for_objects("*")],
                actions=[
                    "s3:GetObjectVersion",
                    "s3:GetObjectVersionAcl",
                    "s3:GetObjectVersionForReplication",
                    "s3:GetObjectLegalHold",
                    "s3:GetObjectVersionTagging",
                    "s3:GetObjectRetention",
                    "s3:ObjectOwnerOverrideToBucketOwner",
                ],
            )
        )

        replication_role.add_to_policy(
            aws_iam.PolicyStatement(
                resources=[destination_bucket.arn_for_objects("*")],
                actions=[
                    "s3:ReplicateObject",
                    "s3:ReplicateDelete",
                    "s3:ReplicateTags",
                ],
            )
        )

        # Ensure that the default child is not None and is a CfnBucket.
        cfn_bucket = cast(aws_s3.CfnBucket, self.source_bucket.node.default_child)
        if cfn_bucket is None:
            raise ValueError("Default child of source_bucket is None.")

        # Now you can safely assign the replication configuration.
        cfn_bucket.replication_configuration = (
            aws_s3.CfnBucket.ReplicationConfigurationProperty(
                role=replication_role.role_arn,
                rules=[
                    aws_s3.CfnBucket.ReplicationRuleProperty(
                        destination=aws_s3.CfnBucket.ReplicationDestinationProperty(
                            bucket=destination_bucket.bucket_arn,
                            account=destination_account,
                        ),
                        status="Enabled",
                    )
                ],
            )
        )
