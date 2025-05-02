"""
Geek Cafe Pipeline
"""

import os
from typing import List

import aws_cdk as cdk
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import pipelines
from aws_cdk.aws_codepipeline import PipelineType
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.commands.command_loader import CommandLoader
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.pipeline.security.policies import CodeBuildPolicy
from cdk_factory.pipeline.security.roles import PipelineRoles
from cdk_factory.pipeline.stage import PipelineStage
from cdk_factory.stack.stack_factory import StackFactory
from cdk_factory.workload.workload_factory import WorkloadConfig

from cdk_factory.configurations.cdk_config import CdkConfig
from cdk_factory.utilities.configuration_loader import ConfigurationLoader

logger = Logger()


class PipelineFactoryStack(cdk.Stack):
    """
    Pipeline Stacks wrap up your application for a CI/CD pipeline Stack
    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=W0622
        *,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
        cdk_config: CdkConfig,
        outdir: str | None = None,
        **kwargs,
    ):

        self.cdk_config = cdk_config
        self.workload: WorkloadConfig = workload
        # use the devops account to run the pipeline
        devop_account = self.workload.devops.account
        devop_region = self.workload.devops.region
        self.outdir: str | None = outdir
        self.kwargs = kwargs
        assert devop_account is not None
        assert devop_region is not None

        devops_environment: cdk.Environment = cdk.Environment(
            account=f"{devop_account}", region=f"{devop_region}"
        )
        # pass it up the chain
        super().__init__(scope, id, env=devops_environment, **kwargs)

        self.pipeline: PipelineConfig = PipelineConfig(
            pipeline=deployment.pipeline, workload=deployment.workload
        )

        # get the pipeline infrastructure
        self.__aws_code_pipeline: pipelines.CodePipeline | None = None

        self.roles = PipelineRoles(self, self.pipeline)

        self.deployment_waves: List[pipelines.Wave] = []

        self.__build_wave_list()

    def __build_wave_list(self):
        """Build the wave list"""

        for deployment in self.pipeline.deployments:
            if deployment.wave_name is not None:
                wave: pipelines.Wave = self.aws_code_pipeline.add_wave(
                    id=deployment.wave_name,
                )
                self.deployment_waves.append(wave)

    @property
    def aws_code_pipeline(self) -> pipelines.CodePipeline:
        """AWS Code Pipeline"""
        if not self.__aws_code_pipeline:
            self.__aws_code_pipeline = self.__pipeline()

        return self.__aws_code_pipeline

    def build(self) -> int:
        """Build the statck"""
        for deployment in self.pipeline.deployments:
            # stacks can be added to a deployment wave
            if deployment.enabled:
                # deploy our stages
                # if deployment.wave_name:
                # set up the waves
                self.__setup_waves(deployment=deployment, **self.kwargs)
                # else:
                # self.__setup_standard_pipeline(deployment=deployment)
            else:
                print(
                    f"\t🚨 Deployment for Environment: {deployment.environment} "
                    f"is disabled."
                )
        if len(self.pipeline.deployments) == 0:
            print(f"\t⛔️ No Deployments configured for {self.workload.name}.")

        return len(self.pipeline.deployments)

    def __pipeline(
        self,
    ) -> pipelines.CodePipeline:
        # CodePipeline to automate the deployment process
        pipeline_name = self.pipeline.build_resource_name("pipeline")
        branch = self.pipeline.branch

        env_vars = self.__get_environment_vars()
        # add some environment vars
        build_environment = codebuild.BuildEnvironment(environment_variables=env_vars)

        codebuild_policy = CodeBuildPolicy()
        role_policy = codebuild_policy.code_build_policies(
            pipeline=self.pipeline,
            code_artifacte_access_role=self.roles.code_artifact_access_role,
        )
        # set up our build options and include our cross account policy
        build_options: pipelines.CodeBuildOptions = pipelines.CodeBuildOptions(
            role_policy=role_policy,
            build_environment=build_environment,
        )

        # create the root pipeline
        code_pipeline = pipelines.CodePipeline(
            scope=self,
            id=f"{pipeline_name}",
            pipeline_name=f"{pipeline_name}",
            synth=self.__get_synth_shell_step(branch=branch),
            # set up the role you want the pipeline to use
            role=self.roles.code_pipeline_service_role,
            # make sure this is set or you'll get errors, we're doing cross account deployments
            cross_account_keys=True,
            code_build_defaults=build_options,
            # TODO: make this configurable
            pipeline_type=PipelineType.V2,
        )

        return code_pipeline

    def __get_environment_vars(self) -> dict:

        branch = self.pipeline.branch

        temp: dict = self.cdk_config.environment_vars
        environment_variables = {}
        for key, value in temp.items():
            environment_variables[key] = codebuild.BuildEnvironmentVariable(value=value)

        environment_variables["GIT_BRANCH_NAME"] = codebuild.BuildEnvironmentVariable(
            value=branch
        )

        if self.cdk_config.config_file_path:

            config_path = self.cdk_config.config_file_path
            if config_path:
                environment_variables["CDK_CONFIG_PATH"] = (
                    codebuild.BuildEnvironmentVariable(value=config_path)
                )

        return environment_variables

    def __setup_waves(self, deployment: DeploymentConfig, **kwargs):
        for deployment in self.pipeline.deployments:
            # stacks can be added to a deployment wave
            if deployment.enabled:
                for stage in self.pipeline.stages:
                    pipeline_stage = PipelineStage(
                        self, f"{deployment.name}-{stage.name}", **kwargs
                    )
                    stack: StackConfig
                    factory: StackFactory = StackFactory()
                    # add the stacks to the stage
                    for stack in stage.stacks:
                        if stack.enabled:
                            print(f"building stack: {stack.name}")
                            module = factory.load_module(
                                module_name=stack.module,
                                scope=pipeline_stage,
                                id=stack.name,
                            )
                            module.build(
                                stack_config=stack,
                                deployment=deployment,
                                workload=self.workload,
                            )

                    if deployment.wave_name:
                        wave = self.__get_wave(deployment.wave_name)
                        wave.add_stage(pipeline_stage)

                # create the waves based on the resources
                print("setting up waves... find all the waves and add stages to waves")

    def __get_wave(self, wave_name: str) -> pipelines.Wave:
        for wave in self.deployment_waves:
            if wave.id == wave_name:
                return wave
        raise RuntimeError(f"Wave {wave_name} not found")

    def __setup_standard_pipeline(self, deployment: DeploymentConfig):
        raise NotImplementedError("This feature is not implemented yet")

    def __get_synth_shell_step(self, branch: str) -> pipelines.ShellStep:
        if not self.workload.cdk_app_file:
            raise ValueError("CDK app file is not defined")
        cdk_directory = self.workload.cdk_app_file.removesuffix("/app.py")

        build_commands = self.__get_build_commands()

        cdk_out_directory = f"{cdk_directory}/cdk.out"

        build_commands.append(f"echo 👉 cdk_directory: {cdk_directory}")
        build_commands.append(f"echo 👉 cdk_out_directory: {cdk_out_directory}")
        build_commands.append("echo 👉 PWD from synth shell step: ${PWD}")

        shell = pipelines.ShellStep(
            "CDK Synth",
            input=self.__get_source_repository(),
            commands=build_commands,
            primary_output_directory=cdk_out_directory,
        )

        # shell = pipelines.CodeBuildStep(
        #     "CDK Synth",
        #     input=self.__get_source_repository(),
        #     partial_build_spec=pipelines.CodeBui
        #     primary_output_directory=cdk_out_directory,
        # )

        return shell

    def __get_build_commands(self) -> List[str]:
        print("generating building commands")

        loader = CommandLoader(workload=self.workload)
        custom_commands = loader.get("cdk_synth")

        if custom_commands:
            print("Using custom CDK synth commands from external file")
            return custom_commands
        else:
            raise RuntimeError("Missing custom CDK synth commands from external file")
        # TODO: add some default commands ?? maybe
        # commands = self.__default_build_commands(
        #     branch, cdk_directory, cdk_out_directory
        # )
        # return commands

    def __get_source_repository(self) -> pipelines.CodePipelineSource:
        repo_name: str = self.workload.devops.code_repository.name
        branch: str = self.pipeline.branch
        repo_id: str = self.pipeline.build_resource_name(repo_name)
        code_repo: codecommit.IRepository
        source_artifact: pipelines.CodePipelineSource

        if self.workload.devops.code_repository.type == "connector_arn":
            code_repository = self.workload.devops.code_repository
            if code_repository.connector_arn:
                source_artifact = pipelines.CodePipelineSource.connection(
                    repo_string=code_repository.name,
                    branch=branch,
                    connection_arn=code_repository.connector_arn,
                    action_name=code_repository.type,
                    code_build_clone_output=True,  # gets us branch and meta data info
                )
            else:
                raise RuntimeError(
                    "Missing Repository connector_arn. "
                    "It's a best practice and therefore "
                    "required to connect your github account to AWS."
                )
        elif self.workload.devops.code_repository.type == "code_commit":
            code_repo = codecommit.Repository.from_repository_name(
                self, f"{repo_id}", repo_name
            )
            # Define the source artifact
            source_artifact = pipelines.CodePipelineSource.code_commit(
                code_repo, branch, code_build_clone_output=True
            )
        else:
            raise RuntimeError("Unknow code repository type.")

        return source_artifact
