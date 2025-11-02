"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Any, Dict, List, Optional
import os

import cdk_nag
from aws_cdk import aws_iam as iam
from constructs import Construct
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)


class ResourceResolver:
    """Flexible resource resolver that can load from environment variables or enhanced SSM parameters"""

    def __init__(
        self,
        scope: Construct,
        deployment: Deployment,
        lambda_config: LambdaFunctionConfig,
    ):
        self.scope = scope
        self.deployment = deployment
        self.lambda_config = lambda_config
        self._ssm_mixin = None

    def _get_ssm_mixin(self):
        """Get or create enhanced SSM parameter mixin"""
        if self._ssm_mixin is None:
            try:
                from cdk_factory.interfaces.standardized_ssm_mixin import (
                    StandardizedSsmMixin,
                )

                self._ssm_mixin = StandardizedSsmMixin()

                # Setup enhanced SSM integration if lambda config has SSM settings
                lambda_dict = getattr(self.lambda_config, "dictionary", {})
                ssm_config = lambda_dict.get("ssm", {})

                if ssm_config.get("enabled", False):
                    self._ssm_mixin.setup_ssm_integration(
                        scope=self.scope,
                        config=lambda_dict,
                        resource_type="lambda",
                        resource_name=self.lambda_config.name,
                    )
            except ImportError:
                # Enhanced SSM not available, will fall back to environment variables
                pass
        return self._ssm_mixin

    def get_table_name(self, table_identifier: str = "APP_TABLE_NAME") -> Optional[str]:
        """
        Get DynamoDB table name from multiple sources with fallback priority:
        1. Enhanced SSM parameter (if configured)
        2. Environment variable
        3. None (will raise error in calling method)
        """
        table_name = None

        # Try enhanced SSM parameter lookup first
        ssm_mixin = self._get_ssm_mixin()
        if ssm_mixin:
            try:
                # Try to auto-import table name from DynamoDB stack
                imported_values = ssm_mixin.auto_import_resources()
                table_name = imported_values.get("table_name")

                if table_name:
                    return table_name

            except Exception:
                # SSM lookup failed, continue to environment variable fallback
                pass

        # Fallback to environment variable
        table_name = os.getenv(table_identifier)

        return table_name

    def get_aws_region(self) -> str:
        """Get AWS region from deployment config or environment"""
        region = self.deployment.region
        if region:
            return region
        return os.getenv("AWS_REGION", "*")

    def get_aws_account(self) -> str:
        """Get AWS account from deployment config or environment"""
        account = self.deployment.account
        if account:
            return account
        # not sure if the * is a good idea here or not
        return os.getenv("AWS_ACCOUNT", "*")


