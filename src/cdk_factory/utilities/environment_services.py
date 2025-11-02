"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from datetime import datetime, UTC
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from cdk_factory.configurations.resources.resource_types import (
    ResourceTypes,
)
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.interfaces.live_ssm_resolver import LiveSsmResolver
from aws_lambda_powertools import Logger

logger = Logger(__name__)


class EnvironmentVariables:
    """
    Easy access to allow the environment variables we use in the application.
    It's a best practice to use this vs doing and os.getenv in each application.
    This helps us track all the environment variables in use
    """

    @staticmethod
    def get_aws_region():
        """
        gets the aws region from an environment var
        """
        value = os.getenv("AWS_REGION")
        return value

    @staticmethod
    def get_aws_profile():
        """
        Get the aws profile used for cli/boto3 commands
        This should only be set with temporty creds and only for development purposes
        """
        value = os.getenv("AWS_PROFILE")
        return value

    @staticmethod
    def get_aws_account_id():
        """
        gets the aws account id from an environment var
        """
        value = os.getenv("AWS_ACCOUNT_ID")
        return value

    @staticmethod
    def get_app_domain():
        """
        gets the app domian name from an environment var
        """
        value = os.getenv("APP_DOMAIN")
        return value

    @staticmethod
    def get_ses_user_name():
        """
        gets the ses user-name from an environment var
        """
        value = os.getenv("SES_USER_NAME")
        return value

    @staticmethod
    def get_ses_password():
        """
        gets the ses password from an environment var
        """
        value = os.getenv("SES_PASSWORD")
        return value

    @staticmethod
    def get_ses_endpoint():
        """
        gets the ses endpoint from an environment var
        """
        value = os.getenv("SES_END_POINT")
        return value

    @staticmethod
    def get_cognito_user_pool():
        """
        gets the cognito user pool from an environment var
        """
        value = os.getenv("COGNITO_USER_POOL")
        return value

    @staticmethod
    def get_cognito_user_pools():
        """
        gets the cognito user pool from an environment var
        """
        value = os.getenv("COGNITO")
        return value

    @staticmethod
    def get_dynamodb_table_name():
        """
        gets the dynamodb table name from an environment var
        """
        value = os.getenv("DYNAMODB_SINGLE_TABLE_NAME")
        return value

    @staticmethod
    def get_lambda_function_to_invoke():
        """
        gets the lambda function to invoke from an environment var
        this is used by sync to asycn lambda invocation, or by the queue
        """
        value = os.getenv("LAMBDA_FUNCTION_TO_INVOKE")
        return value

    @staticmethod
    def get_amazon_trace_id():
        """
        gets the amazon trace id from an environment var
        """
        value = os.getenv("_X_AMZN_TRACE_ID", "NA")
        return value

    @staticmethod
    def get_integration_tests_setting() -> bool:
        """
        determine if integration tests are run from an environment var
        """
        value = str(os.getenv("RUN_INTEGRATION_TESTS", "False")).lower() == "true"
        env = EnvironmentVariables.get_environment_setting()

        if env.lower().startswith("prod"):
            value = False

        return value

    @staticmethod
    def get_environment_setting() -> str:
        """
        gets the environment name from an environment var
        """
        value = os.getenv("ENVIRONMENT")

        if not value:
            logger.warning(
                "ENVIRONMENT var is not set. A future version will throw an error."
            )
            return ""

        return value


