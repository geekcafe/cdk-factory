"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.constructs.lambdas.lambda_function_role_construct import (
    LambdaRoleConstruct,
)

from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.configurations.workload import WorkloadConfig as Workload
from cdk_factory.utilities.lambda_function_utilities import LambdaFunctionUtilities
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.utilities.environment_services import EnvironmentServices

logger = Logger(__name__)


class LambdaConstruct(Construct):
    """Lambda Construct"""

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=W0622
        *,
        deployment: Deployment,
        workload: Workload,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.scope = scope
        self.deployment = deployment
        self.workload = workload

    def create_function(
        self,
        id: str,  # pylint: disable=W0622
        lambda_config: LambdaFunctionConfig,
        *,
        role: iam.Role | None = None,
        layers: List[aws_lambda.ILayerVersion] | None = None,
        environment: dict | None = None,
    ) -> aws_lambda.Function:
        # do a layers check
        layers = self.__check_layers(
            unique_id=id, layers=layers, lambda_config=lambda_config
        )
        environment_vars = EnvironmentServices.load_environment_variables(
            environment=environment,
            deployment=self.deployment,
            lambda_config=lambda_config,
            scope=self,
        )
        # create the standard role
        role = self.__check_role(role=role, unique_id=id, lambda_config=lambda_config)

        utilities = LambdaFunctionUtilities(deployment=self.deployment, workload=self.workload)

        function = utilities.create(
            scope=self.scope,
            id=id,
            lambda_config=lambda_config,
            environment=environment_vars,
            layers=layers,
            role=role,
        )

        return function

    def __check_role(
        self,
        role: iam.Role | None,
        unique_id: str,
        lambda_config: LambdaFunctionConfig,
    ) -> iam.Role:
        if not role:
            role = LambdaRoleConstruct.Role(
                scope=self,
                unique_id=unique_id,
                deployment=self.deployment,
                lambda_config=lambda_config,
            )

        return role

    def __check_layers(
        self,
        unique_id: str,
        layers: List[aws_lambda.ILayerVersion] | None,
        lambda_config: LambdaFunctionConfig,
    ) -> List[aws_lambda.ILayerVersion] | None:
        """
        Check to see if we have our standard / common layer in the list
        If they are needed and not in the list, we'll add them
        Args:
            unique_id (str): A unique is for the layer construct to avoid conflicts
            layers (Sequence[aws_lambda.ILayerVersion] | None): a list of layers
            add_common_layer (bool): adds the common layer if needed

        Returns:
            Sequence[aws_lambda.ILayerVersion] | None: _description_
        """

        if not layers:
            layers = []

        for layer in lambda_config.layers:
            name = layer.get("name")
            arn = layer.get("arn")
            if not name or not arn:
                logger.warning(
                    f"Layer is missing name or arn. skipping name: {name}, arn: {arn}"
                )
                continue
            layers.append(
                aws_lambda.LayerVersion.from_layer_version_arn(
                    scope=self.scope,
                    id=f"{unique_id}-{name}",
                    layer_version_arn=arn,
                )
            )

        if len(layers) > 1:
            logger.info("Multiple layers, removing duplicates")
            layers = list(set(layers))

        if len(layers) > 5:
            raise ValueError(
                f"Too many layers are added to this lambda function {unique_id}. "
                f"The max is 5 and we found {len(layers)}"
            )

        return layers
