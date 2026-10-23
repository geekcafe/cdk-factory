"""
Credential-free synth tests for the codepipeline_monitor stack (FEAT-001).

Mirrors test_appsync_events_stack.py / test_lambda_sqs_trigger_consume_grant.py
via aws_cdk.assertions.Template with a hermetic WorkloadConfig (the "devops"
section is required or WorkloadConfig sys.exit(1)s on a clean env).

Asserts (per DESIGN §4.6):
  (1)  mode all, no exclude_names -> exactly one AWS::Events::Rule, source
       ['aws.codepipeline'], default detail-type, detail.state ['FAILED'], NO
       detail.pipeline key.
  (1b) mode all + exclude_names -> detail.pipeline == [{'anything-but': [...]}].
  (2)  mode selected (2 names) -> detail.pipeline == those names.
  (3)  mode none / enabled:false -> zero AWS::Events::Rule.
  (4)  rule Targets[0].Arn is the imported ARN token (a Ref to the SSM
       CfnParameter).
  (5)  AWS::Lambda::Permission Action=lambda:InvokeFunction,
       Principal=events.amazonaws.com, SourceArn = the rule ARN token (not '*').
  (6)  codebuild.enabled -> extra rule source ['aws.codebuild'], detail-type
       ['CodeBuild Build State Change'], detail.build-status ['FAILED'].
  (7)  missing adapter_lambda_arn_ssm_path -> ValueError at synth.

All credential-free (no AWS creds required).
"""

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.codepipeline_monitor.codepipeline_monitor_stack import (
    CodePipelineMonitorStack,
)
from cdk_factory.workload.workload_factory import WorkloadConfig


WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"
ADAPTER_ARN_SSM_PATH = "/myapp/dev/lambda/myapp-dev-codepipeline-adapter/arn"
STACK_NAME = "codepipeline-monitor"


def _build_template(stack_cfg: dict) -> Template:
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    stack_config = StackConfig(stack_cfg, workload=wl.dictionary)
    deployment = DeploymentConfig(
        workload=wl.dictionary,
        deployment={
            "name": ENV,
            "environment": ENV,
            "account": ACCOUNT,
            "region": REGION,
        },
    )

    app = App()
    stack = CodePipelineMonitorStack(
        app, "CodePipelineMonitor", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def _stack_cfg(monitor: dict, enabled: bool = True) -> dict:
    cfg = {
        "name": STACK_NAME,
        "module": "codepipeline_monitor_stack",
        "codepipeline_monitor": monitor,
    }
    if enabled is not None:
        cfg["enabled"] = enabled
    return cfg


def _codepipeline_rules(template: Template) -> list:
    rules = template.find_resources("AWS::Events::Rule")
    out = []
    for rule in rules.values():
        pattern = rule["Properties"]["EventPattern"]
        if pattern.get("source") == ["aws.codepipeline"]:
            out.append(rule)
    return out


def _codebuild_rules(template: Template) -> list:
    rules = template.find_resources("AWS::Events::Rule")
    out = []
    for rule in rules.values():
        pattern = rule["Properties"]["EventPattern"]
        if pattern.get("source") == ["aws.codebuild"]:
            out.append(rule)
    return out


# ---- (1) mode all, no exclude_names ---------------------------------------


def test_mode_all_no_exclude_names_single_rule_no_pipeline_key():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            }
        )
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1

    pattern = cp_rules[0]["Properties"]["EventPattern"]
    assert pattern["source"] == ["aws.codepipeline"]
    assert pattern["detail-type"] == [
        "CodePipeline Pipeline Execution State Change"
    ]
    assert pattern["detail"]["state"] == ["FAILED"]
    assert "pipeline" not in pattern["detail"]


# ---- (1b) mode all + exclude_names ----------------------------------------


def test_mode_all_with_exclude_names_uses_anything_but():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {
                    "mode": "all",
                    "exclude_names": ["self-deploy-pipeline"],
                },
            }
        )
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    pattern = cp_rules[0]["Properties"]["EventPattern"]
    assert pattern["detail"]["pipeline"] == [
        {"anything-but": ["self-deploy-pipeline"]}
    ]


# ---- (2) mode selected ----------------------------------------------------


def test_mode_selected_pins_pipeline_names():
    names = ["pipeline-a", "pipeline-b"]
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "selected", "names": names},
            }
        )
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    pattern = cp_rules[0]["Properties"]["EventPattern"]
    assert pattern["detail"]["pipeline"] == names


