"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List

import aws_cdk
from aws_cdk.cx_api import CloudAssembly
from aws_lambda_powertools import Logger

from cdk_factory.configurations.cdk_config import CdkConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.pipeline.pipeline_factory import PipelineFactoryStack
from cdk_factory.stack.stack_factory import StackFactory

logger = Logger()
VERBOSE = True


class WorkloadFactory:
    """
    Workload Factory
    """

    def __init__(
        self,
        app: aws_cdk.App,
        config_path: str,
        runtime_directory: str,
        outdir: str | None = None,
        paths: List[str] | None = None,
        cdk_app_file: str | None = None,
    ):
        self.cdk_config = CdkConfig(
            config_path=config_path,
            cdk_context=app.node.get_all_context(),
            runtime_directory=runtime_directory,
            paths=paths,
        )
        self.workload: WorkloadConfig = WorkloadConfig(config=self.cdk_config.config)
        self.workload.paths = paths or []
        self.workload.cdk_app_file = cdk_app_file or __file__
        self.app = app
        self.outdir = outdir
        self.workload.output_directory = outdir

    def synth(self) -> CloudAssembly:
        """Build the workload"""

        self.__generate_deployments()

        return self.app.synth()

    def __generate_deployments(self):
        """
        Generates a deployment pipeline
        """

        logger.info(
            {
                "action": "generate_deployments",
                "message": "Generating Deployments",
            }
        )

        if self.workload.deployments is None or len(self.workload.deployments) == 0:
            logger.info(
                {
                    "action": "generate_deployments",
                    "message": "No deployments found",
                }
            )
            return 0

        for deployment in self.workload.deployments:

            if deployment.enabled:
                self.__build_pipelines(deployment)
                self.__build_stacks(deployment)
            else:
                if VERBOSE:
                    print(
                        f"Skipping deployment: {deployment.name}. Reason enabled: {deployment.enabled}"
                    )

        logger.info(
            {
                "action": "generate_deployments",
                "message": "Completed",
            }
        )

    def __build_stacks(self, deployment: DeploymentConfig):
        if deployment.mode != "stack":
            return

        if VERBOSE:
            print(
                "######################################################################"
            )
            print(f"✨ Building 🎁 deployment stack: {deployment.name}")
            print(
                "######################################################################"
            )
        stack: StackConfig
        factory: StackFactory = StackFactory()

        for stack in deployment.stacks:
            if stack.enabled:
                kwargs = {}
                if stack.kwargs:
                    kwargs = stack.kwargs
                print(f"building stack: {stack.name}")
                module = factory.load_module(
                    module_name=stack.module, scope=self.app, id=stack.name, **kwargs
                )
                module.build(
                    stack_config=stack, deployment=deployment, workload=self.workload
                )

        if VERBOSE:
            print(
                "######################################################################"
            )
            print(f"✨ Completed 🎁 deployment stack: {deployment.name}")
            print(
                "######################################################################"
            )
            print("")

    def __build_pipelines(self, deployment: DeploymentConfig):
        if deployment.mode != "pipeline":
            return

        if VERBOSE:
            print(
                "######################################################################"
            )
            print(f"✨ Building 💧 deployment pipeline: {deployment.pipeline_name}")
            print(
                "######################################################################"
            )

        factory = PipelineFactoryStack(
            scope=self.app,
            id=deployment.name,
            deployment=deployment,
            outdir=self.outdir,
            workload=self.workload,
            cdk_config=self.cdk_config,
            description=deployment.description,
        )

        factory.build()

        if VERBOSE:
            print(
                "######################################################################"
            )
            print(f"✨ Completed 💧 deployment pipeline: {deployment.pipeline_name}")
            print(
                "######################################################################"
            )
            print("")
