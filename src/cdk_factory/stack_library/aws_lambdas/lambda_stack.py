import os
import json
from pathlib import Path
from typing import List


import aws_cdk

from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda

from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.constructs.lambdas.lambda_function_construct import LambdaConstruct
from cdk_factory.constructs.lambdas.lambda_function_docker_construct import (
    LambdaDockerConstruct,
)
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.stack_library.stack_base import StackStandards

from cdk_factory.constructs.sqs.policies.sqs_policies import SqsPolicies

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
    SQS as SQSConfig,
)

from cdk_factory.utilities.merge_defaults import merge_stack_defaults_into_resources

from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ssm as ssm

from cdk_factory.utilities.docker_utilities import DockerUtilities
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.interfaces.istack import IStack
from cdk_factory.configurations.resources.lambda_triggers import LambdaTriggersConfig
from cdk_factory.utilities.route_metadata_validator import RouteMetadataValidator

logger = Logger(__name__)


# currently this will support all three, I may want to bust this out
# to individual code bases (time and maintenance will tell)
# but we'll make 3 module entry points to help with the transition
@register_stack("lambda_docker_image_stack")
@register_stack("lambda_docker_file_stack")
@register_stack("lambda_code_path_stack")
@register_stack("lambda_stack")
class LambdaStack(IStack):
    """
    AWS Lambda Stack.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=w0622
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.exported_lambda_arns: dict = {}  # Store exported Lambda ARNs

        self.__nag_rule_suppressions()

        StackStandards.nag_auto_resources(scope)

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the stack"""

        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        self._sqs_decoupled_mode = stack_config.dictionary.get(
            "sqs_decoupled_mode", False
        )

        # Check for deprecated API Gateway configuration in lambda resources
        self.__check_for_deprecated_api_config(stack_config)

        resources = stack_config.dictionary.get("resources", [])
        if len(resources) == 0:
            resources = stack_config.dictionary.get("lambdas", [])
            if len(resources) == 0:
                raise ValueError("No resources found in stack config")

        # Merge stack-level defaults into each resource dict before
        # LambdaFunctionConfig instantiation so the rest of the pipeline
        # (policy generation, environment loading) sees the merged config.
        additional_permissions = stack_config.dictionary.get(
            "additional_permissions", []
        )
        additional_env_vars = stack_config.dictionary.get(
            "additional_environment_variables", []
        )
        merge_stack_defaults_into_resources(
            resources, additional_permissions, additional_env_vars
        )

        lambda_functions: List[LambdaFunctionConfig] = []
        for resource in resources:
            config = LambdaFunctionConfig(config=resource, deployment=deployment)
            lambda_functions.append(config)

        self.functions = self.__setup_lambdas(lambda_functions)

        # Export Lambda ARNs to SSM Parameter Store for API Gateway integration
        self.__export_lambda_arns_to_ssm()

        # Export route metadata to SSM for API Gateway route discovery
        self.__export_route_metadata_to_ssm()

    def __nag_rule_suppressions(self):
        pass

    def __setup_lambdas(
        self, lambda_functions: List[LambdaFunctionConfig]
    ) -> List[_lambda.Function | _lambda.DockerImageFunction]:
        """
        Setup the Lambda functions
        """

        functions: List[_lambda.Function | _lambda.DockerImageFunction] = []

        # loop through each function and create the lambda
        # we may want to move this to a general lambda setup
        for function_config in lambda_functions:
            lambda_function: _lambda.Function | _lambda.DockerImageFunction

            if function_config.docker.file:
                lambda_function = self.__setup_lambda_docker_file(
                    lambda_config=function_config
                )
            elif function_config.docker.image:
                lambda_function = self.__setup_lambda_docker_image(
                    lambda_config=function_config
                )
            else:
                lambda_function = self.__setup_lambda_code_asset(
                    lambda_config=function_config
                )

            # newer more flexible, where a function can be a consumer
            # and a producer
            if function_config.sqs.queues:
                for queue in function_config.sqs.queues:
                    if queue.is_consumer:
                        self.__trigger_lambda_by_sqs(
                            lambda_function=lambda_function,
                            sqs_config=queue,
                            function_config=function_config,
                        )
                    elif queue.is_dlq_consumer:
                        self.__bind_lambda_to_dlq_consumer(
                            lambda_function=lambda_function,
                            sqs_config=queue,
                            function_config=function_config,
                        )
                    elif queue.is_producer:
                        self.__permit_adding_message_to_sqs(
                            lambda_function=lambda_function,
                            sqs_config=queue,
                            function_config=function_config,
                        )

            if function_config.triggers:
                trigger_id: int = 0
                trigger: LambdaTriggersConfig
                for trigger in function_config.triggers:
                    trigger_id += 1
                    if trigger.resource_type.lower() == "s3":
                        self.__setup_s3_trigger(
                            trigger=trigger,
                            lambda_function=lambda_function,
                            function_name=f"{function_config.name}-{trigger_id}",
                        )

                    elif trigger.resource_type == "event-bridge":
                        self.__set_event_bridge_event(
                            trigger=trigger,
                            lambda_function=lambda_function,
                            name=f"{function_config.name}-{trigger_id}",
                        )
                    else:
                        raise ValueError(
                            f"Trigger type {trigger.resource_type} is not supported"
                        )

            if function_config.resource_policies:
                # Create the policy statement for the Lambda function's resource policy
                for rp in function_config.resource_policies:
                    if rp.get("principal") == "cloudwatch.amazonaws.com":
                        # Add the policy statement to the Lambda function's resource policy
                        lambda_function.add_permission(
                            id=self.deployment.build_resource_name(
                                f"{function_config.name}-resource-permission"
                            ),
                            principal=iam.ServicePrincipal("cloudwatch.amazonaws.com"),
                            source_arn=f"arn:aws:logs:{self.deployment.region}:{self.deployment.account}:*",
                        )
                    else:
                        raise ValueError(
                            f"A resource policy for {rp.get('principal')} has not been defined"
                        )

            # Store Lambda function for SSM export
            self.exported_lambda_arns[function_config.name] = {
                "arn": lambda_function.function_arn,
                "name": lambda_function.function_name,
                "function": lambda_function,
                "config": function_config,
            }

            functions.append(lambda_function)

        if len(functions) == 0:
            logger.warning(
                f"🚨 No Lambda Functions were created. Number of configs: {len(lambda_functions)}"
            )

        elif len(functions) != len(lambda_functions):
            logger.warning(
                f"🚨 Mismatch on number of lambdas created vs configs."
                f" Created: {functions}. "
                f"Number of configs: {len(lambda_functions)}"
            )
        else:
            print(f"👉 {len(functions)} Lambda Definition(s) Created.")

        return functions

    # TODO: move to a service
    def __set_event_bridge_event(
        self,
        trigger: LambdaTriggersConfig,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        name: str,
    ):
        if trigger.resource_type == "event-bridge":
            schedule_config = trigger.schedule

            if not schedule_config:
                raise ValueError(
                    "Invalid or missing EventBridge schedule configuration. "
                    "Expected: {'type': 'rate', 'value': '15 minutes'} "
                    "or {'rate': {'type': 'minutes', 'duration': 15}}"
                )

            # Normalize nested rate format to flat format
            # {"rate": {"type": "minutes", "duration": 15}} → {"type": "rate", "value": "15 minutes"}
            if "rate" in schedule_config and isinstance(schedule_config["rate"], dict):
                rate = schedule_config["rate"]
                duration = rate.get("duration", 0)
                unit = rate.get("type", "minutes")
                schedule_config = {"type": "rate", "value": f"{duration} {unit}"}
            elif "cron" in schedule_config and isinstance(
                schedule_config["cron"], dict
            ):
                schedule_config = {"type": "cron", "value": schedule_config["cron"]}

            if "type" not in schedule_config or "value" not in schedule_config:
                raise ValueError(
                    "Invalid or missing EventBridge schedule configuration. "
                    "Expected: {'type': 'rate', 'value': '15 minutes'} "
                    "or {'rate': {'type': 'minutes', 'duration': 15}}"
                )

            schedule_type = schedule_config["type"].lower()
            schedule_value = schedule_config["value"]

            if schedule_type == "rate":
                # Support simple duration strings like "15 minutes", "1 hour", etc.
                value_parts = schedule_value.split()
                if len(value_parts) != 2:
                    raise ValueError(
                        f"Invalid rate expression: {schedule_value} "
                        'Support simple duration strings like "15 minutes", "1 hour", etc.'
                    )

                num, unit = value_parts
                num = int(num)

                duration = {
                    "minute": aws_cdk.Duration.minutes,
                    "minutes": aws_cdk.Duration.minutes,
                    "hour": aws_cdk.Duration.hours,
                    "hours": aws_cdk.Duration.hours,
                    "day": aws_cdk.Duration.days,
                    "days": aws_cdk.Duration.days,
                }.get(unit.lower())

                if not duration:
                    raise ValueError(
                        f"Unsupported rate unit: {unit}. "
                        "Supported: minute|minutes|hour|hours|day|days"
                    )

                schedule = events.Schedule.rate(duration(num))

            elif schedule_type == "cron":
                # Provide a dict for cron like: {'minute': '0', 'hour': '18', 'day': '*', ...}
                if not isinstance(schedule_value, dict):
                    raise ValueError(
                        "Cron schedule must be a dictionary. "
                        "Provide a dict for cron like: {'minute': '0', 'hour': '18', 'day': '*', ...}"
                    )
                schedule = events.Schedule.cron(**schedule_value)

            elif schedule_type == "expression":
                # Provide a string expression: "rate(15 minutes)" or "cron(0 18 * * ? *)"
                if not isinstance(schedule_value, str):
                    raise ValueError(
                        "Expression schedule must be a string. "
                        'Provide a string expression:  \rate(15 minutes)" or "cron(0 18 * * ? *)"'
                    )
                schedule = events.Schedule.expression(schedule_value)

            else:
                raise ValueError(f"Unsupported schedule type: {schedule_type}")

            rule = events.Rule(
                self,
                id=f"{name}-event-bridge-trigger",
                schedule=schedule,
            )

            rule.add_target(aws_events_targets.LambdaFunction(lambda_function))

    def __setup_s3_trigger(
        self,
        trigger: LambdaTriggersConfig,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        function_name: str,
    ) -> None:
        """
        Set up an S3 bucket event notification trigger for a Lambda function.
        Imports an existing bucket by name (direct or SSM-resolved) and wires
        notifications with optional prefix/suffix filters.
        """
        # Resolve bucket name from direct config or SSM
        bucket_name = trigger.bucket_name
        if trigger.bucket_ssm_path:
            bucket_name = ssm.StringParameter.value_for_string_parameter(
                self, trigger.bucket_ssm_path
            )
        if not bucket_name:
            raise ValueError(
                f"S3 trigger on Lambda '{function_name}' requires either "
                "'bucket_name' or 'bucket_ssm_path'"
            )

        # Import the existing bucket
        bucket = s3.Bucket.from_bucket_name(
            self,
            id=f"{function_name}-s3-bucket",
            bucket_name=bucket_name,
        )

        # Build notification key filters (only if prefix or suffix is specified)
        has_filters = bool(trigger.prefix or trigger.suffix)
        filters = None
        if has_filters:
            filters = s3.NotificationKeyFilter(
                prefix=trigger.prefix or None,
                suffix=trigger.suffix or None,
            )

        # Map event type strings to S3 EventType enum values
        event_type_map = {
            "s3:ObjectCreated:*": s3.EventType.OBJECT_CREATED,
            "s3:ObjectCreated:Put": s3.EventType.OBJECT_CREATED_PUT,
            "s3:ObjectCreated:Post": s3.EventType.OBJECT_CREATED_POST,
            "s3:ObjectCreated:Copy": s3.EventType.OBJECT_CREATED_COPY,
            "s3:ObjectCreated:CompleteMultipartUpload": s3.EventType.OBJECT_CREATED_COMPLETE_MULTIPART_UPLOAD,
            "s3:ObjectRemoved:*": s3.EventType.OBJECT_REMOVED,
            "s3:ObjectRemoved:Delete": s3.EventType.OBJECT_REMOVED_DELETE,
            "s3:ObjectRemoved:DeleteMarkerCreated": s3.EventType.OBJECT_REMOVED_DELETE_MARKER_CREATED,
        }

        event_types = trigger.events
        destination = aws_s3_notifications.LambdaDestination(lambda_function)

        for event_str in event_types:
            s3_event = event_type_map.get(event_str)
            if not s3_event:
                raise ValueError(f"Unsupported S3 event type: '{event_str}'")
            if filters:
                bucket.add_event_notification(s3_event, destination, filters)
            else:
                bucket.add_event_notification(s3_event, destination)

        # Grant S3 permission to invoke the Lambda function
        lambda_function.add_permission(
            id=f"{function_name}-s3-invoke",
            principal=iam.ServicePrincipal("s3.amazonaws.com"),
            source_arn=bucket.bucket_arn,
        )

    def __bind_lambda_to_dlq_consumer(
        self,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        sqs_config: SQSConfig,
        function_config: LambdaFunctionConfig,
    ) -> None:
        """
        Bind a Lambda function as a consumer of an existing Dead Letter Queue.
        Resolves the queue ARN from SSM or constructs it from queue name + deployment context.
        Creates an EventSourceMapping (no queue creation) and grants consume permissions.
        """
        queue_arn: str = ""

        if sqs_config.queue_ssm_path:
            # Resolve queue ARN from SSM parameter
            queue_arn = ssm.StringParameter.value_for_string_parameter(
                self, sqs_config.queue_ssm_path
            )
        elif sqs_config.name:
            # Construct ARN from queue name + deployment context
            name = self.deployment.build_resource_name(
                sqs_config.name, ResourceTypes.SQS
            )
            queue_arn = (
                f"arn:aws:sqs:{self.deployment.region}:{self.deployment.account}:{name}"
            )
        else:
            raise ValueError(
                f"DLQ consumer on Lambda '{function_config.name}' requires either "
                "'queue_name' or 'queue_ssm_path'"
            )

        construct_id = (
            sqs_config.resource_id
            or f"{function_config.name}-{sqs_config.name or 'dlq'}-dlq-consumer"
        )

        # Import the existing DLQ by ARN
        dlq = sqs.Queue.from_queue_arn(
            self,
            id=construct_id,
            queue_arn=queue_arn,
        )

        # Create EventSourceMapping between DLQ and Lambda
        _lambda.EventSourceMapping(
            self,
            id=f"{construct_id}-esm",
            target=lambda_function,
            event_source_arn=dlq.queue_arn,
            batch_size=sqs_config.batch_size,
        )

        # Grant consume permissions
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                resources=[dlq.queue_arn],
            )
        )

    def __check_for_deprecated_api_config(self, stack_config: StackConfig) -> None:
        """No-op — the 'api' field on lambda resources is route metadata
        consumed by the API Gateway stack.  It is not deprecated."""
        pass

    def __export_lambda_arns_to_ssm(self) -> None:
        """
        Export Lambda ARNs to SSM Parameter Store for cross-stack references.
        This enables the API Gateway stack to import and integrate with these Lambdas.
        """
        if not self.exported_lambda_arns:
            logger.info("No Lambda functions to export to SSM")
            return

        # Get SSM export configuration
        ssm_config = self.stack_config.dictionary.get("ssm", {})
        if not ssm_config.get("auto_export", False):
            logger.info("SSM export is not enabled for this stack")
            return

        # Build SSM parameter prefix — requires ssm.namespace
        namespace = ssm_config.get("namespace")
        if not namespace:
            raise ValueError(
                f"Stack '{self.stack_config.name}': "
                f"'ssm.namespace' is required when 'ssm.auto_export' is true. "
                f"Add 'ssm.namespace' to your stack config."
            )

        prefix = f"/{namespace}"

        logger.info(
            f"Exporting {len(self.exported_lambda_arns)} Lambda functions to SSM under {prefix}"
        )

        for lambda_name, lambda_info in self.exported_lambda_arns.items():
            # Create SSM parameter for Lambda ARN
            param_name = f"{prefix}/{lambda_name}/arn"
            ssm.StringParameter(
                self,
                f"ssm-export-{lambda_name}-arn",
                parameter_name=param_name,
                string_value=lambda_info["arn"],
                description=f"Lambda ARN for {lambda_name}",
                tier=ssm.ParameterTier.STANDARD,
            )

            # Also export function name for convenience
            param_name_fname = f"{prefix}/{lambda_name}/function-name"
            ssm.StringParameter(
                self,
                f"ssm-export-{lambda_name}-name",
                parameter_name=param_name_fname,
                string_value=lambda_info["name"],
                description=f"Lambda function name for {lambda_name}",
                tier=ssm.ParameterTier.STANDARD,
            )

            logger.info(f"✅ Exported Lambda '{lambda_name}' to SSM: {param_name}")

            # Docker lambdas: register under ECR-keyed path for auto-discovery
            # Path: /{ecr_prefix}/ecr/{repo-name}/{lambda-name}/arn
            function_config = lambda_info.get("config")
            if function_config and (
                function_config.docker.file or function_config.docker.image
            ):
                raw_ecr_name = function_config.raw_ecr_name
                if raw_ecr_name:
                    # Derive ECR prefix from namespace: strip /lambda/... suffix
                    # e.g. "aplos-nca-saas/beta/lambda/tenants" → "aplos-nca-saas/beta"
                    ecr_prefix = self._get_ecr_prefix(namespace)

                    # Sanitize repo name for SSM path (replace / with -)
                    safe_repo = raw_ecr_name.replace("/", "-")

                    ecr_base = f"/{ecr_prefix}/ecr/{safe_repo}/{lambda_name}"

                    ssm.StringParameter(
                        self,
                        f"ssm-ecr-reg-{lambda_name}-arn",
                        parameter_name=f"{ecr_base}/arn",
                        string_value=lambda_info["arn"],
                        description=f"Docker Lambda ARN for {lambda_name} (ECR: {raw_ecr_name})",
                        tier=ssm.ParameterTier.STANDARD,
                    )

                    ssm.StringParameter(
                        self,
                        f"ssm-ecr-reg-{lambda_name}-function-name",
                        parameter_name=f"{ecr_base}/function-name",
                        string_value=lambda_info["name"],
                        description=f"Docker Lambda function name for {lambda_name}",
                        tier=ssm.ParameterTier.STANDARD,
                    )

                    logger.info(
                        f"✅ Registered Docker Lambda '{lambda_name}' at ECR path: {ecr_base}"
                    )

        print(
            f"📤 Exported {len(self.exported_lambda_arns)} Lambda function(s) to SSM Parameter Store"
        )

    @staticmethod
    def _get_ecr_prefix(namespace: str) -> str:
        """
        Derive the ECR registration prefix from the lambda stack namespace.

        Strips the /lambda/... suffix to get the workload/deployment prefix.
        e.g. "aplos-nca-saas/beta/lambda/tenants" → "aplos-nca-saas/beta"
        e.g. "aplos-nca-saas/beta/lambda" → "aplos-nca-saas/beta"
        e.g. "my-app/prod" → "my-app/prod"

        Args:
            namespace: The ssm.namespace value from the stack config

        Returns:
            The prefix to use for ECR registration paths
        """
        parts = namespace.split("/")
        # Find the "lambda" segment and take everything before it
        try:
            lambda_idx = parts.index("lambda")
            return "/".join(parts[:lambda_idx])
        except ValueError:
            # No "lambda" segment — use the full namespace
            return namespace

    def __export_route_metadata_to_ssm(self) -> None:
        """Export route metadata to SSM for API Gateway route discovery."""
        if not self.exported_lambda_arns:
            return

        ssm_config = self.stack_config.dictionary.get("ssm", {})
        if not ssm_config.get("auto_export", False):
            return

        namespace = ssm_config.get("namespace")
        if not namespace:
            raise ValueError(
                f"Stack '{self.stack_config.name}': "
                f"'ssm.namespace' is required when 'ssm.auto_export' is true. "
                f"Add 'ssm.namespace' to your stack config."
            )

        prefix = f"/{namespace}"

        exported_count = 0
        for lambda_name, lambda_info in self.exported_lambda_arns.items():
            config: LambdaFunctionConfig = lambda_info["config"]
            if not config.api or not config.api.route:
                continue

            api_dict = config.api._config
            RouteMetadataValidator.validate_route_metadata(api_dict, lambda_name)

            route_metadata = {
                "route": api_dict.get("route", ""),
                "method": api_dict.get("method", "GET"),
                "skip_authorizer": api_dict.get("skip_authorizer", False),
                "authorization_type": api_dict.get("authorization_type", ""),
                "routes": api_dict.get("routes", []),
            }

            param_path = f"{prefix}/{lambda_name}/api-route"
            ssm.StringParameter(
                self,
                f"ssm-export-{lambda_name}-api-route",
                parameter_name=param_path,
                string_value=json.dumps(route_metadata),
                description=f"API route metadata for {lambda_name}",
                tier=ssm.ParameterTier.STANDARD,
            )
            exported_count += 1
            logger.info(
                f"✅ Exported route metadata for '{lambda_name}' to SSM: {param_path}"
            )

        if exported_count > 0:
            print(f"📤 Exported {exported_count} route metadata parameter(s) to SSM")

    def __setup_lambda_docker_file(
        self, lambda_config: LambdaFunctionConfig
    ) -> _lambda.DockerImageFunction:

        tag_or_digest = lambda_config.docker.tag
        lambda_docker: LambdaDockerConstruct = LambdaDockerConstruct(
            scope=self,
            id=f"{lambda_config.name}-construct",
            deployment=self.deployment,
            workload=self.workload,
        )

        docker_image_function = lambda_docker.function(
            scope=self,
            lambda_config=lambda_config,
            deployment=self.deployment,
            tag_or_digest=tag_or_digest,
        )

        return docker_image_function

    def __setup_lambda_docker_image(
        self, lambda_config: LambdaFunctionConfig
    ) -> _lambda.DockerImageFunction:
        lambda_docker: LambdaDockerConstruct = LambdaDockerConstruct(
            scope=self,
            id=f"{lambda_config.name}-construct",
            deployment=self.deployment,
            workload=self.workload,
        )

        # Check for SSM-resolved ECR — takes precedence over explicit fields
        if lambda_config.ecr.ecr_ssm_path:
            base_path = lambda_config.ecr.ecr_ssm_path
            repo_name = ssm.StringParameter.value_for_string_parameter(
                self, f"{base_path}/name"
            )
            repo_arn = ssm.StringParameter.value_for_string_parameter(
                self, f"{base_path}/arn"
            )
        else:
            repo_arn = lambda_config.ecr.arn
            repo_name = lambda_config.ecr.name

        # TODO: techdebt
        # our current logic defaults to us-east-1 but we need to make sure the
        # ecr repo is in the same region as our lambda function
        if self.deployment.region not in repo_arn:
            logger.warning(
                {
                    "message": "The ECR Arn does not contain the correct region.  This will be autofixed for now.",
                    "repo_arn": repo_arn,
                    "region": self.deployment.region,
                }
            )
        repo_arn = repo_arn.replace("us-east-1", self.deployment.region)

        # default to the environment
        tag_or_digest: str = self.deployment.environment

        for _lambda in self.deployment.lambdas:
            if _lambda.get("name") == lambda_config.name:

                tag_or_digest = _lambda.get("tag", self.deployment.environment)
                break

        logger.info(
            {
                "action": "setup_lambda_docker_image",
                "repo_arn": repo_arn,
                "repo_name": repo_name,
                "tag_or_digest": tag_or_digest,
            }
        )
        docker_image_function = lambda_docker.function(
            scope=self,
            lambda_config=lambda_config,
            deployment=self.deployment,
            ecr_repo_name=repo_name,
            ecr_arn=repo_arn,
            # default to the environment
            tag_or_digest=tag_or_digest,
        )

        return docker_image_function

    def __setup_lambda_code_asset(
        self, lambda_config: LambdaFunctionConfig
    ) -> _lambda.Function:
        construct: LambdaConstruct = LambdaConstruct(
            scope=self,
            id=f"{lambda_config.name}-construct",
            deployment=self.deployment,
            workload=self.workload,
        )

        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        # Function recreation would cause downtime, so construct ID must be stable
        stable_lambda_id = f"{self.deployment.workload_name}-{self.deployment.environment}-lambda-{lambda_config.name}"
        construct_id = self.deployment.build_resource_name(
            lambda_config.name, resource_type=ResourceTypes.LAMBDA_FUNCTION
        )

        function = construct.create_function(
            id=stable_lambda_id,
            lambda_config=lambda_config,
        )

        return function

    def __create_sqs(self, sqs_config: SQSConfig) -> sqs.Queue:
        # todo allow for the creation of a kms key
        # but we'll also need to add the permissions to decrypt it
        #############################################
        # An error occurred (KMS.AccessDeniedException) when calling the SendMessage operation:
        # User: arn:aws:sts::<ACCOUNT>:assumed-role/<name> is not authorized
        # to perform: kms:GenerateDataKey on resource: arn:aws:kms:<REGION>:<ACCOUNT>:key/<id>
        # because no identity-based policy allows the kms:GenerateDataKey action (Service: AWSKMS;
        # Status Code: 400; Error Code: AccessDeniedException; Request ID: 48ecad9b-0360-4047-a6e0-85aea39b21d7; Proxy: null
        # kms_key = kms.Key(self, id=f"{name}-kms", enable_key_rotation=True)

        # Use stable construct IDs to prevent CloudFormation logical ID changes on pipeline rename
        # Queue recreation would cause message loss, so construct IDs must be stable
        stable_sqs_dlq_id = f"{self.deployment.workload_name}-{self.deployment.environment}-sqs-{sqs_config.name}-dlq"
        stable_sqs_reg_id = f"{self.deployment.workload_name}-{self.deployment.environment}-sqs-{sqs_config.name}"
        name_dlq = self.deployment.build_resource_name(
            f"{sqs_config.name}-dlq", ResourceTypes.SQS
        )
        name_reg = self.deployment.build_resource_name(
            f"{sqs_config.name}", ResourceTypes.SQS
        )
        dlq = None
        dlq_config = None

        if sqs_config.add_dead_letter_queue:
            dlq = sqs.Queue(
                self,
                id=stable_sqs_dlq_id,
                queue_name=name_dlq,
                # encryption=sqs.QueueEncryption.KMS,
                # encryption_master_key=kms_key,
                enforce_ssl=True,
            )

            dlq_config = sqs.DeadLetterQueue(
                max_receive_count=sqs_config.max_receive_count or 5, queue=dlq
            )
            # Add a policy to enforce HTTPS (TLS) connections for the DLQ
            result = dlq.add_to_resource_policy(SqsPolicies.get_tls_policy(dlq))
            assert result.statement_added

            # CloudWatch alarm: fires when any message lands in the DLQ
            cloudwatch.Alarm(
                self,
                id=f"{stable_sqs_dlq_id}-alarm",
                alarm_name=f"{name_dlq}-messages",
                alarm_description=(
                    f"DLQ alarm for {name_dlq}. "
                    f"Messages in this queue indicate Lambda failures "
                    f"that exhausted SQS retries."
                ),
                metric=dlq.metric_approximate_number_of_messages_visible(
                    period=aws_cdk.Duration.minutes(1),
                    statistic="Sum",
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )

        retention_period = sqs_config.message_retention_period_days
        visibility_timeout = sqs_config.visibility_timeout_seconds

        if not retention_period:
            raise RuntimeError(f"Missing retention period for SQS: {name_reg}")

        if not visibility_timeout:
            raise RuntimeError(f"Missing visibility timeout for SQS: {name_reg}")

        queue = sqs.Queue(
            self,
            id=stable_sqs_reg_id,
            queue_name=name_reg,
            retention_period=aws_cdk.Duration.days(retention_period),
            visibility_timeout=aws_cdk.Duration.seconds(visibility_timeout),
            dead_letter_queue=dlq_config,
            # encryption=sqs.QueueEncryption.KMS,
            # encryption_master_key=kms_key,
            enforce_ssl=True,
        )

        policy_result = queue.add_to_resource_policy(SqsPolicies.get_tls_policy(queue))
        assert policy_result.statement_added

        return queue

    def __get_queue(
        self,
        sqs_config: SQSConfig,
        function_config: LambdaFunctionConfig,
        binding_type: str = "ref",
    ) -> sqs.IQueue:
        name = self.deployment.build_resource_name(sqs_config.name, ResourceTypes.SQS)
        queue_arn = (
            f"arn:aws:sqs:{self.deployment.region}:{self.deployment.account}:{name}"
        )

        # Include function name, queue name, and binding type in construct ID
        # to avoid collisions when multiple lambdas reference the same queue.
        # Even if resource_id is set, we prefix with function name for uniqueness.
        base_id = sqs_config.resource_id or sqs_config.name
        construct_id = f"{function_config.name}-{base_id}-{binding_type}-ref"
        queue = sqs.Queue.from_queue_arn(
            self,
            id=construct_id,
            queue_arn=queue_arn,
        )

        return queue

    def __trigger_lambda_by_sqs(
        self,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        sqs_config: SQSConfig,
        function_config: LambdaFunctionConfig,
    ):
        # typically you have one (scalable) consumer and 1 or more producers
        # TODO: I don't think we should do this here.  It's too tightly bound to this
        # lambda and it's deployment.  It should be in a different stack and probably a different
        # pipeline.
        if self._sqs_decoupled_mode:
            queue: sqs.IQueue = self.__get_queue(
                sqs_config=sqs_config,
                function_config=function_config,
                binding_type="consumer",
            )
        else:
            queue: sqs.Queue = self.__create_sqs(sqs_config=sqs_config)

        grant = queue.grant_consume_messages(lambda_function)
        grant.assert_success()
        event_source = event_sources.SqsEventSource(
            queue,
            # Max batch size (1-10)
            batch_size=sqs_config.batch_size,
            # Max batching window in seconds range value 0 to 5 minutes
            max_batching_window=aws_cdk.Duration.seconds(
                sqs_config.max_batching_window_seconds
            ),
        )

        lambda_function.add_event_source(event_source)

        # for some reason the grant above isn't working (according cloudformation - which is failing)
        receive_policy = SqsPolicies.get_receive_policy(queue=queue)
        lambda_function.add_to_role_policy(receive_policy)
        print(f"Binding {lambda_function.function_name} to {queue.queue_name}")

    def __permit_adding_message_to_sqs(
        self,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        sqs_config: SQSConfig,
        function_config: LambdaFunctionConfig,
    ):
        # typically producers don't create the queue, the consumers do
        # so we are following a patter of 1 consumer and 1 or more producers
        # more than one lambda may be invoked to at a time as a consumer
        # but we still only have 1 blueprint or definition of the consumer
        queue: sqs.IQueue = self.__get_queue(
            sqs_config=sqs_config,
            function_config=function_config,
            binding_type="producer",
        )
        queue.grant_send_messages(lambda_function)
