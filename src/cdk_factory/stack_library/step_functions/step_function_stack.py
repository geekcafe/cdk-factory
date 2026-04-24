"""
Step Functions Stack Pattern for CDK-Factory
MIT License. See Project Root for the license information.
"""

import json
import os
from typing import Dict, Any

import aws_cdk as cdk
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from aws_lambda_powertools import Logger

from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.configurations.resources.step_function import StepFunctionConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="StepFunctionStack")


@register_stack("step_function_stack")
class StepFunctionStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for AWS Step Functions state machines.
    Supports ASL definitions from file or inline, Lambda ARN resolution
    via SSM, CloudWatch logging, and STANDARD/EXPRESS types.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.sf_config: StepFunctionConfig | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.state_machine: sfn.StateMachine | None = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        sm_config = stack_config.dictionary.get("state_machine", {})
        self.sf_config = StepFunctionConfig(sm_config)

        sm_name = self.sf_config.name or "state-machine"
        stable_id = f"{deployment.workload_name}-{deployment.environment}-{sm_name}"

        # Load ASL definition
        asl_definition = self._load_definition()

        # Resolve Lambda ARN placeholders in the ASL
        resolved_definition = self._resolve_lambda_arns(asl_definition)

        # Create IAM role for the state machine
        role = self._create_execution_role(stable_id)

        # Determine state machine type
        sm_type = (
            sfn.StateMachineType.EXPRESS
            if self.sf_config.type.upper() == "EXPRESS"
            else sfn.StateMachineType.STANDARD
        )

        # Build state machine kwargs
        sm_kwargs: Dict[str, Any] = {
            "state_machine_name": deployment.build_resource_name(sm_name),
            "definition_body": sfn.DefinitionBody.from_string(
                json.dumps(resolved_definition)
            ),
            "role": role,
            "state_machine_type": sm_type,
        }

        # Configure logging if enabled
        if self.sf_config.logging:
            log_group = logs.LogGroup(
                self,
                f"{stable_id}-logs",
                removal_policy=cdk.RemovalPolicy.DESTROY,
                retention=logs.RetentionDays.ONE_MONTH,
            )
            sm_kwargs["logs"] = sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
            )

        # Create the state machine
        self.state_machine = sfn.StateMachine(self, stable_id, **sm_kwargs)

        # Export SSM parameters
        self._export_ssm_params()

    def _load_definition(self) -> dict:
        """Load ASL definition from file or inline config."""
        if self.sf_config.definition:
            return self.sf_config.definition

        if self.sf_config.definition_file:
            definition_path = self.sf_config.definition_file
            # Resolve relative paths against workload paths if available
            if not os.path.isabs(definition_path):
                if self.workload and hasattr(self.workload, "paths"):
                    for base_path in self.workload.paths:
                        candidate = os.path.join(base_path, definition_path)
                        if os.path.exists(candidate):
                            definition_path = candidate
                            break

            with open(definition_path, "r") as f:
                return json.load(f)

        raise ValueError(
            f"State machine '{self.sf_config.name}' requires either "
            f"'definition_file' or 'definition'"
        )

    def _resolve_lambda_arns(self, definition: dict) -> dict:
        """Substitute SSM-resolved Lambda ARNs into ASL JSON placeholders."""
        lambda_arns = self.sf_config.lambda_arns
        if not lambda_arns:
            return definition

        definition_str = json.dumps(definition)
        for placeholder, ssm_path in lambda_arns.items():
            resolved_arn = ssm.StringParameter.value_for_string_parameter(
                self, ssm_path
            )
            definition_str = definition_str.replace(f"${{{placeholder}}}", resolved_arn)

        return json.loads(definition_str)

    def _create_execution_role(self, stable_id: str) -> iam.Role:
        """Create IAM role with lambda:InvokeFunction for referenced Lambdas."""
        role = iam.Role(
            self,
            f"{stable_id}-role",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )

        lambda_arns = self.sf_config.lambda_arns
        if lambda_arns:
            # Grant invoke on all referenced Lambda functions
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=["*"],
                    effect=iam.Effect.ALLOW,
                )
            )

        # If logging is enabled, grant log permissions
        if self.sf_config.logging:
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogDelivery",
                        "logs:GetLogDelivery",
                        "logs:UpdateLogDelivery",
                        "logs:DeleteLogDelivery",
                        "logs:ListLogDeliveries",
                        "logs:PutResourcePolicy",
                        "logs:DescribeResourcePolicies",
                        "logs:DescribeLogGroups",
                    ],
                    resources=["*"],
                    effect=iam.Effect.ALLOW,
                )
            )

        return role

    def _export_ssm_params(self) -> None:
        """Export state machine ARN and name to SSM when configured."""
        if not self.state_machine:
            return

        ssm_config = self.sf_config.ssm
        if not ssm_config:
            return

        resource_values = {
            "state_machine_arn": self.state_machine.state_machine_arn,
            "state_machine_name": self.state_machine.state_machine_name,
        }

        namespace = self.stack_config.ssm_namespace if self.stack_config else None
        auto_export = self.stack_config.ssm_auto_export if self.stack_config else False

        if namespace and auto_export:
            prefix = f"/{namespace}"
            for export_key, export_value in resource_values.items():
                if export_value is None:
                    continue
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.node.id}-{export_key}",
                    value=export_value,
                    parameter_name=f"{prefix}/{export_key}",
                    description=f"Step Functions {export_key}",
                )
            logger.info(f"Auto-exported Step Functions parameters to SSM")
        else:
            sm_name = self.sf_config.name or "state-machine"
            self.setup_ssm_integration(
                scope=self,
                config=self.stack_config.dictionary.get("state_machine", {}),
                resource_type="step-functions",
                resource_name=sm_name,
            )
            exported_params = self.export_ssm_parameters(resource_values)
            if exported_params:
                logger.info(
                    f"Exported {len(exported_params)} Step Functions parameters to SSM"
                )
