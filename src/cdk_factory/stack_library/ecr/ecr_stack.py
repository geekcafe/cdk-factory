"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.ecr import ECRConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.constructs.ecr.ecr_construct import ECRConstruct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(__name__)


@register_stack("ecr_library_module")
@register_stack("ecr_stack")
class ECRStack(IStack, StandardizedSsmMixin):
    """
    A CloudFormation Stack for an ECR

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

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the stack"""

        self.stack_config = stack_config
        self.deployment = deployment

        constructs = []
        repos = stack_config.dictionary.get("resources", [])
        repo: dict
        for repo in repos:
            config = ECRConfig(config=repo, deployment=deployment)
            # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
            # Repository recreation would cause Docker image loss, so construct ID must be stable
            repo_name = repo.get("name", None)
            if not repo_name:
                # Match test expectation exactly
                raise ValueError("Resource name is required")
            construct_id = f"{deployment.workload_name}-{deployment.environment}-ecr-{repo_name}"

            construct = ECRConstruct(
                scope=self,
                id=construct_id,
                deployment=deployment,
                repo=config,
            )

            constructs.append(construct)
