"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from typing import List, Optional

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.pipeline_stage import PipelineStageConfig
from cdk_factory.configurations.resources.resource_naming import ResourceNaming
from cdk_factory.configurations.resources.resource_types import ResourceTypes


class PipelineConfig:
    """
    Pipeline settings for deployments
    """

    def __init__(self, pipeline: dict, workload: dict) -> None:
        self.pipeline: dict = pipeline
        self.workload: dict = workload
        self.__deployments: List[DeploymentConfig] = []
        self.__stages: List[PipelineStageConfig] = []
        self.__load_deployments()

    def __load_deployments(self):
        """
        Loads the deployments
        """
        deployment: dict = {}
        deployments: List[DeploymentConfig] = []
        for deployment in self.pipeline.get("deployments", []):
            resolved_deployment = self.__load_deployment(deployment.get("name", {}))
            deployments.append(
                DeploymentConfig(workload=self.workload, deployment=resolved_deployment)
            )

        # sort the deployments by order
        deployments.sort(key=lambda x: x.order)
        self.__deployments = deployments

    def __load_deployment(self, deployment_name: str):
        # look for the config at the workload level
        deployments = self.workload.get("deployments", [])

        workload_level_deployment: dict = {}
        pipeline_level_deployment: dict = {}
        if deployments:
            deployment: dict = {}
            for deployment in deployments:
                if deployment.get("name") == deployment_name:
                    workload_level_deployment = deployment
                    break

        # now check for one in our pipelinel level
        for deployment in self.pipeline.get("deployments", []):
            if deployment.get("name") == deployment_name:
                pipeline_level_deployment = deployment
                break

        resolved_deployment = {}
        # merge the two dictionaries
        # start witht workload
        resolved_deployment.update(workload_level_deployment)
        # now merge the overrides
        resolved_deployment.update(pipeline_level_deployment)

        return resolved_deployment

    @property
    def deployments(self) -> List[DeploymentConfig]:
        """
        Returns the deployments for this pipeline
        """
        return self.__deployments

    @property
    def stages(self) -> List[PipelineStageConfig]:
        """
        Returns the stages for this pipeline
        """
        if not self.__stages:
            for stage in self.pipeline.get("stages", []):
                self.__stages.append(PipelineStageConfig(stage, self.workload))
        return self.__stages

    @property
    def name(self):
        """
        Returns the name for deployment
        """
        return self.pipeline["name"]

    @property
    def workload_name(self):
        """Gets the workload name"""
        return self.workload.get("name")

    @property
    def branch(self):
        """
        Returns the git branch this deployment is using
        """
        return self.pipeline["branch"]

    @property
    def enabled(self) -> bool:
        """
        Returns the if this pipeline is enabled
        """
        value = self.pipeline.get("enabled")
        return str(value).lower() == "true" or value is True

    @property
    def versbose_output(self) -> bool:
        # todo: add to config
        return False

    @property
    def npm_build_mode(self):
        """
        Returns npm build mode which is per pipeline and not per wave.
        """
        return self.pipeline["npm_build_mode"]

    def build_resource_name(
        self, name: str, resource_type: Optional[ResourceTypes] = None
    ):
        """
        Builds a name based on the workload_name-stack_name-name
        We need to avoid using things like branch names and environment names
        as we may want to change them in the future for a given stack.
        """

        assert name
        assert self.name
        assert self.workload_name
        separator = "-"

        if resource_type and resource_type == ResourceTypes.CLOUD_WATCH_LOGS:
            separator = "/"

        pipline_name = self.name

        new_name = f"{self.workload_name}{separator}{pipline_name}{separator}{name}"

        if resource_type:
            new_name = ResourceNaming.validate_name(
                new_name, resource_type=resource_type, fix=True
            )

        return new_name.lower()

    def code_artifact_logins(self, include_profile: bool = False) -> List[str]:
        """
        Returns the code artifact logins (if any)
        """
        # todo

        logins = self.pipeline.get("code_artifact_logins", [])

        if not isinstance(logins, list):
            logins = [logins]

        # if not logins:
        #     workload = WorkloadConfig(self.workload)

        #     domain = workload.devops.code_artifact_domain
        #     repository = workload.devops.code_artifact_repository
        #     region = workload.devops.region
        #     codeartifact_login_commands = f"aws codeartifact login --tool pip --domain {domain} --repository {repository} --region {region}"
        #     # if debugging / or a profile is being used
        #     if os.getenv("AWS_PROFILE") and include_profile:
        #         codeartifact_login_commands = f"{codeartifact_login_commands} --profile {os.getenv('AWS_PROFILE')}"
        #     logins = [codeartifact_login_commands]
        return logins
