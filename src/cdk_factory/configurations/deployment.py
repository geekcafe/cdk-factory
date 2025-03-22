"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Any, Dict, List, Optional

from cdk_factory.configurations.resources._resources import Resources
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
        self.__resources: Resources | None = None
        self.__stacks: List[StackConfig] = []
        self.__load()

    def __load(self):
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

        pipelines = self.workload.get("pipelines", [])
        pipeline: dict = {}
        # find the defined pipeline
        for pipeline in pipelines:
            if pipeline.get("name") == pipeline_name:
                self.__pipeline = pipeline
                return

        # if we get here, we didn't find the pipeline name
        # in the list but we defined a name in the deployment
        raise ValueError(
            f"The Pipeline name {pipeline_name} was not found in "
            "the list of defined pipelines. "
        )

    @property
    def resources(self) -> Resources:
        """Deployment Resources"""
        if self.__resources is None:
            self.__resources = Resources(self.__deployment.get("resources", {}))

        return self.__resources

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
        """Access to the pipline dictionary"""
        return self.__pipeline

    @property
    def pipeline_name(self) -> str | None:
        """Returns the pipeline name defined at the deployment level"""
        return self.__deployment.get("pipeline")

    @property
    def name(self):
        """
        Returns the deployment name or unique deployment id
        """
        return self.__deployment["name"]

    @property
    def mode(self):
        """
        Returns the deployment mode
        """
        if "mode" not in self.__deployment:
            raise ValueError("Deployment mode is required.")

        return self.__deployment["mode"]

    @property
    def stack_name(self):
        """
        Returns the pipeline stack_name
        """
        return self.__pipeline.get("name")

    @property
    def branch(self):
        """
        Returns the pipeline branch
        """
        return self.__pipeline.get("branch")

    @property
    def manual_approval(self) -> bool:
        """
        Returns the this deployment has an approval process name
        """
        value = self.__deployment.get("manual_approval")
        return str(value).lower() == "true" or value is True

    @property
    def account(self):
        """
        Returns the deployment account number
        """
        return self.__deployment["account"]

    @property
    def region(self):
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
        return self.__deployment["environment"]

    @property
    def subdomain(self):
        """
        Returns the deployment subdomain name
        """
        return self.__deployment["subdomain"]

    @property
    def hosted_zone(self) -> "Route53HostedZoneConfig":
        """Gets the hosted zone name"""
        zone = self.__deployment.get("hosted_zone", {})
        return Route53HostedZoneConfig(zone)

    @property
    def wave_name(self) -> str | None:
        """Gets the wave name"""
        return self.__deployment.get("wave", {}).get(
            "name", f"{self.name}-deployment-wave"
        )

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

    # def get_ssm_parameter_name(self, resource: str) -> str:
    #     """
    #     Gets a standardized ssm parameter name
    #     Args:
    #         resource (Enum): ther resource name we are creating a parameter for

    #     Returns:
    #         str: a formatted parameter using slashes in the form of
    #         f"/{self.workload.name}/{self.stack_name}/{self.name}/{resource}"
    #     """

    #     parameter = f"/{self.workload.get('name')}/{self.stack_name}/{self.name}/{str(resource)}"

    #     return str(parameter).lower()

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

        NOTICE - BECAREFULL
        Changing this can break deployments!!  Resources and stack names use this.
        If you break this pattern, it will mostlikely have an adverse affect on deployments.
        """

        if not resource_name:
            raise ValueError("Resource name is required")

        if resource_type:
            if resource_type == ResourceTypes.CLOUD_WATCH_LOGS:
                separator = "/"
            if resource_type == ResourceTypes.PARAMETER_STORE:
                separator = "/"

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

    # def get_ssm_parameter_ecr_name(self, ecr_name: str) -> str:
    #     """
    #     A standardized ssm parameter naming convention for the ecr name
    #     Used to store information and state that can be passed around
    #     """
    #     parameter = self.__get_ssm_parameter_for_ecr(
    #         ecr_name=ecr_name, ecr_attribute="name"
    #     )

    #     return parameter

    # def get_ssm_parameter_ecr_arn(self, ecr_name: str) -> str:
    #     """
    #     A standardized ssm parameter naming convention for the ecr arn
    #     Used to store information and state that can be passed around
    #     """
    #     parameter = self.__get_ssm_parameter_for_ecr(
    #         ecr_name=ecr_name, ecr_attribute="arn"
    #     )

    #     return parameter

    # def get_ssm_parameter_ecr_uri(self, ecr_name: str) -> str:
    #     """
    #     A standardized ssm parameter naming convention for the ecr uri
    #     Used to store information and state that can be passed around
    #     """

    #     parameter = self.__get_ssm_parameter_for_ecr(
    #         ecr_name=ecr_name, ecr_attribute="uri"
    #     )

    #     return parameter

    # def __get_ssm_parameter_for_ecr(self, ecr_name: str, ecr_attribute: str) -> str:
    #     assert self.environment
    #     assert self.branch

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="ecr",
    #         resource_name=ecr_name,
    #         resource_property=ecr_attribute,
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_hosted_zone_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention for the hosted zone id
    #     Used to store information and state that can be passed around
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="hosted_zone",
    #         resource_name=f"{self.hosted_zone.name}",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_user_pool_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="userpool",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_admin_user_pool_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="userpool/admin",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_user_pool_id_list(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention for a list of user pool id's
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="userpools",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_user_pool_arn(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="userpool",
    #         resource_property="arn",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_admin_user_pool_arn(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="userpool/admin",
    #         resource_property="arn",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_primary_client_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="client/primary",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_admin_client_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="client/admin",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_secret_client_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="client/secret",
    #         resource_property="id",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_cognito_secret_client_secret(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="cognito",
    #         resource_name="client/secret",
    #         resource_property="value",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_rum_endpoint(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="rum",
    #         resource_name="endpoint",
    #         resource_property="value",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_rum_application_region(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="rum",
    #         resource_name="application_region",
    #         resource_property="value",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_rum_application_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="rum",
    #         resource_name="application_id",
    #         resource_property="value",
    #     )

    #     return parameter

    # @property
    # def ssm_parameter_for_rum_identity_pool_id(self) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name="rum",
    #         resource_name="identity_pool_id",
    #         resource_property="value",
    #     )

    #     return parameter

    # # @property
    # def get_ssm_parameter_for_api_gateway_id(self, name: str) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name=f"api-gateway-{name}",
    #         resource_name="rest-api",
    #         resource_property="id",
    #     )

    #     return parameter

    # # @property
    # def get_ssm_parameter_for_api_gateway_root_resource_id(self, name: str) -> str:
    #     """
    #     A standardized ssm parameter naming convention
    #     """

    #     parameter = self.get_ssm_parameter(
    #         resource_type_name=f"api-gateway-{name}",
    #         resource_name="root",
    #         resource_property="resource-id",
    #     )

    #     return parameter

    # def get_ssm_parameter(
    #     self, resource_type_name: str, resource_name: str, resource_property: str
    # ) -> str:
    #     """
    #     Gets an SSM Parameter for parameter store.
    #     Note that you can't have duplicates across different stacks, Cfn will error out.

    #     """

    #     parameter_name = f"{resource_type_name}/{resource_name}/{resource_property}"
    #     parameter_path = f"/{self.workload.get('name')}/{self.pipeline.get('name')}/{self.name}/{parameter_name}"
    #     return parameter_path

    # def get_ssm_parameter_arn(self, parameter_path: str) -> str:
    #     """
    #     Gets an SSM Parameter for parameter store.
    #     Note that you can't have duplicates across different stacks, Cfn will error out.

    #     """
    #     if parameter_path.startswith("/"):
    #         parameter_path = parameter_path[1::]

    #     arn = f"arn:aws:ssm:{self.region}:{self.account}:parameter/{parameter_path}"

    #     return arn

    @property
    def naming_convention(self) -> str:
        """
        Returns the naming convention for deployment
        """
        return self.__deployment.get("naming_convention", "latest")