class EnvironmentServices:
    """
    This class is a collection of services that are used in the application
    """

    @staticmethod
    def load_environment_variables(
        environment: dict | None,
        *,
        deployment: Deployment,
        lambda_config: LambdaFunctionConfig,
        scope: Construct,
    ) -> dict | None:
        """Loads environment variables"""
        if not environment:
            environment = {}
        # more verbose
        environment["WORKLOAD_NAME"] = deployment.workload.get("name", "NA")
        environment["ENVIRONMENT_NAME"] = deployment.workload.get("environment", deployment.environment)
        environment["DEPLOYMENT_NAME"] = deployment.name
        environment["ENVIRONMENT"] = deployment.workload.get("environment", deployment.environment)
        environment["PIPELINE"] = deployment.pipeline.get("name", "NA")
        environment["ACCOUNT"] = deployment.account
        environment["DEPLOYMENT"] = deployment.name
        environment["POWERTOOLS_LOGGER_LOG_EVENT"] = str(
            lambda_config.powertools_log_event
        )
        environment["POWERTOOLS_LOGGER_SAMPLE_RATE"] = str(
            lambda_config.powertools_sample_rate
        )
        environment["POWERTOOLS_SERVICE_NAME"] = deployment.workload.get(
            "name", "workload"
        )
        environment["LOG_LEVEL"] = lambda_config.log_level
        environment["DEPLOYMENT_DATE"] = f"{datetime.now(UTC)}-UTC"

        if lambda_config.environment_variables is None:
            return environment
        
        # Initialize live SSM resolver if configuration supports it
        live_resolver = None
        if hasattr(lambda_config, 'ssm') and lambda_config.ssm:
            try:
                # Convert lambda config to dict format for LiveSsmResolver
                ssm_config = lambda_config.ssm if isinstance(lambda_config.ssm, dict) else lambda_config.ssm.__dict__
                live_resolver = LiveSsmResolver({"ssm": ssm_config})
                if live_resolver.enabled:
                    logger.info("Live SSM resolution enabled for Lambda environment variables")
            except Exception as e:
                logger.warning(f"Failed to initialize live SSM resolver: {e}")
        
        # load the other environment vars
        for item in lambda_config.environment_variables:
            name = item["name"]
            value = item.get("value")
            if not value:
                if "ssm_parameter" in item:
                    ssm_parameter_path = item["ssm_parameter"]
                    
                    # Get CDK token value first
                    cdk_token_value = ssm.StringParameter.value_for_string_parameter(
                        scope=scope,
                        parameter_name=ssm_parameter_path,
                    )
                    
                    # Try live resolution if available and appropriate
                    if live_resolver and live_resolver.should_use_live_resolution(cdk_token_value):
                        live_value = live_resolver.resolve_parameter(
                            ssm_parameter_path, 
                            fallback_value=None
                        )
                        if live_value:
                            logger.info(f"Live resolved environment variable {name} from {ssm_parameter_path}")
                            value = live_value
                        else:
                            logger.warning(f"Live resolution failed for {name}, using CDK token")
                            value = cdk_token_value
                    else:
                        value = cdk_token_value
                        
                elif "fallback_value" in item:
                    value = item["fallback_value"]
                    
                if not value:
                    logger.warning(
                        f"Environment variable {name} is not set. A future version will throw an error."
                    )
                    continue
            # set the value
            environment[name] = value

        return environment

    @staticmethod
    def generate_dynamic_mapping(
        deployment: Deployment, key_name: str, key_value: str
    ) -> str:
        if str(key_name).startswith("SQS_"):
            sqs_name = deployment.build_resource_name(key_value, ResourceTypes.SQS)
            url = (
                "https://sqs"
                f".{deployment.region}.amazonaws.com/{deployment.account}/{sqs_name}"
            )
            key_value = url
            return key_value
        else:
            logger.warning(f"unknown mapping for {key_name}")
            raise ValueError(f"unknown environment variable mapping for {key_name}")

    @staticmethod
    def get_user_pool_ids(
        deployment: Deployment,
        scope: Construct,
    ) -> str | None:
        """
        Get a list of defined user pools

        Returns:
            Token Strings - these are just tokens at this point - not actual values
        """
        # TODO: needs refactoring
        # user_pool_id = ssm.StringParameter.value_for_string_parameter(
        #     scope=scope,
        #     parameter_name=deployment.ssm_parameter_for_cognito_user_pool_id,
        # )
        # admin_user_pool_id = ssm.StringParameter.value_for_string_parameter(
        #     scope=scope,
        #     parameter_name=deployment.ssm_parameter_for_cognito_admin_user_pool_id,
        # )
        # user_pools: str = f"{user_pool_id},{admin_user_pool_id}"

        # return user_pools
        return None
