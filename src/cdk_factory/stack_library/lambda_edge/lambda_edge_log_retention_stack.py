"""
Lambda@Edge Log Retention Stack Pattern for CDK-Factory
Creates a scheduled EventBridge rule that invokes a Lambda to set log
retention on Lambda@Edge log groups created in edge regions.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Optional, Dict, Any
from pathlib import Path
import json

import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig
from cdk_factory.utilities.lambda_function_utilities import LambdaFunctionUtilities
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig

logger = Logger(service="LambdaEdgeLogRetentionStack")


@register_stack("lambda_edge_log_retention_library_module")
@register_stack("lambda_edge_log_retention_stack")
class LambdaEdgeLogRetentionStack(IStack, StandardizedSsmMixin):
    """Creates a scheduled Lambda that enforces log retention for Lambda@Edge logs."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:  # pylint: disable=redefined-builtin
        super().__init__(scope, id, **kwargs)
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.function: Optional[_lambda.Function] = None
        self.rule: Optional[events.Rule] = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        cfg = self._get_config(stack_config)

        # 1) Create function (stable construct id)
        self.function = self._create_lambda_function(cfg)

        # 2) Permissions needed by function
        self._attach_permissions(self.function)

        # 3) Create EventBridge rule/schedule to invoke the function
        self.rule = self._create_schedule_rule(cfg, self.function)

        # 4) Export SSM parameters if configured
        self._add_outputs(cfg)

    # ------------------ helpers ------------------
    def _stable_id(self, base: str) -> str:
        """Return a deterministic construct ID independent of pipeline names."""
        return f"{self.deployment.workload_name}-{self.deployment.environment}-{base}"

    def _get_config(self, stack_config: StackConfig) -> Dict[str, Any]:
        """
        Read configuration for this stack.
        
        The code_path and handler are OPTIONAL - they default to the internal
        library function. Users only need to specify them if using a custom implementation.
        
        Expected structure under key 'log_retention':
        {
          "name": "edge-log-retention",                    # Optional
          "description": "...",                            # Optional
          "code_path": "path/to/custom/handler",          # Optional - defaults to internal library function
          "handler": "custom.handler",                     # Optional - defaults to app.lambda_handler
          "runtime": "python3.12",                         # Optional
          "schedule": { "type": "expression", "value": "rate(1 day)" },  # Optional
          "enable": true,                                  # Optional
          "detail": { "days": 7, "dry_run": true },       # Optional
          "ssm": { "exports": {...} }                      # Optional
        }
        """
        d = stack_config.dictionary or {}
        cfg = d.get("log_retention", {}) or {}

        # Get the absolute path to the internal library function
        # This resolves to the installed cdk_factory package location
        import importlib.resources
        try:
            # Python 3.9+
            cdk_factory_root = importlib.resources.files("cdk_factory")
            internal_function_path = str(cdk_factory_root / "stack_library" / "lambda_edge" / "functions" / "log_retention_manager")
        except AttributeError:
            # Fallback for older Python
            import pkg_resources
            cdk_factory_root = pkg_resources.resource_filename("cdk_factory", "")
            internal_function_path = str(Path(cdk_factory_root) / "stack_library" / "lambda_edge" / "functions" / "log_retention_manager")

        # Defaults - use internal library function
        defaults = {
            "name": "edge-log-retention",
            "description": "Manage Lambda@Edge log group retention across regions",
            "code_path": internal_function_path,  # Internal library function
            "handler": "app.lambda_handler",
            "runtime": "python3.12",
            "schedule": {"type": "expression", "value": "rate(1 day)"},
            "enable": True,
            "detail": {"days": 7, "dry_run": True},
            "ssm": {
                "exports": {
                    "function_arn": f"/{self.deployment.environment}/{self.deployment.workload_name}/lambda-edge/log-retention/function-arn",
                    "rule_arn": f"/{self.deployment.environment}/{self.deployment.workload_name}/lambda-edge/log-retention/rule-arn",
                }
            },
        }

        # Merge defaults with provided config
        out = {**defaults, **cfg}
        # Ensure nested merges for 'schedule', 'detail', 'ssm.exports'
        out["schedule"] = {**defaults["schedule"], **cfg.get("schedule", {})}
        out["detail"] = {**defaults["detail"], **cfg.get("detail", {})}
        ssm_cfg = cfg.get("ssm", {}).get("exports", {})
        out.setdefault("ssm", {}).setdefault("exports", {})
        out["ssm"]["exports"].update({**defaults["ssm"]["exports"], **ssm_cfg})
        return out

    def _create_lambda_function(self, cfg: Dict[str, Any]) -> _lambda.Function:
        """Create the log retention manager Lambda using the shared utilities."""
        lambda_name = cfg["name"]
        # Build a LambdaFunctionConfig compatible dict
        lambda_dict = {
            "name": lambda_name,
            # Path should be folder containing app.py
            "src": cfg["code_path"],
            "handler": cfg["handler"],
            "description": cfg.get("description", ""),
            "runtime": cfg.get("runtime", "python3.12"),
            # Keep function name generation controlled by our stable construct id
            "auto_name": False,
            # Short runtime; this Lambda scans regions and updates policies
            "timeout": 300,
            # Keep memory modest; adjust via config if needed
            "memory_size": 256,
            # Use powertools layer by default
            "include_power_tools_layer": True,
            # Dependencies installed directly
            "dependencies_to_layer": False,
        }

        function_config = LambdaFunctionConfig(config=lambda_dict, deployment=self.deployment)
        utilities = LambdaFunctionUtilities(deployment=self.deployment, workload=self.workload)

        # Stable Construct ID so CFN logical IDs won't change with pipeline names
        function_id = self._stable_id(f"lambda-{lambda_name}")

        fn = utilities.create(
            scope=self,
            id=function_id,
            lambda_config=function_config,
        )

        # Add tags
        cdk.Tags.of(fn).add("ManagedBy", "CDK-Factory")
        cdk.Tags.of(fn).add("Purpose", "LambdaEdgeLogRetention")
        return fn

    def _attach_permissions(self, fn: _lambda.Function) -> None:
        """Grant permissions required to enumerate regions and set log retention."""
        # CloudWatch Logs across regions
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:DescribeLogGroups",
                    "logs:PutRetentionPolicy",
                ],
                resources=["*"]
            )
        )
        # Describe regions
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ec2:DescribeRegions"],
                resources=["*"]
            )
        )

    def _create_schedule_rule(self, cfg: Dict[str, Any], fn: _lambda.Function) -> events.Rule:
        """Create EventBridge Rule to invoke the Lambda on a schedule."""
        schedule_cfg = cfg.get("schedule", {})
        schedule_type = str(schedule_cfg.get("type", "expression")).lower()
        schedule_value = schedule_cfg.get("value", "rate(1 day)")

        if schedule_type == "rate":
            # Allow human-readable like "15 minutes", "1 hour"
            parts = str(schedule_value).split()
            if len(parts) == 2 and parts[0].isdigit():
                n, unit = int(parts[0]), parts[1].lower()
                duration = {
                    "minute": cdk.Duration.minutes,
                    "minutes": cdk.Duration.minutes,
                    "hour": cdk.Duration.hours,
                    "hours": cdk.Duration.hours,
                    "day": cdk.Duration.days,
                    "days": cdk.Duration.days,
                }.get(unit)
                if not duration:
                    raise ValueError(f"Unsupported rate unit: {unit}")
                schedule = events.Schedule.rate(duration(n))
            else:
                # Fallback to expression
                schedule = events.Schedule.expression(f"rate({schedule_value})")
        elif schedule_type == "cron":
            if not isinstance(schedule_value, dict):
                raise ValueError("Cron schedule must be a dict of cron fields")
            schedule = events.Schedule.cron(**schedule_value)
        else:
            # expression like "rate(1 day)" or full cron()
            schedule = events.Schedule.expression(str(schedule_value))

        rule_id = self._stable_id("rule-edge-log-retention")
        rule = events.Rule(
            self,
            id=rule_id,
            schedule=schedule,
            enabled=bool(cfg.get("enable", True)),
        )

        # Ensure the Lambda permission for EventBridge
        fn.add_permission(
            id=f"{rule_id}-invokePermission",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=rule.rule_arn,
        )

        # Pass detail wrapper to match lambda handler expectations
        detail = cfg.get("detail", {"days": 7, "dry_run": True})
        input_payload = {"detail": detail}
        rule.add_target(
            events_targets.LambdaFunction(
                fn,
                event=events.RuleTargetInput.from_object(input_payload),
            )
        )
        return rule

    def _add_outputs(self, cfg: Dict[str, Any]) -> None:
        """Export useful parameters to SSM if configured."""
        ssm_exports = (cfg.get("ssm") or {}).get("exports") or {}
        if not ssm_exports:
            return

        mapping = {
            "function_arn": self.function.function_arn if self.function else "",
            "rule_arn": self.rule.rule_arn if self.rule else "",
        }

        for key, param_path in ssm_exports.items():
            value = mapping.get(key)
            if not value:
                continue
            self.export_ssm_parameter(
                self,
                id=f"{self._stable_id('log-retention')}-{key}",
                value=value,
                parameter_name=param_path,
                description=f"{key} for Lambda@Edge log retention manager",
            )