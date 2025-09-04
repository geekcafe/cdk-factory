"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from pathlib import Path
from typing import List, Dict, Any
from aws_lambda_powertools import Logger
import aws_cdk
from aws_cdk import aws_lambda
from cdk_factory.configurations.resources.docker import DockerConfig
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
from cdk_factory.configurations.resources.apigateway_route_config import (
    ApiGatewayConfigRouteConfig,
)
from cdk_factory.configurations.resources.ecr import ECRConfig
from cdk_factory.configurations.resources.sqs import SQS
from cdk_factory.configurations.resources.lambda_triggers import LambdaTriggersConfig
from cdk_factory.configurations.resources.cloudwatch_widget import (
    CloudWatchWidgetConfig,
)
from cdk_factory.utilities.os_execute import OsExecute
from cdk_factory.configurations.resources.resource_mapping import (
    ResourceMapping,
)
from cdk_factory.configurations.deployment import DeploymentConfig

logger = Logger()


class LambdaFunctionConfig(EnhancedBaseConfig):
    """Lambda Function Config Settings"""

    def __init__(
        self, config: dict, deployment: DeploymentConfig | None = None
    ) -> None:
        super().__init__(
            config or {},
            resource_type="lambda",
            resource_name=config.get("name", "lambda") if config else "lambda",
        )
        self.__config = config
        self.docker: DockerConfig = DockerConfig(config=config.get("docker", {}))
        self.api: ApiGatewayConfigRouteConfig | None = None

        api_route_config = config.get("api", None)
        if api_route_config and isinstance(api_route_config, dict):
            self.api = ApiGatewayConfigRouteConfig(config=api_route_config)

        self.ecr: ECRConfig = ECRConfig(
            config=config.get("ecr", {}), deployment=deployment
        )
        self.sqs: SQS = SQS(config=config.get("sqs", {}))
        self.triggers: List[LambdaTriggersConfig] = []
        self.cloudwatch_widget: CloudWatchWidgetConfig = CloudWatchWidgetConfig(
            config=config.get("cloudwatch_widget", {})
        )
        self.__name: str | None = None
        self.__execution_role_arn: str | None = None
        self.__execution_role_name: str | None = None
        self.__deployment = config
        self.__load()

    def __load(self) -> None:
        triggers: List[dict] = self.__config.get("triggers", [])

        if triggers:
            for trigger in triggers:
                item = LambdaTriggersConfig(trigger)
                self.triggers.append(item)

        default_queues = [
            {"type": "producer", "queue_name": "app-audit-logger-sqs-queue"}
        ]

        for queue in default_queues:
            # make sure it's not already added
            # get all the queue names
            if self.sqs and self.sqs.queues and isinstance(self.sqs.queues, list):
                queue_names = [q.name for q in self.sqs.queues]
                if queue["queue_name"] not in queue_names:
                    self.sqs.queues.append(SQS(queue))
                else:
                    logger.warning(f"Queue {queue} already added.")

    @property
    def name(self) -> str:
        """Name"""
        if not self.__name and self.__config and isinstance(self.__config, dict):
            self.__name = self.__config.get("name")

        if isinstance(self.__name, str):
            return self.__name
        return ""

    @name.setter
    def name(self, value: str) -> None:
        self.__name = config

    @property
    def resource_policies(self) -> List[dict]:
        """Gets a list of resource polices"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("resource_policies")
            if isinstance(value, list):
                return value

        return []

    @property
    def auto_name(self) -> bool:
        """auto_name"""
        if self.__config and isinstance(self.__config, dict):
            # default to false on the auto naming
            return str(self.__config.get("auto_name", "false")) == "true"

        return False

    @property
    def src(self) -> str:
        """Source Directory"""
        if self.__config and isinstance(self.__config, dict):
            src_directory = self.__config.get("src")

            if src_directory:
                return src_directory

        raise RuntimeError(
            f"Source Directory was not defined for lambda function {self.name}"
        )

    @property
    def version_file(self) -> str:
        """Version File"""
        if self.__config and isinstance(self.__config, dict):
            version_file = self.__config.get("version_file")
            if version_file:
                return version_file

        return ""

    @property
    def version_number(self) -> str:
        """Gets the version number from a file"""
        if self.version_file:
            try:
                path: str = str(Path(__file__).parents[4].absolute())
                path = os.path.join(path, self.version_file)
                if path.endswith(".txt"):
                    # in this case we have an actual version.txt file
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as version_file:
                            return version_file.read()
                elif path.endswith(".py"):
                    if os.path.exists(path):
                        version = OsExecute.execute(["python", path])
                        if version:
                            return version
                else:
                    print(f"Version file not found at {path}")
            except Exception as e:  # noqa: E722 pylint: disable=W0718
                logger.error(e)
                return "0.0.0_e"
        return "0.0.0_na"

    @property
    def handler(self) -> str:
        """Handler"""
        if self.__config and isinstance(self.__config, dict):
            handler = self.__config.get("handler")
            if handler:
                return handler

        return "app.lambda_handler"

    @property
    def description(self) -> str:
        """Description"""
        if self.__config and isinstance(self.__config, dict):
            description = self.__config.get("description")
            if description:
                return description
            else:
                return f"Lambda Function for {self.name}"

        return ""

    @property
    def memory_size(self) -> int:
        """Memory Size"""
        if self.__config and isinstance(self.__config, dict):
            size = self.__config.get("memory_size")
            if size:
                return int(size)

        return 128

    @property
    def reserved_concurrent_executions(self) -> int | None:
        """
        Reserved Concurrent Executions: (sets both the max and min number of concurrent instances)

        This sets both the maximum and minimum number of concurrent instances
        allocated to your function. When a function has reserved concurrency,
        no other function can use that concurrency. Reserved concurrency is useful
        for ensuring that your most critical functions always have enough concurrency
        to handle incoming requests.

        Additionally, reserved concurrency can be used for limiting concurrency to
        prevent overwhelming downstream resources, like database connections.

        Reserved concurrency acts as both a lower and upper bound - it reserves the
        specified capacity exclusively for your function while also preventing it
        from scaling beyond that limit. Configuring reserved concurrency for a
        function incurs no additional charges.

        """
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("reserved_concurrent_executions")
            if value:
                return int(value)

        return None

    @property
    def runtime(self) -> aws_lambda.Runtime:
        """Runtime"""
        if self.__config and isinstance(self.__config, dict):
            runtime = self.__config.get("runtime")
            # at some point we'll need to covert this to a cdk runtime
            if runtime:
                runtime = ResourceMapping.get_runtime(runtime)
                return runtime

        return aws_lambda.Runtime.PYTHON_3_12
        # return aws_lambda.Runtime.PYTHON_3_11

    @property
    def timeout(self) -> aws_cdk.Duration:
        """Timeout"""
        api_max_timeout: int = 30  # technically 29 seconds
        timeout: int = 30
        if self.__config and isinstance(self.__config, dict):
            timeout = int(self.__config.get("timeout", timeout))

        if self.api and (self.api.route or self.api.routes):
            if timeout > api_max_timeout:
                logger.warning(
                    f"Timeout of {timeout} for lambda function {self.name} is greater "
                    f"than the api max timeout of {api_max_timeout} seconds. "
                    f"The api max timeout will be used instead."
                )
            timeout = api_max_timeout

        duration = aws_cdk.Duration.seconds(timeout)
        return duration

    @property
    def stack(self) -> str | None:
        """Stack. Defines which stack the function will go out in"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("stack", "primary")

        return None

    @property
    def dependencies_to_layer(self) -> bool:
        """Dependencies to Layer"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("dependencies_to_layer")).lower() == "true"

        return True

    @property
    def insights_version(self) -> aws_lambda.LambdaInsightsVersion | None:
        """
        Insights Version.  Gets the configured insights vesion.
        NOTE: there are charges for using insights listed as custom metrics - I think.
        """
        if self.__config and isinstance(self.__config, dict):
            version = self.__config.get("insights_version")
            if version:
                return ResourceMapping.get_insights_version(version)

        # default to none if not defined.
        return None

    @property
    def add_common_layer(self) -> bool:
        """Add Common Layer"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("add_common_layer", "true")).lower() == "true"

        return True

    @property
    def architecture(self) -> aws_lambda.Architecture:
        """Architecture"""
        if self.__config and isinstance(self.__config, dict):
            architecture = self.__config.get("architecture")
            if architecture:
                return ResourceMapping.get_architecture(architecture)

        return aws_lambda.Architecture.X86_64

    @property
    def tracing(self) -> aws_lambda.Tracing:
        """Tracing"""
        if self.__config and isinstance(self.__config, dict):
            tracing = self.__config.get("tracing")
            if tracing:
                return ResourceMapping.get_tracing(tracing)

        return aws_lambda.Tracing.ACTIVE

    @property
    def include_power_tools_layer(self) -> bool:
        """Include Power Tools Layer"""
        if self.__config and isinstance(self.__config, dict):
            return (
                str(self.__config.get("include_power_tools_layer", "true")).lower()
                == "true"
            )

        return True

    @property
    def environment_variables(self) -> List[dict]:
        """Environment Variables"""
        environment_vars: List[dict] = []
        if self.__config and isinstance(self.__config, dict):
            environment_vars = self.__config.get("environment_variables", [])

        return environment_vars

    @property
    def log_level(self) -> str:
        """Power Tools Log Level"""
        value = "INFO"
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("log_level", value)

        return value

    @property
    def powertools_sample_rate(self) -> float:
        """Power Tools Sample Rate"""
        value = 0.1
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("powertools_sample_rate", value)

        return float(value)

    @property
    def powertools_log_event(self) -> bool:
        """Power Tools Log Event"""
        value = True
        if self.__config and isinstance(self.__config, dict):
            value = (
                str(self.__config.get("powertools_log_event", value)).lower() == "true"
            )

        return value

    @property
    def permissions(self) -> List[str]:
        """Permissions"""
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("permissions")
            if value:
                return value

        return []

    def arn(self, aws_region: str, aws_account_number: str, name: str) -> str:
        """
        ToDo move this to a centralized area so it's not confusing
        We are passing in the name here but we should expected it to be the transformed name
        """

        arn: str = f"arn:aws:lambda:{aws_region}:{aws_account_number}:function:{name}"

        return arn

    @property
    def layers(self) -> List[Dict[str, str]]:
        """Lambda Config"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("layers", [])

        return []

    @property
    def execution_role_arn(self) -> str | None:
        """Execution Role Arn"""
        if (
            not self.__execution_role_arn
            and self.__config
            and isinstance(self.__config, dict)
        ):
            self.__execution_role_arn = self.__config.get("execution_role_arn")

        return self.__execution_role_arn

    @execution_role_arn.setter
    def execution_role_arn(self, value: str) -> None:
        self.__execution_role_arn = value

    @property
    def execution_role_name(self) -> str | None:
        """Execution Role Name"""
        if (
            not self.__execution_role_name
            and self.__config
            and isinstance(self.__config, dict)
        ):
            self.__execution_role_name = self.__config.get("execution_role_name")

        return self.__execution_role_name

    @execution_role_name.setter
    def execution_role_name(self, value: str) -> None:
        self.__execution_role_name = value
