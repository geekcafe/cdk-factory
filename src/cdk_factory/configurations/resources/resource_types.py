"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from enum import Enum
from typing import Any, Dict, List


class ResourceTypes(Enum):
    """Common Resource Types"""

    S3_BUCKET = 1
    LAMBDA_FUNCTION = 2
    API_GATEWAY = 3
    DYNAMO_DB = 3
    LAMBDA_LAYER = 4
    ECR_REPOSITORY = 5
    CLOUD_WATCH_LOGS = 6
    SQS = 7
    PARAMETER_STORE = 8
    IAM_ROLE = 9


ResourceMap: List[Dict[str, Any]] = [
    {
        "type": ResourceTypes.S3_BUCKET,
        "resource": "s3.Bucket",
        "package": "aws_cdk.aws_s3",
        "name": "S3 Bucket",
        "max_length": 63,
        "invalid_chars": " .",
    },
    {
        "type": ResourceTypes.LAMBDA_FUNCTION,
        "resource": "lambda.Function",
        "package": "aws_cdk.aws_lambda",
        "name": "Lambda Function",
        "max_length": 64,
    },
    {
        "type": ResourceTypes.API_GATEWAY,
        "resource": "apigw.RestApi",
        "package": "aws_cdk.aws_apigateway",
        "name": "API Gateway",
    },
    {
        "type": ResourceTypes.DYNAMO_DB,
        "resource": "dynamodb.Table",
        "package": "aws_cdk.aws_dynamodb",
        "name": "DynamoDB Table",
    },
    {
        "type": ResourceTypes.LAMBDA_LAYER,
        "resource": "lambda.LayerVersion",
        "package": "aws_cdk.aws_lambda",
        "name": "Lambda Layer",
        "max_length": 64,
    },
    {
        "type": ResourceTypes.ECR_REPOSITORY,
        "resource": "ecr.Repository",
        "package": "aws_cdk.aws_ecr",
        "name": "ECR Repository",
    },
    {
        "type": ResourceTypes.CLOUD_WATCH_LOGS,
        "resource": "logs.LogGroup",
        "package": "aws_cdk.aws_logs",
        "name": "Cloud Watch Logs",
    },
    {
        "type": ResourceTypes.SQS,
        "resource": "sqs.Queue",
        "package": "aws_cdk.aws_sqs",
        "name": "SQS Queue",
        "max_length": 80,
    },
    {
        "type": ResourceTypes.PARAMETER_STORE,
        "resource": "ssm.StringParameter",
        "package": "aws_cdk.aws_ssm",
        "name": "Parameter Store",
        "max_length": 2024,
    },
    {
        "type": ResourceTypes.IAM_ROLE,
        "resource": "iam.Role",
        "package": "aws_cdk.aws_iam",
        "name": "IAM Role",
        "max_length": 64,
    },
]
