"""
Geek Cafe Pipeline
"""

import os
from pathlib import Path
from typing import List, Dict, Any
import yaml

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
from cdk_factory.pipeline.path_utils import convert_app_file_to_relative_directory

logger = Logger()


class PipelineFactoryStack(IStack):
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

        # Cache created sources keyed by repo+branch to avoid duplicate node IDs
        self._source_cache: Dict[str, pipelines.CodePipelineSource] = {}

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
        if not pipeline_deployments:
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
            # create the stage using stable_id to prevent logical ID changes when stage name changes
            pipeline_stage = PipelineStage(self, stage.stable_id, **kwargs)

            self.__setup_stacks(
                stage_config=stage, pipeline_stage=pipeline_stage, deployment=deployment
            )
            # add the stacks to a wave or a regular
            pre_steps = self._get_pre_steps(stage, deployment)
            post_steps = self._get_post_steps(stage, deployment)
            wave_name = stage.wave_name

            # if we don't have any stacks we'll need to use the wave
            if not stage.stacks:
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
        self, stage_config: PipelineStageConfig, deployment: DeploymentConfig
    ) -> List[pipelines.ShellStep]:
        return self._get_steps("pre_steps", stage_config, deployment)

    def _get_post_steps(
        self, stage_config: PipelineStageConfig, deployment: DeploymentConfig
    ) -> List[pipelines.ShellStep]:
        return self._get_steps("post_steps", stage_config, deployment)

    def _get_steps(self, key: str, stage_config: PipelineStageConfig, deployment: DeploymentConfig):
        """
        Gets the build steps from the config.json.

        Commands can be:
        - A list of strings (each string is a separate command)
        - A single multi-line string (treated as a single script block)

        This allows support for complex shell constructs like if blocks, loops, etc.
        
        For builds with source/buildspec/environment, creates CodeBuildStep instead of ShellStep.
        """
        shell_steps: List[pipelines.Step] = []

        # Only process builds if this stage explicitly defines them
        if not stage_config.dictionary.get("builds"):
            return shell_steps

        for build in stage_config.builds:
            if str(build.get("enabled", "true")).lower() == "true":
                # Check if this is a CodeBuild step (has source, buildspec, or environment)
                if build.get("source") or build.get("buildspec") or build.get("environment"):
                    # Create CodeBuildStep for external builds
                    codebuild_step = self._create_codebuild_step(build, key, deployment, stage_config.name)
                    if codebuild_step:
                        shell_steps.append(codebuild_step)
                else:
                    # Create traditional ShellStep for inline commands
                    steps = build.get(key, [])
                    step: Dict[str, Any]
                    for step in steps:
                        step_id = step.get("id") or step.get("name")
                        commands = step.get("commands", [])

                        # Normalize commands to a list
                        # If commands is a single string, wrap it in a list
                        if isinstance(commands, str):
                            commands = [commands]

                        shell_step = pipelines.ShellStep(
                            id=step_id,
                            commands=commands,
                        )
                        shell_steps.append(shell_step)

        return shell_steps
    
    def _create_codebuild_step(self, build: Dict[str, Any], key: str, deployment: DeploymentConfig, stage_name: str) -> pipelines.CodeBuildStep:
        """
        Creates a CodeBuildStep for builds that specify source, buildspec, or environment.
        
        Supports:
        - External GitHub repositories (public and private)
        - Custom buildspec files
        - Environment configuration (compute type, image, privileged mode)
        - Environment variables
        - GitHub authentication via CodeConnections
        """
        build_name = build.get("name", "custom-build")
        
        # Parse source configuration
        source_config = build.get("source", {})
        source_type = source_config.get("type", "GITHUB").upper()
        source_location = source_config.get("location")
        source_branch = source_config.get("branch", "main")
        
        # Determine if this is the right step type (pre or post)
        # Only create the step if it's supposed to run at this point
        # For now, assume CodeBuild steps run as pre_steps by default
        if key != "pre_steps":
            return None
        
        if not source_location:
            logger.warning(f"Build '{build_name}' has no source location specified, skipping")
            return None
        
        # Parse buildspec
        # If a buildspec path is specified, try to load it locally and convert to from_object()
        buildspec_path = build.get("buildspec")
        buildspec = None

        if buildspec_path:
            try:
                candidate = Path(buildspec_path)
                if not candidate.is_file():
                    # Try relative to cwd
                    candidate = Path(os.getcwd()) / buildspec_path
                if candidate.is_file():
                    with candidate.open("r", encoding="utf-8") as f:
                        yml = yaml.safe_load(f)
                    if isinstance(yml, dict):
                        buildspec = codebuild.BuildSpec.from_object(yml)
                    else:
                        raise ValueError("Parsed buildspec YAML is not a dictionary")
                else:
                    raise FileNotFoundError(f"Buildspec file not found: {buildspec_path}")
            except Exception as exc:
                raise RuntimeError(f"Failed to load buildspec from '{buildspec_path}': {exc}")
        else:
            # No buildspec specified - check for inline commands
            inline_commands = build.get("commands", [])
            if isinstance(inline_commands, str):
                inline_commands = [inline_commands]
            if inline_commands:
                # Create inline buildspec from commands
                buildspec = codebuild.BuildSpec.from_object({
                    "version": "0.2",
                    "phases": {
                        "build": {
                            "commands": inline_commands
                        }
                    }
                })
        
        # Parse environment configuration
        env_config = build.get("environment", {})
        compute_type_str = env_config.get("compute_type", "BUILD_GENERAL1_SMALL")
        
        # Map string to CDK enum
        compute_type_map = {
            "BUILD_GENERAL1_SMALL": codebuild.ComputeType.SMALL,
            "BUILD_GENERAL1_MEDIUM": codebuild.ComputeType.MEDIUM,
            "BUILD_GENERAL1_LARGE": codebuild.ComputeType.LARGE,
            "BUILD_GENERAL1_2XLARGE": codebuild.ComputeType.X2_LARGE,
        }
        compute_type = compute_type_map.get(compute_type_str, codebuild.ComputeType.SMALL)
        
        build_image_str = env_config.get("image", "aws/codebuild/standard:7.0")
        privileged_mode = env_config.get("privileged_mode", False)
        
        # Parse build image
        if build_image_str.startswith("aws/codebuild/standard:"):
            version = build_image_str.split(":")[-1]
            build_image = codebuild.LinuxBuildImage.from_code_build_image_id(f"aws/codebuild/standard:{version}")
        else:
            build_image = codebuild.LinuxBuildImage.from_code_build_image_id(build_image_str)
        
        # Parse environment variables
        env_vars_list = build.get("environment_variables", [])
        env_vars = {}
        for env_var in env_vars_list:
            var_name = env_var.get("name")
            var_value = env_var.get("value")
            var_type = env_var.get("type", "PLAINTEXT")
            
            if var_name and var_value is not None:
                if var_type == "PLAINTEXT":
                    env_vars[var_name] = codebuild.BuildEnvironmentVariable(value=str(var_value))
                elif var_type == "PARAMETER_STORE":
                    env_vars[var_name] = codebuild.BuildEnvironmentVariable(
                        value=str(var_value),
                        type=codebuild.BuildEnvironmentVariableType.PARAMETER_STORE
                    )
                elif var_type == "SECRETS_MANAGER":
                    env_vars[var_name] = codebuild.BuildEnvironmentVariable(
                        value=str(var_value),
                        type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER
                    )
        
        # Create build environment
        build_environment = codebuild.BuildEnvironment(
            build_image=build_image,
            compute_type=compute_type,
            privileged=privileged_mode,
            environment_variables=env_vars
        )
        
        # Determine input source
        if source_type == "GITHUB":
            # GitHub source - supports both public and private repos
            # For private repos, use the workload's code repository connection
            repo_string = self._parse_github_repo_string(source_location)
            cache_key = f"{repo_string}:{source_branch}"
            input_source = self._source_cache.get(cache_key)
            if not input_source:
                input_source = pipelines.CodePipelineSource.connection(
                    repo_string=repo_string,
                    branch=source_branch,
                    connection_arn=self.workload.devops.code_repository.connector_arn,
                    action_name=f"{build_name}",
                )
                self._source_cache[cache_key] = input_source
        else:
            logger.warning(f"Unsupported source type '{source_type}' for build '{build_name}'")
            return None
        
        # Create CodeBuildStep
        logger.info(f"Creating CodeBuildStep '{build_name}' with source from {source_location}")
        
        # CodeBuildStep requires 'commands' param; when using a buildspec (repo or inline)
        # we pass an empty list so only the buildspec runs
        commands: List[str] = []
        
        codebuild_step = pipelines.CodeBuildStep(
            id=f"{build_name}-{stage_name}",
            input=input_source,
            commands=commands,
            build_environment=build_environment,
            partial_build_spec=buildspec,
        )
        
        return codebuild_step
    
    def _parse_github_repo_string(self, location: str) -> str:
        """
        Converts GitHub URL to org/repo format.
        
        Examples:
        - https://github.com/geekcafe/myrepo.git -> geekcafe/myrepo
        - https://github.com/geekcafe/myrepo -> geekcafe/myrepo
        - geekcafe/myrepo -> geekcafe/myrepo
        """
        if location.startswith("https://github.com/"):
            # Remove https://github.com/ prefix
            repo_string = location.replace("https://github.com/", "")
            # Remove .git suffix if present
            if repo_string.endswith(".git"):
                repo_string = repo_string[:-4]
            return repo_string
        else:
            # Assume it's already in org/repo format
            return location

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
                    stack_config=stack_config,
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

        if not cf_stacks:
            print(f"\t\t ⚠️ No stacks added to stage: {stage_config.name}")
            print(f"\t\t ⚠️ Internal Stack Count: {len(stage_config.stacks)}")

        # add dependencies
        for cf_stack in cf_stacks:
            dependencies = cf_stack["stack_config"].dependencies
            if cf_stack["stack_config"].dictionary.get("depends_on"):
                # add to the array
                dependencies.extend(cf_stack["stack_config"].dictionary.get("depends_on"))

            if dependencies:
                for dependency in dependencies:
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

        build_commands = self._get_build_commands()

        # Convert absolute output directory to relative path for BuildSpec
        # This prevents baking in local absolute paths
        cdk_out_directory = self._get_relative_output_directory()

        if cdk_out_directory.startswith("/"):
            raise ValueError("CDK output directory must be a relative path")

        # Debug logging - will be baked into buildspec
        build_commands.append(
            f"echo '👉 CDK output directory (relative): {cdk_out_directory}'"
        )

        shell = pipelines.ShellStep(
            "CDK Synth",
            input=self._get_source_repository(),
            commands=build_commands,
            primary_output_directory=cdk_out_directory,
        )

        return shell

    def _get_relative_output_directory(self) -> str:
        """
        Convert absolute output directory to relative path from repository root.
        This prevents baking local absolute paths into the BuildSpec.

        Example:
            Absolute: /Users/eric/project/devops/cdk-iac/cdk.out
            Relative: devops/cdk-iac/cdk.out
        """
        output_dir = self.workload.output_directory

        # Get the current working directory (repository root during synthesis)
        cwd = os.getcwd()

        # Convert to absolute paths for reliable comparison
        abs_output = os.path.abspath(output_dir)
        abs_cwd = os.path.abspath(cwd)

        # Compute relative path from repo root to output directory
        try:
            relative_path = os.path.relpath(abs_output, abs_cwd)
            return relative_path
        except ValueError:
            print(f"Failed to compute relative path from {abs_output} to {abs_cwd}")
            # Different drives on Windows or other edge case
            # Fall back to basename approach (just the directory name)
            return "cdk.out"

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
