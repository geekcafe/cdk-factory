import os
import json
from pathlib import Path
from typing import List


import aws_cdk

from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda

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

from aws_cdk import aws_ssm as ssm

from cdk_factory.utilities.docker_utilities import DockerUtilities
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.interfaces.istack import IStack
from cdk_factory.configurations.resources.lambda_triggers import LambdaTriggersConfig

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

        # Check for deprecated API Gateway configuration in lambda resources
        self.__check_for_deprecated_api_config(stack_config)

        resources = stack_config.dictionary.get("resources", [])
        if len(resources) == 0:
            resources = stack_config.dictionary.get("lambdas", [])
            if len(resources) == 0:
                raise ValueError("No resources found in stack config")

        lambda_functions: List[LambdaFunctionConfig] = []
        for resource in resources:
            config = LambdaFunctionConfig(config=resource, deployment=deployment)
            lambda_functions.append(config)

        self.functions = self.__setup_lambdas(lambda_functions)
        
        # Export Lambda ARNs to SSM Parameter Store for API Gateway integration
        self.__export_lambda_arns_to_ssm()

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
                        raise NotImplementedError("S3 triggers are implemented yet.")

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
            schedule_config = (
                trigger.schedule
            )  # e.g., {'type': 'rate', 'value': '15 minutes'}

            if (
                not schedule_config
                or "type" not in schedule_config
                or "value" not in schedule_config
            ):
                raise ValueError(
                    "Invalid or missing EventBridge schedule configuration. "
                    " {'type': 'rate|cron|expressions', 'value': '15 minutes'}"
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

    def __check_for_deprecated_api_config(self, stack_config: StackConfig) -> None:
        """
        Check for deprecated API Gateway configuration in lambda resources.
        Raises an error with migration guidance if found.
        """
        resources = stack_config.dictionary.get("resources", [])
        if not resources:
            resources = stack_config.dictionary.get("lambdas", [])
        
        deprecated_configs = []
        for resource in resources:
            # Check for 'api' key in resource configuration
            if "api" in resource or "api_gateway" in stack_config.dictionary:
                deprecated_configs.append(resource.get("name", "unnamed"))
        
        if deprecated_configs:
            error_msg = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ 🚨 DEPRECATED CONFIGURATION DETECTED                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

Your lambda_stack configuration includes API Gateway setup, which is now 
deprecated. This pattern caused deployment issues and violated AWS best practices.

📋 AFFECTED RESOURCES:
{chr(10).join(f"   • {name}" for name in deprecated_configs)}

🔧 REQUIRED MIGRATION (Breaking Change v2.0+):

Lambda stacks should ONLY create Lambda functions. API Gateway integration 
should be handled in a separate api_gateway_stack.

NEW PATTERN:
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Lambda Stack (lambda_stack)                                              │
│    • Creates Lambda functions                                               │
│    • Exports Lambda ARNs to SSM Parameter Store                             │
│    • NO API Gateway configuration                                           │
│                                                                              │
│ 2. API Gateway Stack (api_gateway_stack)                                    │
│    • Imports Lambda ARNs from SSM                                           │
│    • Creates API Gateway                                                    │
│    • Wires Lambda integrations                                              │
│    • Manages stages, deployments, and domains                               │
└─────────────────────────────────────────────────────────────────────────────┘

📚 MIGRATION GUIDE:
https://github.com/geek-cafe/cdk-factory/blob/main/docs/MIGRATION_V2.md

💡 QUICK FIX:
1. Remove 'api' configuration from lambda resources
2. Remove 'api_gateway' from stack config  
3. Create new api_gateway_stack configuration
4. Update pipeline: lambdas deploy first, then api_gateway

❓ NEED HELP?
See examples: cdk-factory/examples/separate-api-gateway/

════════════════════════════════════════════════════════════════════════════════
"""
            raise ValueError(error_msg)

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
        if not ssm_config.get("enabled", False):
            logger.info("SSM export is not enabled for this stack")
            return
        
        # Build SSM parameter prefix
        # Try 'workload' first, fall back to 'organization' for backward compatibility
        workload = ssm_config.get("workload", ssm_config.get("organization", self.deployment.workload_name))
        environment = ssm_config.get("environment", self.deployment.environment)
        prefix = f"/{workload}/{environment}/lambda"
        
        logger.info(f"Exporting {len(self.exported_lambda_arns)} Lambda functions to SSM under {prefix}")
        
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
        
        print(f"📤 Exported {len(self.exported_lambda_arns)} Lambda function(s) to SSM Parameter Store")

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
        )
        repo_arn = lambda_config.ecr.arn
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
        repo_name = lambda_config.ecr.name

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

            dlq_config = sqs.DeadLetterQueue(max_receive_count=5, queue=dlq)
            # Add a policy to enforce HTTPS (TLS) connections for the DLQ
            result = dlq.add_to_resource_policy(SqsPolicies.get_tls_policy(dlq))
            assert result.statement_added

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
        self, sqs_config: SQSConfig, function_config: LambdaFunctionConfig
    ) -> sqs.IQueue:
        name = self.deployment.build_resource_name(sqs_config.name, ResourceTypes.SQS)
        queue_arn = (
            f"arn:aws:sqs:{self.deployment.region}:{self.deployment.account}:{name}"
        )

        # if an id was provided in the settings use that one, otherwise build an id
        construct_id = (
            sqs_config.resource_id
            or f"{self.deployment.build_resource_name(function_config.name)}-{sqs_config.name}-sqs-arn"
        )
        queue = sqs.Queue.from_queue_arn(
            self,
            id=f"{construct_id}",
            queue_arn=queue_arn,
        )

        return queue

    def __trigger_lambda_by_sqs(
        self,
        lambda_function: _lambda.Function | _lambda.DockerImageFunction,
        sqs_config: SQSConfig,
    ):
        # typically you have one (scalable) consumer and 1 or more producers
        # TODO: I don't think we should do this here.  It's too tightly bound to this
        # lambda and it's deployment.  It should be in a different stack and probably a different
        # pipeline.
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
            sqs_config=sqs_config, function_config=function_config
        )
        queue.grant_send_messages(lambda_function)
