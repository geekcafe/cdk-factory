"""
Geek Cafe Pipeline
"""

import os
from typing import List, Dict, Any

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
from cdk_factory.configurations.pipeline_stage import PipelineStageConfig
from cdk_factory.interfaces.istack import IStack

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
        add_env_context: bool = True,
        **kwargs,
    ):

        self.cdk_config = cdk_config
        self.workload: WorkloadConfig = workload
        # use the devops account to run the pipeline
        devops_account = self.workload.devops.account
        devops_region = self.workload.devops.region
        self.outdir: str | None = outdir
        self.kwargs = kwargs
        self.add_env_context = add_env_context

        if not devops_account:
            raise ValueError("DevOps Account is required")
        if not devops_region:
            raise ValueError("DevOps Regions is required")

        devops_environment: cdk.Environment = cdk.Environment(
            account=f"{devops_account}", region=f"{devops_region}"
        )
        # pass it up the chain
        # check if kwargs for "env" for the pipeline for the devops
        # this allows for cross account deployments
        kwargs["env"] = devops_environment

        super().__init__(scope, id, **kwargs)

        self.pipeline: PipelineConfig = PipelineConfig(
            pipeline=deployment.pipeline, workload=deployment.workload
        )

        # get the pipeline infrastructure
        self._aws_code_pipeline: pipelines.CodePipeline | None = None

        self.roles = PipelineRoles(self, self.pipeline)

        self.deployment_waves: Dict[str, pipelines.Wave] = {}

    @property
    def aws_code_pipeline(self) -> pipelines.CodePipeline:
        """AWS Code Pipeline"""
        if not self._aws_code_pipeline:
            self._aws_code_pipeline = self._pipeline()

        return self._aws_code_pipeline

    def build(self) -> int:
        """Build the stack"""

        if not self.pipeline.enabled:
            print(f"🚨 Pipeline is disabled for {self.pipeline.name}")
            return 0

        # only get deployments that are of mode "pipeline"
        pipeline_deployments = [
            d for d in self.pipeline.deployments if d.mode == "pipeline"
        ]

        for deployment in pipeline_deployments:
            # stacks can be added to a deployment wave
            if deployment.enabled:

                self._setup_deployment_stages(deployment=deployment)
            else:
                print(
                    f"\t🚨 Deployment for Environment: {deployment.environment} "
                    f"is disabled."
                )
        if len(pipeline_deployments) == 0:
            print(f"\t⛔️ No Pipeline Deployments configured for {self.workload.name}.")

        return len(pipeline_deployments)

    def _pipeline(
        self,
    ) -> pipelines.CodePipeline:
        # CodePipeline to automate the deployment process
        pipeline_name = self.pipeline.build_resource_name(self.pipeline.name)

        # add some environment vars
        env_vars = self._get_environment_vars()
        build_environment = codebuild.BuildEnvironment(environment_variables=env_vars)

        codebuild_policy = CodeBuildPolicy()
        role_policy = codebuild_policy.code_build_policies(
            pipeline=self.pipeline,
            code_artifact_access_role=self.roles.code_artifact_access_role,
        )
        # set up our build options and include our cross account policy
        build_options: pipelines.CodeBuildOptions = pipelines.CodeBuildOptions(
            role_policy=role_policy,
            build_environment=build_environment,
        )

        cdk_cli_version = self.workload.devops.cdk_cli_version
        pipeline_version = self.workload.devops.pipeline_version
        pipeline_type = PipelineType.V2
        if str(pipeline_version).lower() == "v1":
            pipeline_type = PipelineType.V1
        # create the root pipeline
        code_pipeline = pipelines.CodePipeline(
            scope=self,
            id=f"{pipeline_name}",
            pipeline_name=f"{pipeline_name}",
            synth=self._get_synth_shell_step(),
            # set up the role you want the pipeline to use
            role=self.roles.code_pipeline_service_role,
            # make sure this is set or you'll get errors, we're doing cross account deployments
            cross_account_keys=True,
            code_build_defaults=build_options,
            # TODO: make this configurable
            pipeline_type=pipeline_type,
            cli_version=cdk_cli_version,
        )

        return code_pipeline

    def _get_environment_vars(self) -> dict:

        branch = self.pipeline.branch

        temp: dict = self.cdk_config.environment_vars
        environment_variables = {}
        for key, value in temp.items():
            environment_variables[key] = codebuild.BuildEnvironmentVariable(value=value)

        environment_variables["GIT_BRANCH_NAME"] = codebuild.BuildEnvironmentVariable(
            value=branch
        )

        cdk_config_path = self.cdk_config.get_config_path_environment_setting()
        if cdk_config_path:

            config_path = cdk_config_path
            if config_path:
                environment_variables["CDK_CONFIG_PATH"] = (
                    codebuild.BuildEnvironmentVariable(value=config_path)
                )

        return environment_variables

    def _setup_deployment_stages(self, deployment: DeploymentConfig, **kwargs):

        if not deployment.enabled:
            return

        print("👉 Loading all stages of the deployment")

        # add the stages to a pipeline
        for stage in self.pipeline.stages:
            print(f"\t 👉 Prepping stage: {stage.name}")
            if not stage.enabled:
                print(f"\t\t ⚠️ Stage {stage.name} is disabled - skipping.")
                continue
            # create the stage
            pipeline_stage = PipelineStage(self, stage.name, **kwargs)

            self.__setup_stacks(
                stage_config=stage, pipeline_stage=pipeline_stage, deployment=deployment
            )
            # add the stacks to a wave or a regular
            pre_steps = self._get_pre_steps(stage)
            post_steps = self._get_post_steps(stage)
            wave_name = stage.wave_name

            # if we don't have any stacks we'll need to use the wave
            if len(stage.stacks) == 0:
                wave_name = stage.name

            if wave_name:
                print(f"\t 👉 Adding stage {stage.name} to 🌊 {wave_name}")
                # waves can run multiple stages in parallel
                wave = self._get_wave(wave_name)

                if len(stage.stacks) > 0:
                    # only add the stage if we have at least one stack
                    wave.add_stage(pipeline_stage)

                for pre_step in pre_steps:
                    wave.add_pre(pre_step)

                for post_step in post_steps:
                    wave.add_post(post_step)
            else:
                # regular stages are run sequentially
                print(f"\t 👉 Adding stage {stage.name} to pipeline")
                self.aws_code_pipeline.add_stage(
                    stage=pipeline_stage, pre=pre_steps, post=post_steps
                )

    def _get_pre_steps(
        self, stage_config: PipelineStageConfig
    ) -> List[pipelines.ShellStep]:
        return self._get_steps("pre_steps", stage_config)

    def _get_post_steps(
        self, stage_config: PipelineStageConfig
    ) -> List[pipelines.ShellStep]:
        return self._get_steps("post_steps", stage_config)

    def _get_steps(self, key: str, stage_config: PipelineStageConfig):
        """
        Gets the build steps from the config.json
        """
        shell_steps: List[pipelines.ShellStep] = []

        for build in stage_config.builds:
            if str(build.get("enabled", "true")).lower() == "true":
                steps = build.get(key, [])
                step: Dict[str, Any]
                for step in steps:
                    step_id = step.get("id") or step.get("name")
                    commands = step.get("commands", [])
                    shell_step = pipelines.ShellStep(
                        id=step_id,
                        commands=commands,
                    )
                    shell_steps.append(shell_step)

        return shell_steps

    def __setup_stacks(
        self,
        stage_config: PipelineStageConfig,
        pipeline_stage: PipelineStage,
        deployment: DeploymentConfig,
    ):
        stack_config: StackConfig
        factory: StackFactory = StackFactory()
        # add the stacks to the stage_config
        cf_stacks: List[IStack] = []
        for stack_config in stage_config.stacks:
            if stack_config.enabled:
                print(
                    f"\t\t 👉 Adding stack_config: {stack_config.name} to Stage: {stage_config.name}"
                )
                kwargs = {}
                if stack_config.kwargs:
                    kwargs = stack_config.kwargs
                else:
                    kwargs["stack_name"] = stack_config.name

                cf_stack = factory.load_module(
                    module_name=stack_config.module,
                    scope=pipeline_stage,
                    id=stack_config.name,
                    deployment=deployment,
                    add_env_context=self.add_env_context,
                    **kwargs,
                )
                cf_stack.build(
                    stack_config=stack_config,
                    deployment=deployment,
                    workload=self.workload,
                )
                stack = {
                    "stack": cf_stack,
                    "stack_config": stack_config,
                    "stack_name": stack_config.name,
                }
                cf_stacks.append(stack)
            else:
                print(
                    f"\t\t ⚠️ Stack {stack_config.name} is disabled in stage: {stage_config.name}"
                )

        if len(cf_stacks) == 0:
            print(f"\t\t ⚠️ No stacks added to stage: {stage_config.name}")
            print(f"\t\t ⚠️ Internal Stack Count: {len(stage_config.stacks)}")

        # add dependencies
        for cf_stack in cf_stacks:
            if cf_stack["stack_config"].dependencies:
                for dependency in cf_stack["stack_config"].dependencies:
                    # get the stack from the cf_stacks list
                    for stack in cf_stacks:
                        if stack["stack_config"].name == dependency:
                            cf_stack["stack"].add_dependency(stack["stack"])
                            break

        return cf_stacks

    def _get_wave(self, wave_name: str) -> pipelines.Wave:

        if wave_name in self.deployment_waves:
            print(f"\t\tRetrieving wave 🌊 {wave_name}")
            return self.deployment_waves[wave_name]
        else:
            print(f"\t\tDefining wave 🌊 {wave_name}")
            wave: pipelines.Wave = self.aws_code_pipeline.add_wave(
                id=wave_name,
            )
            self.deployment_waves[wave_name] = wave
            return wave

    def _get_synth_shell_step(self) -> pipelines.ShellStep:
        if not self.workload.cdk_app_file:
            raise ValueError("CDK app file is not defined")
        cdk_directory = self.workload.cdk_app_file.removesuffix("/app.py")

        build_commands = self._get_build_commands()

        cdk_out_directory = self.workload.output_directory

        build_commands.append(f"echo 👉 cdk_directory: {cdk_directory}")
        build_commands.append(f"echo 👉 cdk_out_directory: {cdk_out_directory}")
        build_commands.append("echo 👉 PWD from synth shell step: ${PWD}")

        shell = pipelines.ShellStep(
            "CDK Synth",
            input=self._get_source_repository(),
            commands=build_commands,
            primary_output_directory=cdk_out_directory,
        )

        return shell

    def _get_build_commands(self) -> List[str]:
        # print("generating building commands")

        loader = CommandLoader(workload=self.workload)
        custom_commands = loader.get("cdk_synth")

        if custom_commands:
            # print("Using custom CDK synth commands from external file")
            return custom_commands
        else:
            raise RuntimeError("Missing custom CDK synth commands from external file")

    def _get_source_repository(self) -> pipelines.CodePipelineSource:
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
            raise RuntimeError("Unknown code repository type.")

        return source_artifact