# ---- (3) disabled ---------------------------------------------------------


def test_mode_none_creates_zero_rules():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "none"},
            }
        )
    )
    template.resource_count_is("AWS::Events::Rule", 0)


def test_enabled_false_creates_zero_rules():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            },
            enabled=False,
        )
    )
    template.resource_count_is("AWS::Events::Rule", 0)


# ---- (4) target is the imported ARN token ---------------------------------


def test_rule_target_is_imported_adapter_arn_token():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            }
        )
    )
    cp_rules = _codepipeline_rules(template)
    targets = cp_rules[0]["Properties"]["Targets"]
    assert len(targets) == 1
    arn = targets[0]["Arn"]
    # The ARN is a Ref to an AWS::SSM::Parameter::Value<String> CfnParameter
    # (a deploy-time token), never a literal string.
    assert isinstance(arn, dict) and "Ref" in arn
    cfn_params = template.find_parameters("*")
    assert arn["Ref"] in cfn_params
    assert cfn_params[arn["Ref"]]["Type"] == "AWS::SSM::Parameter::Value<String>"


# ---- (5) scoped invoke permission -----------------------------------------


def test_lambda_invoke_permission_scoped_to_rule_arn():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            }
        )
    )
    template.resource_count_is("AWS::Lambda::Permission", 1)
    perms = template.find_resources("AWS::Lambda::Permission")
    props = list(perms.values())[0]["Properties"]

    assert props["Action"] == "lambda:InvokeFunction"
    assert props["Principal"] == "events.amazonaws.com"

    # FunctionName is the imported ARN token (Ref to SSM CfnParameter).
    function_name = props["FunctionName"]
    assert isinstance(function_name, dict) and "Ref" in function_name

    # SourceArn must be the rule ARN token (GetAtt on the rule), not '*'.
    source_arn = props["SourceArn"]
    assert source_arn != "*"
    assert isinstance(source_arn, dict)
    assert source_arn.get("Fn::GetAtt", [None, None])[1] == "Arn"


# ---- (6) codebuild rule ---------------------------------------------------


def test_codebuild_enabled_adds_codebuild_rule():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
                "codebuild": {"enabled": True},
            }
        )
    )
    # Two rules total: codepipeline + codebuild.
    template.resource_count_is("AWS::Events::Rule", 2)
    cb_rules = _codebuild_rules(template)
    assert len(cb_rules) == 1
    pattern = cb_rules[0]["Properties"]["EventPattern"]
    assert pattern["source"] == ["aws.codebuild"]
    assert pattern["detail-type"] == ["CodeBuild Build State Change"]
    assert pattern["detail"]["build-status"] == ["FAILED"]


def test_codebuild_disabled_by_default_single_rule():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            }
        )
    )
    template.resource_count_is("AWS::Events::Rule", 1)


# ---- (7) missing adapter SSM path -----------------------------------------


def test_missing_adapter_lambda_arn_ssm_path_raises():
    with pytest.raises(ValueError, match="adapter_lambda_arn_ssm_path"):
        _build_template(
            _stack_cfg(
                {
                    "pipelines": {"mode": "all"},
                }
            )
        )


# ---- extra: approval-rejection widens the detail-type ---------------------


def test_subscribe_action_execution_widens_detail_type():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
                "approval_rejection": {"subscribe_action_execution": True},
            }
        )
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    detail_types = cp_rules[0]["Properties"]["EventPattern"]["detail-type"]
    assert "CodePipeline Pipeline Execution State Change" in detail_types
    assert "CodePipeline Action Execution State Change" in detail_types


# ---- extra: SSM export of rule ARN ----------------------------------------


def test_rule_arn_exported_to_ssm():
    template = _build_template(
        _stack_cfg(
            {
                "adapter_lambda_arn_ssm_path": ADAPTER_ARN_SSM_PATH,
                "pipelines": {"mode": "all"},
            }
        )
    )
    params = template.find_resources("AWS::SSM::Parameter")
    names = {p["Properties"]["Name"] for p in params.values()}
    assert any(
        name.startswith(f"/{WORKLOAD}/{ENV}/codepipeline-monitor/") for name in names
    )


# ---- extra: both registry aliases resolve ---------------------------------


def test_module_registered_under_both_aliases():
    from cdk_factory.stack.stack_module_registry import modules

    assert modules.registry.get("codepipeline_monitor_stack") is CodePipelineMonitorStack
    assert (
        modules.registry.get("codepipeline_monitor_library_module")
        is CodePipelineMonitorStack
    )
