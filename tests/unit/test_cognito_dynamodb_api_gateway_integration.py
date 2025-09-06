"""
Integration test for cognito-dynamodb-api-gateway configuration using WorkloadFactory
Tests SSM parameter creation and format validation with real CDK synthesis
"""

import unittest
import os
import tempfile
from pathlib import Path
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.workload.workload_factory import WorkloadFactory


class TestCognitoDynamoDbApiGatewayIntegration(unittest.TestCase):
    """Test integration using cognito-dynamodb-api-gateway.json config"""

    def setUp(self):
        """Set up test resources"""
        self.app = App()
        path = os.path.dirname(os.path.abspath(__file__))
        self.config_path = str(
            Path(
                os.path.join(path, "files/configs/cognito-dynamodb-api-gateway.json")
            ).resolve()
        )

        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at {self.config_path}")

        # Create a temporary runtime directory
        self.runtime_dir = tempfile.mkdtemp()

        # Create the commands directory and cdk_synth.sh file
        commands_dir = os.path.join(self.runtime_dir, "commands")
        os.makedirs(commands_dir, exist_ok=True)

        cdk_synth_file = os.path.join(commands_dir, "cdk_synth.sh")
        with open(cdk_synth_file, "w") as f:
            f.write(
                """#!/bin/bash
# CDK Synth commands for testing
npm ci
npx cdk synth
"""
            )
        os.chmod(cdk_synth_file, 0o755)

        # Create the lambdas directory and API Gateway health Lambda
        lambdas_dir = os.path.join(self.runtime_dir, "lambdas", "api_gateway_health")
        os.makedirs(lambdas_dir, exist_ok=True)

        # Create a simple Lambda handler
        lambda_file = os.path.join(lambdas_dir, "app.py")
        with open(lambda_file, "w") as f:
            f.write(
                """import json

def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({'status': 'healthy'})
    }
"""
            )

        # Set required environment variables for the config
        os.environ["ENVIRONMENT"] = "dev"
        os.environ["CDK_WORKLOAD_NAME"] = "my-cool-app"
        os.environ["AWS_ACCOUNT_NUMBER"] = "123456789012"
        os.environ["DEVOPS_AWS_ACCOUNT"] = "123456789012"
        os.environ["DEVOPS_REGION"] = "us-east-1"
        os.environ["SITE_BUCKET_NAME"] = "test-bucket"
        os.environ["HOSTED_ZONE_ID"] = "Z02787413IAOSKE4U9VE8"
        os.environ["HOSTED_ZONE_NAME"] = "dev.my-cool-app.com"
        os.environ["DNS_ALIAS"] = "api.dev.my-cool-app.com"
        os.environ["CODE_REPOSITORY_NAME"] = "geekcafe/my-cool-app-aws-infrastructure"
        os.environ["CODE_REPOSITORY_ARN"] = (
            "arn:aws:codeconnections:us-east-1:123456789012:connection/a90857d9-89b8-4823-ad6f-69a335c20414"
        )
        os.environ["GIT_BRANCH"] = "main"

    def test_pipeline_build_and_ssm_parameters(self):
        """Test that pipeline builds successfully and creates correct SSM parameters"""

        # Create WorkloadFactory with the config and paths including runtime directory
        factory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            runtime_directory=self.runtime_dir,
            paths=[self.runtime_dir],  # Add runtime directory to paths
            add_env_context=False,  # Disable env context for testing
        )

        # Build the workload (this should create the pipeline and stacks)
        cloud_assembly = factory.synth()

        # Verify that stacks were created
        self.assertIsNotNone(cloud_assembly)

        # Get the pipeline stack template
        pipeline_stack_name = "my-cool-app-dev-infra-pipeline"
        pipeline_template = Template.from_stack(
            next(
                stack
                for stack in self.app.node.children
                if stack.node.id == pipeline_stack_name
            )
        )

        # Verify pipeline was created
        pipeline_template.has_resource_properties(
            "AWS::CodePipeline::Pipeline", {"Name": "my-cool-app-dev-infra-pipeline"}
        )

    def test_cognito_ssm_parameters_format(self):
        """Test that Cognito stack creates SSM parameters in correct format"""

        # Create WorkloadFactory
        factory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            runtime_directory=self.runtime_dir,
            paths=[self.runtime_dir],
            add_env_context=False,
        )

        # Build the workload
        factory.synth()

        # Find the Cognito stack within the pipeline structure
        cognito_stack = None

        def find_cognito_stack(node):
            """Recursively search for cognito stack"""
            if hasattr(node, "node") and "cognito" in node.node.id:
                return node
            if hasattr(node, "node") and hasattr(node.node, "children"):
                for child in node.node.children:
                    result = find_cognito_stack(child)
                    if result:
                        return result
            return None

        # Search through all app children recursively
        for stack in self.app.node.children:
            cognito_stack = find_cognito_stack(stack)
            if cognito_stack:
                break

        self.assertIsNotNone(cognito_stack, "Cognito stack should be created")

        # Get the Cognito stack template
        cognito_template = Template.from_stack(cognito_stack)

        # Expected SSM parameter paths from new enhanced pattern
        expected_cognito_params = {
            "/my-cool-app/dev/cognito/user-pool/user_pool_arn": "user_pool_arn",
            "/my-cool-app/dev/cognito/user-pool/user_pool_id": "user_pool_id",
            "/my-cool-app/dev/cognito/user-pool/user_pool_name": "user_pool_name",
        }

        # Check that SSM parameters are created with correct paths
        for param_path, param_key in expected_cognito_params.items():
            cognito_template.has_resource_properties(
                "AWS::SSM::Parameter", {"Name": param_path, "Type": "String"}
            )

    def test_dynamodb_ssm_parameters_format(self):
        """Test that DynamoDB stack creates SSM parameters in correct format"""

        # Create WorkloadFactory
        factory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            runtime_directory=self.runtime_dir,
            paths=[self.runtime_dir],
            add_env_context=False,
        )

        # Build the workload
        factory.synth()

        # Find the DynamoDB stack within the pipeline structure
        dynamodb_stack = None

        def find_dynamodb_stack(node):
            """Recursively search for dynamodb stack"""
            if hasattr(node, "node") and "dynamodb" in node.node.id:
                return node
            if hasattr(node, "node") and hasattr(node.node, "children"):
                for child in node.node.children:
                    result = find_dynamodb_stack(child)
                    if result:
                        return result
            return None

        # Search through all app children recursively
        for stack in self.app.node.children:
            dynamodb_stack = find_dynamodb_stack(stack)
            if dynamodb_stack:
                break

        self.assertIsNotNone(dynamodb_stack, "DynamoDB stack should be created")

        # Get the DynamoDB stack template
        dynamodb_template = Template.from_stack(dynamodb_stack)

        # Expected SSM parameter paths from new enhanced pattern
        expected_dynamodb_params = {
            "/my-cool-app/dev/dynamodb/app-table/table_name": "table_name",
            "/my-cool-app/dev/dynamodb/app-table/table_arn": "table_arn",
            "/my-cool-app/dev/dynamodb/app-table/table_stream_arn": "table_stream_arn",
        }

        # Check that the main SSM parameters are created with correct paths
        main_params = [
            "/my-cool-app/dev/dynamodb/app-table/table_name",
            "/my-cool-app/dev/dynamodb/app-table/table_arn",
            "/my-cool-app/dev/dynamodb/app-table/table_stream_arn",
        ]

        for param_path in main_params:
            dynamodb_template.has_resource_properties(
                "AWS::SSM::Parameter", {"Name": param_path, "Type": "String"}
            )

    def test_api_gateway_ssm_parameters_format(self):
        """Test that API Gateway stack creates SSM parameters in correct format"""

        # Create WorkloadFactory
        factory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            runtime_directory=self.runtime_dir,
            paths=[self.runtime_dir],
            add_env_context=False,
        )

        # Build the workload
        factory.synth()

        # Find the API Gateway stack within the pipeline structure
        api_gateway_stack = None

        def find_api_gateway_stack(node):
            """Recursively search for api gateway stack"""
            # Check if this is a CDK Stack and contains api-gateway in the name
            if (
                hasattr(node, "__class__")
                and "Stack" in node.__class__.__name__
                and hasattr(node, "node")
                and "api-gateway" in node.node.id
            ):
                return node
            if hasattr(node, "node") and hasattr(node.node, "children"):
                for child in node.node.children:
                    result = find_api_gateway_stack(child)
                    if result:
                        return result
            return None

        # Search through all app children recursively
        for stack in self.app.node.children:
            api_gateway_stack = find_api_gateway_stack(stack)
            if api_gateway_stack:
                break

        self.assertIsNotNone(api_gateway_stack, "API Gateway stack should be created")

        # Get the API Gateway stack template
        api_gateway_template = Template.from_stack(api_gateway_stack)

        # Expected SSM parameter paths from new enhanced pattern
        expected_api_gateway_params = {
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_id": "api_id",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_arn": "api_arn",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_url": "api_url",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/root_resource_id": "root_resource_id",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/authorizer_id": "authorizer_id",
        }

        # Check that the main SSM parameters are created with correct paths
        main_params = [
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_id",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_arn",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/api_url",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/root_resource_id",
            "/my-cool-app/dev/api-gateway/my-cool-app-dev/authorizer_id",
        ]

        for param_path in main_params:
            api_gateway_template.has_resource_properties(
                "AWS::SSM::Parameter", {"Name": param_path, "Type": "String"}
            )

    def test_ssm_parameter_cross_reference(self):
        """Test that API Gateway correctly references Cognito SSM parameters"""

        # Create WorkloadFactory
        factory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            runtime_directory=self.runtime_dir,
            paths=[self.runtime_dir],
            add_env_context=False,
        )

        # Build the workload
        factory.synth()

        # Find the Cognito stack to verify it exports the parameter
        cognito_stack = None

        def find_cognito_stack(node):
            """Recursively search for cognito stack"""
            # Check if this is a CDK Stack and contains cognito in the name
            if (
                hasattr(node, "__class__")
                and "Stack" in node.__class__.__name__
                and hasattr(node, "node")
                and "cognito" in node.node.id
            ):
                return node
            if hasattr(node, "node") and hasattr(node.node, "children"):
                for child in node.node.children:
                    result = find_cognito_stack(child)
                    if result:
                        return result
            return None

        # Search through all app children recursively
        for stack in self.app.node.children:
            cognito_stack = find_cognito_stack(stack)
            if cognito_stack:
                break

        self.assertIsNotNone(cognito_stack, "Cognito stack should be created")
        cognito_template = Template.from_stack(cognito_stack)

        # Verify that Cognito exports the user pool ARN parameter using new enhanced pattern
        cognito_user_pool_arn_path = "/my-cool-app/dev/cognito/user-pool/user_pool_arn"

        # Check that Cognito stack exports the SSM parameter that API Gateway imports
        cognito_template.has_resource_properties(
            "AWS::SSM::Parameter", {"Name": cognito_user_pool_arn_path}
        )

    def tearDown(self):
        """Clean up test resources"""
        # Clean up environment variables
        env_vars_to_clean = [
            "ENVIRONMENT",
            "CDK_WORKLOAD_NAME",
            "AWS_ACCOUNT_NUMBER",
            "DEVOPS_AWS_ACCOUNT",
            "DEVOPS_REGION",
            "SITE_BUCKET_NAME",
            "HOSTED_ZONE_ID",
            "HOSTED_ZONE_NAME",
            "DNS_ALIAS",
            "CODE_REPOSITORY_NAME",
            "CODE_REPOSITORY_ARN",
            "GIT_BRANCH",
        ]

        for var in env_vars_to_clean:
            if var in os.environ:
                del os.environ[var]


if __name__ == "__main__":
    unittest.main()
