"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_lambda_powertools import Logger
from constructs import Construct
from aws_cdk import aws_iam as iam

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.s3_buckets.s3_bucket_construct import S3BucketConstruct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin

logger = Logger(__name__)


@register_stack("bucket_library_module")
@register_stack("bucket_stack")
class S3BucketStack(IStack, StandardizedSsmMixin):
    """
    A CloudFormation Stack for an S3 Bucket

    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.scope = scope
        self.id = id
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.bucket_config: S3BucketConfig | None = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the stack"""

        self.stack_config = stack_config
        self.deployment = deployment

        self.bucket_config = S3BucketConfig(stack_config.dictionary.get("bucket", {}))

        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        # Bucket recreation would cause data loss, so construct ID must be stable
        stable_bucket_id = f"{deployment.workload_name}-{deployment.environment}-bucket"

        self.bucket_stack: S3BucketConstruct = S3BucketConstruct(
            self,
            id=stable_bucket_id,
            stack_config=stack_config,
            deployment=deployment,
        )
        self.bucket = self.bucket_stack.bucket

        self._apply_bucket_policy()
        self._exports()

    def _apply_bucket_policy(self) -> None:
        """Apply bucket policy statements if configured"""
        bucket_policy_config = self.bucket_config.dictionary.get("bucket_policy", {})
        statements = bucket_policy_config.get("statements", [])
        
        if not statements:
            return
        
        for statement in statements:
            # Build principals
            principals_config = statement.get("principals", {})
            principals = []
            
            if "service" in principals_config:
                service = principals_config["service"]
                if isinstance(service, list):
                    principals.extend([iam.ServicePrincipal(s) for s in service])
                else:
                    principals.append(iam.ServicePrincipal(service))
            
            if "aws" in principals_config:
                aws_principals = principals_config["aws"]
                if isinstance(aws_principals, list):
                    principals.extend([iam.ArnPrincipal(p) for p in aws_principals])
                else:
                    principals.append(iam.ArnPrincipal(aws_principals))
            
            # Build conditions
            conditions = {}
            for condition in statement.get("conditions", []):
                test = condition.get("test")
                variable = condition.get("variable")
                values = condition.get("values")
                
                if test and variable and values:
                    # Resolve SSM values in condition values
                    resolved_values = []
                    for value in values:
                        resolved_value = self.resolve_ssm_value(self, value, value)
                        resolved_values.append(resolved_value)
                    
                    conditions[test] = {variable: resolved_values}
            
            # Build policy statement
            policy_statement = iam.PolicyStatement(
                sid=statement.get("sid"),
                effect=iam.Effect.ALLOW if statement.get("effect", "Allow") == "Allow" else iam.Effect.DENY,
                principals=principals if principals else None,
                actions=statement.get("actions", []),
                resources=statement.get("resources", []),
                conditions=conditions if conditions else None,
            )
            
            self.bucket.add_to_resource_policy(policy_statement)
            logger.info(f"Added bucket policy statement: {statement.get('sid')}")

    def _exports(self) -> None:
        """Exports the bucket name and ARN to SSM"""
        ssm = self.bucket_config.ssm
        exports = ssm.get("exports", {})
        if not ssm:
            return
        auto_export = ssm.get("auto_export", False)

        known_key_values = {
            "bucket_name": self.bucket.bucket_name,
            "bucket_arn": self.bucket.bucket_arn,
        }

        if auto_export:
            for export_key, export_parameter in known_key_values.items():
                value = known_key_values[export_key]
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.id}-{export_key}",
                    value=value,
                    parameter_name=export_parameter,
                    description=f"Bucket {export_key}",
                )
        else:
            # user specified exports
            for export_key, export_parameter in exports.items():
                if export_key not in known_key_values:
                    # raise error if they specify an unknown export key
                    raise ValueError(f"Unknown export key: {export_key}")
                value = known_key_values[export_key]
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.id}-{export_key}",
                    value=value,
                    parameter_name=export_parameter,
                    description=f"Bucket {export_key}",
                )
