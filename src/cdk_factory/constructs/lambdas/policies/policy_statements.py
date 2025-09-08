"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List
from aws_cdk import aws_iam as iam
from constructs import Construct


class PolicyStatements:
    """Reusable Policy Statements"""

    @staticmethod
    def log_group_policy_statement() -> iam.PolicyStatement:
        # Custom Policy for the Lambda Role
        statement = iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=["arn:aws:logs:*:*:*"],
            effect=iam.Effect.ALLOW,
        )
        return statement

    @staticmethod
    def lambda_insights_policy_statement() -> iam.PolicyStatement:
        statement = iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        return statement

    @staticmethod
    def bucket_read_policy_statement(bucket_name: str) -> iam.PolicyStatement:
        statement = iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:ListBucket",
                "s3:ListBucketMultipartUploads",
                "s3:ListMultipartUploadParts",
            ],
            resources=[
                f"arn:aws:s3:::{bucket_name}",
                f"arn:aws:s3:::{bucket_name}/*",
            ],
            effect=iam.Effect.ALLOW,
        )
        return statement

    @staticmethod
    def bucket_read_write_policy_statement(bucket_name: str) -> iam.PolicyStatement:
        statement = PolicyStatements.bucket_read_policy_statement(
            bucket_name=bucket_name
        )

        statement.actions.append("s3:PutObject")
        statement.actions.append("s3:PutObjectAcl")
        statement.actions.append("s3:PutObjectTagging")
        statement.actions.append("s3:AbortMultipartUpload")
        statement.actions.append("s3:GetBucketLocation")
        statement.actions.append("s3:GetObject")

        return statement

    @staticmethod
    def dynamodb_read_policy_statement(
        table_name: str, indexes: List[str] | None = None
    ) -> iam.PolicyStatement:
        # add the table resource
        resources = [f"arn:aws:dynamodb:*:*:table/{table_name}"]

        if indexes:
            # add indexes; these are required for searching by an index
            for index in indexes:
                i = f"arn:aws:dynamodb:*:*:table/{table_name}/index/{index}"
                resources.append(i)

        statement = iam.PolicyStatement(
            actions=[
                "dynamodb:BatchGetItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
            ],
            resources=resources,
            effect=iam.Effect.ALLOW,
        )
        return statement

    @staticmethod
    def dynamodb_read_write_policy_statement(
        table_name: str, indexes: List[str] | None = None
    ) -> iam.PolicyStatement:
        # add the table resource

        statement = PolicyStatements.dynamodb_read_policy_statement(
            table_name=table_name, indexes=indexes
        )

        statement.actions.append("dynamodb:BatchWriteItem")
        statement.actions.append("dynamodb:PutItem")
        statement.actions.append("dynamodb:UpdateItem")
        return statement

    @staticmethod
    def cognito_user_pool_policy_statement(
        cognito_user_pool_arn: str,
    ) -> iam.PolicyStatement:
        # add the table resource

        statement = iam.PolicyStatement(
            actions=["cognito-idp:*"],
            resources=[
                f"{cognito_user_pool_arn}/*",
            ],
            effect=iam.Effect.ALLOW,
        )
        return statement

    @staticmethod
    def cognito_user_pool_admin_policy_statement(
        cognito_user_pool_arn: str,
    ) -> iam.PolicyStatement:
        # add the table resource

        statement = iam.PolicyStatement(
            actions=["cognito-idp:*"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        return statement
