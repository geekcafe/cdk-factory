"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Any, Dict, List, Optional

# from cdk_factory.configurations.resources._resources import Resources
from cdk_factory.configurations.resources.resource_naming import ResourceNaming
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.resources.route53_hosted_zone import (
    Route53HostedZoneConfig,
)
from cdk_factory.configurations.stack import StackConfig


class DeploymentConfig:
    """
    Deployment Configuration
    """

    def __init__(self, workload: dict, deployment: dict) -> None:
        self.__workload: dict = workload
        self.__deployment: dict = deployment
        self.__pipeline: dict = {}
        self.__stacks: List[StackConfig] = []
        self.__load()

    def __load(self):
        # Validate environment consistency
        deployment_env = self.__deployment.get("environment")
        workload_env = self.__workload.get("environment")
        
        if deployment_env and workload_env and deployment_env != workload_env:
            from aws_lambda_powertools import Logger
            logger = Logger()
            logger.warning(
                f"Environment mismatch: deployment.environment='{deployment_env}' != workload.environment='{workload_env}'. "
                f"Using workload.environment for consistency."
            )
        
        self.__load_pipeline()
        self.__load_stacks()

    def __load_stacks(self):
        """
        Loads the stacks for the deployment
        """
        stacks = self.__deployment.get("stacks", [])
        self.__stacks = []
        for stack in stacks:
            if isinstance(stack, dict):
                self.__stacks.append(StackConfig(stack, self.__workload))
            if isinstance(stack, str):
                # if the stack is a string, it's the stack name
                # and we need to load the stack configuration
                # from the workload
                stack_list: List[dict] = self.__workload.get("stacks", [])
                stack_dict: dict | None = None
                for stack_item in stack_list:
                    if stack_item.get("name") == stack:
                        stack_dict = stack_item
                        break
                if stack_dict is None:
                    raise ValueError(f"Stack {stack} not found in workload")
                self.__stacks.append(StackConfig(stack_dict, self.__workload))

    def __load_pipeline(self):
        """
        Loads the pipeline configuration (if defined)
        """
        pipeline_name = self.pipeline_name

        if pipeline_name is None:
            return

        p = self.__deployment.get("pipeline")
        if isinstance(p, dict):
            # this instance we are defining the pipeline at the deployment level
            # basically inline (which is typically the preferred way to do it)
            self.__pipeline = p
            return

        # if we defined the pipeline with a name, then we should look at a list
        # of pipelines defined at the workload level and select the correct one
        # they must match the name defined at the deployment level
        pipelines = self.workload.get("pipelines", [])
        pipeline: dict = {}
        # find the defined pipeline from our list of pipelines
        for pipeline in pipelines:
            if pipeline.get("name") == pipeline_name:
                self.__pipeline = pipeline
                return

        if self.mode == "pipeline":
            self.__pipeline = self.__deployment
            return

        # if we get here, we didn't find the pipeline name
        # in the list but we defined a name in the deployment
        raise ValueError(
            f'The Pipeline name "{pipeline_name}" was not found in '
            f"the list of defined pipelines: {pipelines}"
        )

    @property
    def config(self) -> Dict[str, Any]:
        return self.__deployment

    @property
    def stacks(self) -> List[StackConfig]:
        """Deployment Stacks"""
        return self.__stacks

    @property
    def workload(self) -> dict:
        """Access to the workload dictionary"""
        return self.__workload

    @property
    def pipeline(self) -> dict:
        """Access to the pipeline dictionary"""
        return self.__pipeline

    @property
    def pipeline_name(self) -> str | None:
        """Returns the pipeline name defined at the deployment level"""
        pipeline = self.__deployment.get("pipeline")
        if not pipeline:
            return None

        if isinstance(pipeline, dict):
            return pipeline.get("name")
        elif isinstance(pipeline, str):
            return pipeline
        else:
            raise ValueError("Pipeline must be a dictionary or string or None")

    @property
    def name(self):
        """
        Returns the deployment name or unique deployment id
        """
        return self.__deployment["name"]

    @property
    def description(self) -> str | None:
        return self.__deployment.get("description")

    @property
    def mode(self):
        """
        Returns the deployment mode
        """
        if "mode" not in self.__deployment:
            raise ValueError("Deployment mode is required.")

        return self.__deployment["mode"]

    @property
    def branch(self):
        """
        Returns the pipeline branch
        """
        return self.pipeline.get("branch")

    @property
    def manual_approval(self) -> bool:
        """
        Returns the this deployment has an approval process name
        """
        value = self.__deployment.get("manual_approval")
        return str(value).lower() == "true" or value is True

    @property
    def account(self) -> str | None:
        """
        Returns the deployment account number
        """
        return self.__deployment.get("account")

    @property
    def region(self) -> str | None:
        """
        Returns the deployment region name
        """
        return self.__deployment.get("region", "us-east-1")

    @property
    def is_integration(self) -> bool:
        """
        Returns true if this is marked as an integration deployment.
        These deployments go out first and do not require approval.
        Once deployed they should run tests (smoke of full) and if they
        succeed the rest of the deployment can go out... if not then
        we should halt the other deployments.
        """
        value = self.__deployment.get("is_integration")
        return str(value).lower() == "true" or value is True

    @property
    def enabled(self) -> bool:
        """
        Returns the this deployment has an approval process name
        """
        value = self.__deployment.get("enabled")
        return str(value).lower() == "true" or value is True

    @property
    def order(self) -> int:
        """
        Returns the order of the deployment
        """
        value = self.__deployment.get("order", 0)
        return int(value)

    @property
    def workload_name(self) -> str:
        """
        Returns the deployment workload name
        """
        value = self.workload.get("name")
        if value is None:
            raise ValueError("Workload name is required.")
        return value

    @property
    def environment(self):
        """
        Returns the deployment environment name
        """
        return self.__deployment.get("environment")

    @property
    def subdomain(self):
        """
        Returns the deployment subdomain name
        """
        return self.__deployment.get("subdomain")

    @property
    def hosted_zone(self) -> "Route53HostedZoneConfig":
        """Gets the hosted zone name"""
        zone = self.__deployment.get("hosted_zone", {})
        return Route53HostedZoneConfig(zone)

    @property
    def wave_name(self) -> str | None:
        """Gets the wave name"""
        wave_name = self.__deployment.get("wave", {}).get("name")

        return wave_name

    @property
    def ssl_cert_arn(self) -> str | None:
        """Gets the ssl cert arn"""
        cert = self.__deployment.get("ssl_cert_arn")
        return cert

    @property
    def tenant(self) -> str:
        """
        Gets the tenant if configured, otherwise it will return the name of the deployment

        Returns:
            str: tenant name
        """
        tenant = self.__deployment.get("tenant", self.name)

        return tenant

    @property
    def lambdas(self) -> List[dict]:
        """
        Get a dictionary of lambdas for this deployment

        """
        value = self.__deployment.get("lambdas", [])
        return value

    @property
    def api_gateways(self) -> List[Dict[str, Any]]:
        """
        Get a dictionary of api gateways for this deployment

        """
        value = self.__deployment.get("api_gateways", [])
        return value

    @property
    def naming_prefix(self) -> str | None:
        """Gets the naming prefix"""
        value = self.__deployment.get("naming_prefix")

        return value

    @property
    def naming_to_lower_case(self) -> bool:
        """Gets the naming prefix"""
        value = str(self.__deployment.get("naming_to_lower_case")).lower() == "true"

        return value

    @property
    def tags(self) -> Dict[str, str]:
        """
        Returns the tags for this deployment
        """
        tags = self.__deployment.get("tags", {})
        if not isinstance(tags, dict):
            raise ValueError("Tags must be a dictionary")
        return tags

    def build_resource_name(
        self,
        resource_name: str,
        resource_type: Optional[ResourceTypes] = None,
    ):
        """
        Builds a name based off the "name" and then specific fields
        from workload and pipeline.  It's important that this does not change once we
        go live.

        NOTICE - BE CAREFUL
        Changing this can break deployments!!  Resources and stack names use this.
        If you break this pattern, it will most-likely have an adverse affect on deployments.
        """

        if not resource_name:
            raise ValueError("Resource name is required")

        resource_name = str(resource_name).replace(
            "{{workload-name}}", self.workload_name
        )
        resource_name = str(resource_name).replace("{{deployment-name}}", self.name)

        assert resource_name
        # resource validation

        if resource_type:
            resource_name = ResourceNaming.validate_name(
                resource_name,
                resource_type=resource_type,
                fix=str(self.workload.get("auto_fix_resource_names", False)).lower()
                == "true",
            )

        if self.naming_to_lower_case:
            resource_name = resource_name.lower()

        return resource_name

    @property
    def naming_convention(self) -> str:
        """
        Returns the naming convention for deployment
        """
        return self.__deployment.get("naming_convention", "latest")

    def get_ssm_parameter_arn(self, parameter_name: str) -> str:
        """
        Gets an SSM Parameter for parameter store.
        Note that you can't have duplicates across different stacks, Cfn will error out.

        """
        if parameter_name.startswith("/"):
            parameter_name = parameter_name[1::]

        arn = f"arn:aws:ssm:{self.region}:{self.account}:parameter/{parameter_name}"

        return arn

    def get_ssm_parameter_name(
        self,
        resource_type: str,
        resource_name: str,
        resource_property: Optional[str] = None,
    ) -> str:
        """
        Gets an SSM Parameter for parameter store.
        Note that you can't have duplicates across different stacks, Cfn will error out.
        Arguments:
            resource_type {str} -- Resource Type (e.g S3)
            resource_name {str} -- Resource Name (bucket name)
            resource_property {str} -- Resource Property (optional) (arn)
        Returns:
            str: The SSM Parameter Name
        Best Practice Nameing Convention:
            /<env>/<workload-or-app-name>/<resource-type>/<name>/<optional-sub-property>
            /dev/workload-name/s3/primary-bucket
            /dev/workload-name/hosted-zone/example.com/id
        """

        parameter_name = (
            f"/{self.environment}/{self.workload_name}/{resource_type}"
            f"/{resource_name}"
        )
        if resource_property:
            parameter_name = f"{parameter_name}/{resource_property}"

        return parameter_name.lower()