class PolicyDocuments:
    """Reusable Policy Statements"""

    def __init__(
        self,
        scope: Construct,
        role: iam.Role,
        lambda_config: LambdaFunctionConfig,
        deployment: Deployment,
    ) -> None:
        self.scope: Construct = scope
        self.role: iam.Role = role
        self.lambda_config: LambdaFunctionConfig = lambda_config
        self.deployment: Deployment = deployment
        self._resource_resolver = None

    def default_lambda_policy_doc(self) -> iam.Policy:
        """Creates the default policy document"""
        statements: List[iam.PolicyStatement] = []
        # Custom Policy for the Lambda Role
        lambda_exec_policy_statements = iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=["arn:aws:logs:*:*:*"],
            effect=iam.Effect.ALLOW,
        )
        statements.append(lambda_exec_policy_statements)

        lambda_insights_statements = iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        statements.append(lambda_insights_statements)

        lambda_xray_permissions = iam.PolicyStatement(
            sid="XrayPermissions",
            actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        statements.append(lambda_xray_permissions)

        policy = iam.Policy(
            scope=self.scope,
            id=f"{self.deployment.build_resource_name(self.lambda_config.name)}-policy-doc",
            statements=statements,
        )

        cdk_nag.NagSuppressions.add_resource_suppressions(
            construct=policy,
            suppressions=[
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="Not sure how to get rid of these errors",
                    applies_to=[
                        "Resource::arn:aws:logs:*:*:*",  # logging
                        "Resource::*",  # put metric
                    ],
                )
            ],
            apply_to_children=True,
        )

        return policy

    def generate_and_bind_lambda_policy_docs(self) -> None:
        """Generates and binds the necessary policy documents"""
        policy_doc: iam.Policy = self.default_lambda_policy_doc()
        policy_doc.attach_to_role(self.role)

        nag_exclusions = []

        if self.lambda_config.permissions:
            statements = []
            for permission in self.lambda_config.permissions:
                permission_details = self.get_permission_details(permission)
                if permission_details is None:
                    print(f"Permission set for {permission} not found")
                    raise ValueError(
                        f"Permission set for {permission} not found when attempting "
                        "to generate permissions."
                    )
                statement = iam.PolicyStatement(
                    sid=permission_details.get("sid"),
                    actions=permission_details["actions"],
                    resources=permission_details["resources"],
                    # todo: change this to add it dynamically, we may want to deny
                    effect=iam.Effect.ALLOW,
                )

                statements.append(statement)
                if permission_details.get("nag"):
                    nag_exclusions.append(permission_details.get("nag"))

            if len(statements) > 0:
                policy = iam.Policy(
                    self.scope,
                    id=f"{self.deployment.build_resource_name(self.lambda_config.name)}-resources-policy-doc",
                    statements=statements,
                )

                policy.attach_to_role(self.role)

            if len(nag_exclusions) > 0:
                nag: dict | None = None
                for nag in nag_exclusions:
                    if nag is None:
                        continue

                    cdk_nag.NagSuppressions.add_resource_suppressions(
                        construct=policy,
                        suppressions=[
                            cdk_nag.NagPackSuppression(
                                id=nag["id"],
                                reason=nag["reason"],
                                applies_to=nag["resources"],
                            )
                        ],
                        apply_to_children=True,
                    )

        return None

    def _get_resource_resolver(self):
        """Get or create a resource resolver for flexible resource lookup"""
        if self._resource_resolver is None:
            self._resource_resolver = ResourceResolver(
                scope=self.scope,
                deployment=self.deployment,
                lambda_config=self.lambda_config,
            )
        return self._resource_resolver

    def get_permission_details(self, permission: str | dict) -> dict:
        """Returns the details of a specific permission"""

        # TODO: this all needs refactoring for flexibility

        permissions_map = {
            "dynamodb_read": self._get_dynamodb_read_permissions(),
            "dynamodb_write": self._get_dynamodb_write_permissions(),
            "dynamodb_delete": self._get_dynamodb_delete_permissions(),
            # "s3_read_workload": self.__s3_read_permissions(
            #     self.deployment.get_workload_bucket_name()
            # ),
            # "s3_write_workload": self.__s3_write_permissions(
            #     self.deployment.get_workload_bucket_name()
            # ),
            # "s3_delete_workload": self.__s3_delete_permissions(
            #     self.deployment.get_workload_bucket_name()
            # ),
            # "s3_read_upload": self.__s3_read_permissions(
            #     self.deployment.get_upload_bucket_name()
            # ),
            # "s3_write_upload": self.__s3_write_permissions(
            #     self.deployment.get_upload_bucket_name()
            # ),
            "parameter_store_read": self.__get_parameter_store_read_permissions(),
            "cognito_user_pool_read": {
                "name": "Cognito",
                "description": "Cognito User Pool Access",
                "sid": "CognitoUserPoolAccess",
                "actions": ["cognito-idp:ListUserPools"],
                "resources": ["*"],
            },
            "cognito_user_pool_client_read": {
                "name": "Cognito",
                "description": "Cognito User Pool Client Access",
                "sid": "CognitoUserPoolClientAccess",
                "actions": ["cognito-idp:ListUserPoolClients"],
                "resources": ["*"],
            },
            "cognito_user_pool_group_read": {
                "name": "Cognito",
                "description": "Cognito User Pool Group Access",
                "sid": "CognitoUserPoolGroupAccess",
                "actions": ["cognito-idp:ListGroups"],
                "resources": ["*"],
            },
            "cognito_admin": {
                "name": "Cognito",
                "description": "Cognito Admin Access",
                "sid": "CognitoAdminAccess",
                "actions": ["cognito-idp:*"],
                "resources": ["*"],
                "nag": {
                    "id": "AwsSolutions-IAM5",
                    "reason": "This wildcard permission is necessary for our use case with cognito access.",
                    "resources": [
                        "Resource::*",
                        "Action::cognito-idp:*",
                    ],
                },
            },
        }

        permission_details: dict | None = None
        if isinstance(permission, str):
            permission_details = permissions_map.get(permission)
        elif isinstance(permission, dict):
            permission_details = self.get_permission_details_from_dict(permission)

        return permission_details or {}

    def _get_dynamodb_write_permissions(self) -> dict:
        """Get DynamoDB write permissions with flexible resource resolution."""
        resolver = self._get_resource_resolver()

        table_name = resolver.get_table_name()
        aws_region = resolver.get_aws_region()
        aws_account = resolver.get_aws_account()

        if not table_name:
            raise ValueError(
                "DynamoDB table name not found. Please ensure either:\n"
                "1. 'APP_TABLE_NAME' environment variable is set, OR\n"
                "2. Enhanced SSM parameters are configured with DynamoDB table name auto-import\n"
                "This is required for 'dynamodb_write' permission to generate proper PolicyStatement resources."
            )

        table_arn = f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}"
        index_arn = (
            f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}/index/*"
        )

        return {
            "name": "DynamoDB",
            "description": "DynamoDB Write",
            "sid": "DynamoDbWriteAccess",
            "actions": [
                "dynamodb:BatchWriteItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
            ],
            "resources": [table_arn, index_arn],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": (
                    "This wildcard permission is necessary for our use case because of DynamoDB indexes. "
                    "Alternatively, we could define the specific index(es)"
                ),
                "resources": [
                    f"Resource::{table_arn}",
                    f"Resource::{index_arn}",
                ],
            },
        }

    def _get_dynamodb_delete_permissions(self) -> dict:
        """Get DynamoDB delete permissions with flexible resource resolution."""
        resolver = self._get_resource_resolver()

        table_name = resolver.get_table_name()
        aws_region = resolver.get_aws_region()
        aws_account = resolver.get_aws_account()

        if not table_name:
            raise ValueError(
                "DynamoDB table name not found. Please ensure either:\n"
                "1. 'APP_TABLE_NAME' environment variable is set, OR\n"
                "2. Enhanced SSM parameters are configured with DynamoDB table name auto-import\n"
                "This is required for 'dynamodb_delete' permission to generate proper PolicyStatement resources."
            )

        table_arn = f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}"
        index_arn = (
            f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}/index/*"
        )

        return {
            "name": "DynamoDB",
            "description": "DynamoDB Delete",
            "sid": "DynamoDbDeleteAccess",
            "actions": [
                "dynamodb:DeleteItem",
            ],
            "resources": [table_arn, index_arn],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": "This wildcard permission is necessary for our use case because of DynamoDB indexes.",
                "resources": [
                    f"Resource::{table_arn}",
                    f"Resource::{index_arn}",
                ],
            },
        }

    def _get_dynamodb_read_permissions(self) -> dict:
        """Get DynamoDB read permissions with flexible resource resolution."""
        resolver = self._get_resource_resolver()

        table_name = resolver.get_table_name()
        aws_region = resolver.get_aws_region()
        aws_account = resolver.get_aws_account()

        if not table_name:
            raise ValueError(
                "DynamoDB table name not found. Please ensure either:\n"
                "1. 'APP_TABLE_NAME' environment variable is set, OR\n"
                "2. Enhanced SSM parameters are configured with DynamoDB table name auto-import\n"
                "This is required for 'dynamodb_read' permission to generate proper PolicyStatement resources."
            )

        # Construct proper resource ARNs
        table_arn = f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}"
        index_arn = (
            f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/{table_name}/index/*"
        )

        return {
            "name": "DynamoDB",
            "description": "DynamoDB Read",
            "sid": "DynamoDbReadAccess",
            "actions": [
                "dynamodb:GetItem",
                "dynamodb:Scan",
                "dynamodb:Query",
                "dynamodb:BatchGetItem",
            ],
            "resources": [table_arn, index_arn],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": (
                    "This wildcard permission is necessary for our use case because of DynamoDB indexes. "
                    "Alternatively, we could define the specific index(es)"
                ),
                "resources": [
                    f"Resource::{table_arn}",
                    f"Resource::{index_arn}",
                ],
            },
        }

    def __s3_read_permissions(
        self, bucket_name: str, sid: str | None = None
    ) -> Dict[str, Any]:
        policy = {
            "name": "S3",
            "description": "S3 Read",
            "actions": ["s3:GetObject"],
            "resources": [
                f"arn:aws:s3:::{bucket_name}",
                f"arn:aws:s3:::{bucket_name}/*",
            ],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": "This wildcard permission is necessary for our use case with bucket access.",
                "resources": [
                    f"Resource::arn:aws:s3:::{bucket_name}",
                    f"Resource::arn:aws:s3:::{bucket_name}/*",
                ],
            },
        }

        if sid:
            policy["sid"] = sid

        return policy

    def __s3_delete_permissions(
        self, bucket_name: str, sid: str | None = None
    ) -> Dict[str, Any]:
        policy = {
            "name": "S3",
            "description": "S3 Delete. Restricting to just .png files",
            "actions": [
                "s3:DeleteObject",
                "s3:GetBucketLocation",
            ],
            "resources": [
                f"arn:aws:s3:::{bucket_name}/*.png",
            ],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": "This wildcard permission is necessary for our use case with bucket access.",
                "resources": [
                    f"Resource::arn:aws:s3:::{bucket_name}/*.png",
                ],
            },
        }

        if sid:
            policy["sid"] = sid

        return policy

    def __s3_write_permissions(
        self, bucket_name: str, sid: str | None = None
    ) -> Dict[str, Any]:
        policy = {
            "name": "S3",
            "description": "S3 Write",
            "actions": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:PutObjectTagging",
                "s3:ListBucketMultipartUploads",
                "s3:AbortMultipartUpload",
                "s3:ListMultipartUploadParts",
                "s3:GetBucketLocation",
            ],
            "resources": [
                f"arn:aws:s3:::{bucket_name}",
                f"arn:aws:s3:::{bucket_name}/*",
            ],
            "nag": {
                "id": "AwsSolutions-IAM5",
                "reason": "This wildcard permission is necessary for our use case with bucket access.",
                "resources": [
                    f"Resource::arn:aws:s3:::{bucket_name}",
                    f"Resource::arn:aws:s3:::{bucket_name}/*",
                ],
            },
        }

        if sid:
            policy["sid"] = sid

        return policy

    def __get_parameter_store_read_permissions(self) -> dict:
        """Returns the necessary permissions for the parameter store"""

        permission: Dict[str, Any] = {
            "name": "ssm",
            "description": "Parameter Store Read",
            "sid": "ParameterStoreRead",
            "actions": [
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath",
                "ssm:DescribeParameters",
            ],
            "resources": [],
        }

        return permission

    def get_permission_details_from_dict(self, permission: dict) -> dict:
        """Returns the details of a specific permission"""

        resources = permission.get("resources", [])
        actions = permission.get("actions", [])

        if "lambda:InvokeFunction" in actions:
            tmp = []
            for resource in resources:
                function_name = self.deployment.build_resource_name(
                    resource, ResourceTypes.LAMBDA_FUNCTION
                )
                tmp.append(
                    f"arn:aws:lambda:{self.deployment.region}:{self.deployment.account}:function:{function_name}"
                )

            resources = tmp

        permission_details = {
            "name": permission.get("name"),
            "description": permission.get("description"),
            "sid": permission.get("sid"),
            "actions": actions,
            "resources": resources,
            "nag": permission.get("nag"),
        }

        return permission_details
