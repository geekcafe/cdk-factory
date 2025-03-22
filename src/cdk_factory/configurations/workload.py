"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from typing import Any, Dict, List
from aws_lambda_powertools import Logger
from cdk_factory.utilities.json_utility import JsonUtility

from cdk_factory.configurations.devops import DevOps
from cdk_factory.configurations.management import Management
from cdk_factory.configurations.resources.cloudfront import CloudFrontConfig
from cdk_factory.configurations.resources._resources import Resources
from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.pipeline_stage import PipelineStageConfig
from cdk_factory.configurations.deployment import DeploymentConfig

logger = Logger()


class WorkloadConfig:
    """
    Workload Configuration
    """

    def __init__(self, config: str | dict) -> None:
        self.__workload: dict | None = None

        self.__devops: DevOps | None = None
        self.__management: Management | None = None
        self.__cloudfront: CloudFrontConfig | None = None
        self.__resources: Resources | None = None
        self.__pipelines: List[PipelineConfig] = []
        self.__stacks: List[StackConfig] = []
        self.__config_path: str | None = None
        self.__pipeline_stages: List[PipelineStageConfig] = []
        self.__deployments: List[DeploymentConfig] = []
        self.__tags: Dict[str, Any] = {}
        self.__load_config(config)

        self.__paths: list[str] = []
        self.__cdk_app_file: str | None = None

    def __load_config(self, config: str | dict) -> None:
        if isinstance(config, str):
            config_path = config
            if not os.path.exists(config_path):
                raise FileNotFoundError(config_path)

            ju = JsonUtility(config_path)
            config = ju.load()

        if not isinstance(config, dict):
            raise ValueError(
                "Failed to load Config. Config must be a dictionary at this point."
            )

        workload: dict = {}

        if "workload" in config:
            workload = config["workload"]
        else:
            workload = config

        self.__workload = workload

        self.__devops = DevOps(workload["devops"])
        self.__management = Management(workload.get("management", {}))
        self.__cloudfront = CloudFrontConfig(workload.get("cloudfront", {}))
        self.__resources = Resources(workload.get("resources", {}))

        for pipeline in workload.get("pipelines", []):
            self.pipelines.append(PipelineConfig(pipeline, workload=workload))

        for stack in workload.get("stacks", []):
            self.stacks.append(StackConfig(stack=stack, workload=workload))

        for pipeline_stage in workload.get("stages", []):
            self.__pipeline_stages.append(
                PipelineStageConfig(pipeline_stage, workload=workload)
            )

        for deployment in workload.get("deployments", []):
            for pipeline in self.pipelines:
                self.__deployments.append(DeploymentConfig(workload, deployment))

        self.tags = workload.get("tags", {})

    @property
    def devops(self) -> DevOps:
        """The DevOps configuration"""
        if not self.__devops:
            raise ValueError("DevOps is not defined in the configuration.")
        return self.__devops

    @property
    def management(self) -> Management | None:
        """The Management configuration"""

        return self.__management

    @property
    def cloudfront(self) -> CloudFrontConfig | None:
        """The CloudFront configuration"""

        return self.__cloudfront

    @property
    def resources(self) -> Resources | None:
        """The Resources configuration"""
        return self.__resources

    @property
    def pipelines(self) -> List[PipelineConfig]:
        """The Pipelines configuration"""
        return self.__pipelines

    @property
    def deployments(self) -> List[DeploymentConfig]:
        """The Pipelines configuration"""
        return self.__deployments

    @property
    def stacks(self) -> List[StackConfig]:
        """The Stacks configuration"""
        return self.__stacks

    @property
    def config_path(self) -> str | None:
        """The path to the configuration file"""
        return self.__config_path

    @property
    def dictionary(self) -> dict:
        """Returns the dictionay version of this object"""
        if not self.__workload:
            raise ValueError("Workload is not defined in the configuration.")
        if not isinstance(self.__workload, dict):
            raise ValueError("Workload is not a dictionary")
        return self.__workload

    @property
    def name(self) -> str:
        """
        Returns the workload name
        """
        value = self.dictionary.get("name")
        if not value:
            raise ValueError("Workload name is required")
        if not isinstance(value, str):
            raise ValueError("Workload name must be a string")

        return value

    @property
    def domain(self) -> str | None:
        """
        Returns the workload root domain
        """
        value = self.dictionary.get("primary_domain")
        if isinstance(value, str):
            return value.lower()
        else:
            if value is not None:
                logger.error("Workload primary_domain must be a string")

            return None

    @property
    def tags(self) -> Dict[str, Any]:
        """
        Returns the workload tags
        """
        return self.__tags

    @tags.setter
    def tags(self, value: Dict[str, Any]):
        """
        Sets the workload tags
        """
        if not isinstance(value, dict):
            raise ValueError("Tags must be a dictionary")
        self.__tags = value

    @property
    def paths(self) -> list[str]:
        """
        Returns the cdk root directory
        """
        return self.__paths

    @paths.setter
    def paths(self, values: list[str]):
        """
        Sets the cdk root directory
        """
        _values: List[str] = []
        for v in values:
            if os.path.isfile(v):
                v = os.path.dirname(v)

            _values.append(v)

        self.__paths = list(set(_values))

    @property
    def cdk_app_file(self) -> str | None:
        """
        Returns the cdk app file
        """
        return self.__cdk_app_file

    @cdk_app_file.setter
    def cdk_app_file(self, value: str):
        """
        Sets the cdk root directory
        """
        # if not os.path.isfile(value):
        #     raise ValueError(f"{value} is not a file")

        self.__cdk_app_file = value
