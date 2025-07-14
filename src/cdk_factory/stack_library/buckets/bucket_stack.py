"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.s3 import S3BucketConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.s3_buckets.s3_bucket_construct import S3BucketConstruct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("bucket_library_module")
@register_stack("bucket_stack")
class S3BucketStack(IStack):
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

        S3BucketConstruct(
            self,
            id=deployment.build_resource_name(self.bucket_config.name),
            stack_config=stack_config,
            deployment=deployment,
        )
