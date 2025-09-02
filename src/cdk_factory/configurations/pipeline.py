"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from typing import List, Optional, Dict, Any

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
        self._deployments: List[DeploymentConfig] = []
        self._stages: List[PipelineStageConfig] = []
        self.__load_deployments()

    def __load_deployments(self):
        """
        Loads the deployments
        """
        deployment: dict = {}
        deployments: List[DeploymentConfig] = []

        # this is the newer way
        for deployment in self.workload.get("deployments", []):
            if deployment.get("mode") == "pipeline":
                deployments.append(
                    DeploymentConfig(workload=self.workload, deployment=deployment)
                )

        # sort the deployments by order
        deployments.sort(key=lambda x: x.order)
        self._deployments = deployments

    @property
    def deployments(self) -> List[DeploymentConfig]:
        """
        Returns the deployments for this pipeline
        """
        return self._deployments

    @property
    def stages(self) -> List[PipelineStageConfig]:
        """
        Returns the stages for this pipeline
        """
        if not self._stages:
            for stage in self.pipeline.get("stages", []):
                self._stages.append(PipelineStageConfig(stage, self.workload))
        return self._stages

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
    def verbose_output(self) -> bool:
        # todo: add to config
        return False

    @property
    def npm_build_mode(self):
        """
        Returns npm build mode which is per pipeline and not per wave.
        """
        return self.pipeline["npm_build_mode"]

    def build_resource_name(
        self,
        name: str,
        resource_type: Optional[ResourceTypes] = None,
        lower_case: bool = True,
    ):
        """
        Builds a name based on the workload_name-stack_name-name
        We need to avoid using things like branch names and environment names
        as we may want to change them in the future for a given stack.
        """
        resource_name = name

        if not resource_name:
            raise ValueError("Resource name is required")

        resource_name = str(resource_name).replace(
            "{{workload-name}}", self.workload_name
        )
        resource_name = str(resource_name).replace("{{pipeline-name}}", self.name)

        resource_name = str(resource_name).replace(
            "{{environment}}", os.getenv("ENVIRONMENT", "")
        )

        # remove any leading dashes -
        parts = resource_name.split("-")
        # remove any empty elements in the array
        parts = [x for x in parts if x]
        # put it back
        resource_name = "-".join(parts)

        if resource_type:
            resource_name = ResourceNaming.validate_name(
                resource_name,
                resource_type=resource_type,
                fix=str(self.workload.get("auto_fix_resource_names", False)).lower()
                == "true",
            )

        if lower_case:
            resource_name = resource_name.lower()

        return resource_name

    def code_artifact_logins(self, include_profile: bool = False) -> List[str]:
        """
        Returns the code artifact logins (if any)
        """
        from cdk_factory.configurations.resources.code_artifact_login import CodeArtifactLoginConfig
        
        logins_config = self.pipeline.get("code_artifact_logins", [])
        
        if not logins_config:
            return []
        
        # Create enhanced config object
        login_config = CodeArtifactLoginConfig(logins_config)
        
        # Return commands appropriate for current environment
        return login_config.get_commands_for_environment()
