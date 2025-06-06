"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence, List, cast

from aws_cdk import aws_iam as iam, RemovalPolicy
from aws_cdk import aws_lambda, aws_logs as logs
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.utilities.file_operations import FileOperations
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.configurations.pipeline import PipelineConfig

logger = Logger(__name__)


class LambdaFunctionUtilities:
    """
    Lambda wrapper
    """

    def __init__(self, deployment: Deployment) -> None:
        self.deployment: Deployment = deployment

    def create(
        self,
        scope: Construct,
        id: str,  # pylint: disable=redefined-builtin
        lambda_config: LambdaFunctionConfig,
        *,
        layers: List[aws_lambda.ILayerVersion] | None = None,
        requirements_files: List[str] | None = None,
        environment: Mapping[str, str] | None = None,
        role: iam.Role | None = None,
    ) -> aws_lambda.Function:
        """_summary_

        Args:
            scope (Construct): _description_
            id (str): _description_
            lambda_config (LambdaFunctionConfig): A lambda configuration object
            layers (Sequence[str], optional): List of Lambda Layers. Defaults to None.
            requirements_files (Sequence[str], optional): List of Requirements files. Defaults to None.
            role (iam.Role, optional): The IAM Role for the Lamnda Function. Defaults to None.


        Raises:
            FileNotFoundError: _description_
            FileNotFoundError: _description_
            FileNotFoundError: _description_

        Returns:
            aws_lambda.Function: _description_
        """

        project_root = Path(__file__).parents[3]

        lambda_directory = lambda_config.src
        if not os.path.exists(lambda_directory):
            lambda_directory = os.path.join(project_root, lambda_directory)

        if not os.path.exists(lambda_directory):
            raise FileNotFoundError(
                f"Lambda Build Failure. Failed to find lambda directory {lambda_directory}."
            )
        lambda_relative_directory = lambda_directory.replace(
            str(project_root), ""
        ).removeprefix("/")

        output_dir = os.path.join(
            str(project_root),
            ".lambda_package",
            lambda_relative_directory,
        )

        self.__validate_directories(
            output_dir=output_dir, lambda_directory=lambda_directory
        )

        self.__requirements(
            scope=scope,
            id=id,
            layers=layers,
            include_power_tools_layer=lambda_config.include_power_tools_layer,
            requirements_files=requirements_files,
            dependencies_to_layer=lambda_config.dependencies_to_layer,
            lambda_directory=lambda_directory,
            handler=lambda_config.handler,
            output_dir=output_dir,
        )
        zip_file = FileOperations.zip_directory(
            output_dir, exclude_list=["__pycache__"]
        )

        function_name = None
        description = lambda_config.description
        if not function_name:
            function_name = id
            print(f"👉function name is using the id = {id}")

        if description:
            description = f"{description}"

        description = f"{lambda_config.name} - {description}"

        if description and len(description) > 256:
            length = len(description)
            description = f"{description[:253]}..."
            logger.warning(
                {
                    "function_name": function_name,
                    "path": lambda_directory,
                    "message": (
                        "The description is longer than 256 characters which includes "
                        "the function name as part of the description (automatically added). "
                        "It's been automatically truncated to 253 characters and an elipse (...) "
                        "to indicate more information was present."
                    ),
                    "length": length,
                }
            )

        log_name = f"{function_name or id}-log"

        log_group = logs.LogGroup(
            scope=scope,
            id=f"{id}-log-group",
            # adding a -log to it since they were orginally autocreated
            # log_group_name=f"/aws/lambda/{log_name}",
            # todo: get from config
            retention=logs.RetentionDays.ONE_MONTH,
            # todo: get from config
            removal_policy=RemovalPolicy.RETAIN,
        )

        # let the system create the function name
        # yes, they are ugly names but you less likely to have a deployment conflict
        # setting none to be safe, even though it's commented out below
        # function_name = None
        if lambda_config.auto_name:
            function_name = None

        lambda_function = aws_lambda.Function(
            scope=scope,
            id=id,
            function_name=function_name,
            handler=lambda_config.handler,
            code=aws_lambda.Code.from_asset(zip_file),
            description=description,
            runtime=lambda_config.runtime,
            layers=layers,
            environment=environment,
            role=self.__get_role_without_policy_updates(role),
            insights_version=lambda_config.insights_version,
            architecture=lambda_config.architecture,
            memory_size=lambda_config.memory_size,
            timeout=lambda_config.timeout,
            tracing=lambda_config.tracing,
            log_group=log_group,
        )

        # not sure if we need to do this or if setting the log_group about will take care of it
        log_group.grant_write(lambda_function)

        return lambda_function

    def __get_role_without_policy_updates(
        self, role: iam.Role | None
    ) -> iam.IRole | None:

        if not role:
            return None

        return role.without_policy_updates()

    def create_dependencies_layer(
        self,
        scope: Construct,
        lambda_directory: str,
        function_name: str,
        requirement_files: Sequence[str],
    ) -> aws_lambda.LayerVersion | None:
        """
        Creates a lambda layer for the dependencies
        Args:
            lambda_directory (str): directory where the lambda layer is.  It's expecting a requirements.txt file
            function_name (str): the function name, which is used as part of the lambda layer name

        Returns:
            aws_lambda.LayerVersion: The Lambda Layer
        """

        if not requirement_files:
            return None

        for file in requirement_files:
            if not os.path.exists(file):
                raise FileNotFoundError(
                    f"Lambda Layer Build Failrure. Failed to find requirements file {file}."
                )
        project_root = Path(__file__).parents[3]
        lambda_relative_directory = lambda_directory.replace(
            str(project_root), ""
        ).removeprefix("/")

        output_dir = os.path.join(
            str(project_root), ".lambda_dependencies", lambda_relative_directory
        )

        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Install requirements for layer in the output_dir
        if not os.environ.get("SKIP_PIP"):
            # Note: Pip will create the output dir if it does not exist
            for file in requirement_files:
                pipelineConfig: PipelineConfig = PipelineConfig(
                    self.deployment.pipeline, self.deployment.workload
                )
                logins = pipelineConfig.code_artifact_logins()
                for login in logins:
                    commands = login.split()
                    subprocess.check_call(commands)
                commands = f"pip install -r {file} -t {output_dir}/python".split()
                subprocess.check_call(commands)

        # make sure we have some files in the output dir
        if os.path.exists(f"{output_dir}/python"):
            files = os.listdir(output_dir)
            if len(files) > 1:  # account for the /python directory
                print(f"creating lambda layer for: {function_name}-dependencies")
                return aws_lambda.LayerVersion(
                    scope=scope,
                    id=f"{function_name}-dependencies",
                    code=aws_lambda.Code.from_asset(output_dir),
                )
            else:
                print(
                    f"skipping lambda layer for: {function_name}-dependencies.  No output for the requirements file."
                )
        return None

    def __validate_directories(self, output_dir: str, lambda_directory: str) -> None:
        print(f"output dir: {output_dir}")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        if not os.path.exists(output_dir):
            print(f"making output dir: {output_dir}")
            os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"directory not found: {output_dir}")

        if not os.path.exists(lambda_directory):
            raise FileNotFoundError(f"directory not found: {lambda_directory}")

        shutil.copytree(lambda_directory, output_dir, dirs_exist_ok=True)

    def __requirements(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        layers: List[aws_lambda.ILayerVersion] | None,
        include_power_tools_layer: bool,
        requirements_files: List[str] | None,
        dependencies_to_layer: bool,
        lambda_directory: str,
        handler: str,
        output_dir: str,
    ):
        logger.info("checking requirements")
        if include_power_tools_layer:
            if not layers:
                layers = []

            logger.info("adding power tools")
            # arn = self.deployment.workload.devops.lambda_layers.power_tools_arn
            # TODO: add to configs
            arn = f"arn:aws:lambda:{self.deployment.region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:62"

            if arn:
                arn = arn.replace("us-east-1", self.deployment.region)
                if "{aws_region}" in arn:
                    arn = arn.replace("{aws_region}", self.deployment.region)
                deployment_resource_name = self.deployment.build_resource_name(
                    "power-tools-Layer"
                )
                layer_id = f"{id}-{deployment_resource_name}"

                layers.append(
                    aws_lambda.LayerVersion.from_layer_version_arn(
                        scope=scope,
                        id=layer_id,
                        layer_version_arn=arn,
                    )
                )

        if not requirements_files:
            # look for a requirements.txt file
            req_file = os.path.join(lambda_directory, "requirements.txt")
            if os.path.exists(req_file):
                requirements_files = [req_file]

        # dependcies as layers or directly added
        if (
            requirements_files
            and dependencies_to_layer
            and (not layers or len(layers) < 5)
        ):
            logger.info("adding requirements as a lambda layer")
            dependency_layer = self.create_dependencies_layer(
                scope=scope,
                lambda_directory=lambda_directory,
                function_name=handler,
                requirement_files=requirements_files,
            )
            if not layers:
                layers = []
            if dependency_layer:
                layers.append(dependency_layer)
        elif requirements_files:
            logger.info("installing requirements directly into the lambda package area")
            for requirment in requirements_files:
                if os.path.exists(requirment):
                    pipelineConfig: PipelineConfig = PipelineConfig(
                        self.deployment.pipeline, self.deployment.workload
                    )
                    logins = pipelineConfig.code_artifact_logins()
                    for login in logins:
                        commands = login.split()
                        subprocess.check_call(commands)

                    commands = f"pip install -r {requirment} -t {output_dir}".split()
                    subprocess.check_call(commands)
                else:
                    logger.warning(
                        {
                            "lambda": f"{handler}",
                            "path": lambda_directory,
                            "requirements": requirment,
                            "message": "a requirement file was attached but could not be found.",
                        }
                    )
