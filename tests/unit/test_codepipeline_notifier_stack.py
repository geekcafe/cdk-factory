"""
Credential-free synth tests for the codepipeline_notifier stack (FEAT-002).

Mirrors test_codepipeline_monitor_stack.py via aws_cdk.assertions.Template with
a hermetic WorkloadConfig (the "devops" section is required or WorkloadConfig
sys.exit(1)s on a clean env). Run with SKIP_PIP=1 so LambdaFunctionUtilities does
not attempt a pip install during the Lambda asset build.

The notifier module OWNS its Lambda, so the asset is packaged from the standalone
project's ``src/devops_monitoring_lambdas`` package. The test points the
workload ``paths`` at the standalone repo root so the packaging helper resolves
``lambda.src`` (``./src/devops_monitoring_lambdas``). If that repo is not present
the Lambda-packaging tests skip (the no-Lambda assertions still run).

Asserts (per DESIGN §11):
  (1)  mode all, no exclude -> one CodePipeline rule, no detail.pipeline.
  (1b) mode all + exclude -> anything-but containing the self-exclude name.
  (2)  mode selected -> pinned detail.pipeline.
  (3)  mode none / enabled:false -> zero rules AND zero SNS topics AND zero Lambda.
  (4)  N channels-with-emails -> N AWS::SNS::Topic + correct Subscription count.
  (5)  owned Lambda target -> exactly one auto AWS::Lambda::Permission
       (events.amazonaws.com, SourceArn = rule ARN token, not '*').
  (6)  role ATTACHED TO THE FUNCTION scoped for GetSecretValue + Publish (not '*').
  (7)  codebuild.enabled -> extra aws.codebuild rule.
  (8)  env vars present & MONITOR_CHANNELS JSON contains the created topic ARNs.
  (9)  invalid config (dangling ref / empty channel / bad priority) -> ValueError.
  (10) both registry aliases resolve.
  (11) SSM fallback literal is exactly 'codepipeline-notifier'.
"""

import json
import os

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.codepipeline_notifier.codepipeline_notifier_stack import (
    CodePipelineNotifierStack,
)
from cdk_factory.workload.workload_factory import WorkloadConfig


WORKLOAD = "myapp"
ENV = "dev"
ACCOUNT = "111122223333"
REGION = "us-east-1"
STACK_NAME = "codepipeline-notifier"
SECRET_NAME = "codepipeline-notifier/slack/bot-token"

# The standalone project that owns the packaged notifier Lambda source. The
# packaging helper resolves lambda.src against the workload paths.
_STANDALONE_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "geek-cafe-devops-monitoring",
    )
)
_STANDALONE_SRC = os.path.join(_STANDALONE_ROOT, "src", "devops_monitoring_lambdas")
_HAS_STANDALONE = os.path.isdir(_STANDALONE_SRC)

requires_standalone = pytest.mark.skipif(
    not _HAS_STANDALONE,
    reason=(
        "geek-cafe-devops-monitoring package not present; Lambda packaging "
        "cannot be synthesized"
    ),
)

_LAMBDA_BLOCK = {
    "name": f"{WORKLOAD}-{ENV}-codepipeline-notifier",
    "src": "./src/devops_monitoring_lambdas",
    "handler": "handlers.codepipeline_notifier.app.lambda_handler",
    "runtime": "python3.11",
    "timeout": 30,
    "memory_size": 256,
    "include_power_tools_layer": True,
}


def _build_template(notifier: dict, enabled: bool = True) -> Template:
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    if _HAS_STANDALONE:
        wl.paths = [_STANDALONE_ROOT]
    stack_config = StackConfig(
        _stack_cfg(notifier, enabled=enabled), workload=wl.dictionary
    )
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
    stack = CodePipelineNotifierStack(
        app, "CodePipelineNotifier", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


def _stack_cfg(notifier: dict, enabled: bool = True) -> dict:
    cfg = {
        "name": STACK_NAME,
        "module": "codepipeline_notifier_stack",
        "codepipeline_notifier": notifier,
    }
    if enabled is not None:
        cfg["enabled"] = enabled
    return cfg


def _base_notifier(**overrides) -> dict:
    """A minimal valid notifier config with one Slack+SNS central channel."""
    notifier = {
        "pipelines": {"mode": "all"},
        "slack_bot_token_secret_name": SECRET_NAME,
        "channels": {
            "central": {
                "slack_channel_id": "C0CENTRAL000",
                "sns_emails": ["devops-oncall@example.com"],
            },
        },
        "central": "central",
        "state_priority_map": {"FAILED": "critical", "SUCCEEDED": "normal"},
        "deliver_priorities": ["critical"],
        "lambda": dict(_LAMBDA_BLOCK),
    }
    notifier.update(overrides)
    return notifier


def _codepipeline_rules(template: Template) -> list:
    rules = template.find_resources("AWS::Events::Rule")
    return [
        r
        for r in rules.values()
        if r["Properties"]["EventPattern"].get("source") == ["aws.codepipeline"]
    ]


def _codebuild_rules(template: Template) -> list:
    rules = template.find_resources("AWS::Events::Rule")
    return [
        r
        for r in rules.values()
        if r["Properties"]["EventPattern"].get("source") == ["aws.codebuild"]
    ]


# ---- (1) mode all, no exclude ---------------------------------------------


@requires_standalone
def test_mode_all_no_exclude_single_rule_no_pipeline_key():
    template = _build_template(_base_notifier(pipelines={"mode": "all"}))
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    pattern = cp_rules[0]["Properties"]["EventPattern"]
    assert pattern["source"] == ["aws.codepipeline"]
    assert pattern["detail-type"] == ["CodePipeline Pipeline Execution State Change"]
    assert set(pattern["detail"]["state"]) == {"FAILED", "SUCCEEDED"}
    assert "pipeline" not in pattern["detail"]


# ---- (1b) mode all + exclude (self-exclude feedback-loop guard) ------------


@requires_standalone
def test_mode_all_with_exclude_names_uses_anything_but_with_self_exclude():
    self_exclude = f"{WORKLOAD}-{ENV}-devops-monitoring-pipeline"
    template = _build_template(
        _base_notifier(pipelines={"mode": "all", "exclude_names": [self_exclude]})
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    pipeline_filter = cp_rules[0]["Properties"]["EventPattern"]["detail"]["pipeline"]
    assert pipeline_filter == [{"anything-but": [self_exclude]}]
    # REVIEW finding 2: the self-exclude name is present in the anything-but list.
    assert self_exclude in pipeline_filter[0]["anything-but"]


# ---- (2) mode selected ----------------------------------------------------


@requires_standalone
def test_mode_selected_pins_pipeline_names():
    names = ["pipeline-a", "pipeline-b"]
    template = _build_template(
        _base_notifier(pipelines={"mode": "selected", "names": names})
    )
    cp_rules = _codepipeline_rules(template)
    assert len(cp_rules) == 1
    assert cp_rules[0]["Properties"]["EventPattern"]["detail"]["pipeline"] == names


# ---- (3) disabled: zero rules, topics, lambda ------------------------------


def test_mode_none_creates_zero_resources():
    template = _build_template(_base_notifier(pipelines={"mode": "none"}))
    template.resource_count_is("AWS::Events::Rule", 0)
    template.resource_count_is("AWS::SNS::Topic", 0)
    template.resource_count_is("AWS::Lambda::Function", 0)


def test_enabled_false_creates_zero_resources():
    template = _build_template(_base_notifier(pipelines={"mode": "all"}), enabled=False)
    template.resource_count_is("AWS::Events::Rule", 0)
    template.resource_count_is("AWS::SNS::Topic", 0)
    template.resource_count_is("AWS::Lambda::Function", 0)


# ---- (4) per-channel SNS topics + subscriptions ---------------------------


@requires_standalone
def test_per_channel_sns_topics_and_subscriptions():
    template = _build_template(
        _base_notifier(
            channels={
                "central": {
                    "slack_channel_id": "C0CENTRAL000",
                    "sns_emails": ["a@example.com", "b@example.com"],
                },
                "team-web": {
                    "slack_channel_id": "C0WEBTEAM000",
                    "sns_emails": ["web@example.com"],
                },
                "slack-only": {
                    "slack_channel_id": "C0SLACKONLY0",
                    "sns_emails": [],
                },
            },
            central="central",
        )
    )
    # Two channels have emails -> two topics. The slack-only channel has none.
    template.resource_count_is("AWS::SNS::Topic", 2)
    # 2 + 1 = 3 email subscriptions.
    template.resource_count_is("AWS::SNS::Subscription", 3)


# ---- (5) owned Lambda auto invoke permission scoped to the rule -----------


@requires_standalone
def test_owned_lambda_auto_invoke_permission_scoped_to_rule():
    template = _build_template(_base_notifier())
    # One rule -> one auto-added permission for the owned function.
    perms = template.find_resources("AWS::Lambda::Permission")
    assert len(perms) == 1
    props = list(perms.values())[0]["Properties"]
    assert props["Action"] == "lambda:InvokeFunction"
    assert props["Principal"] == "events.amazonaws.com"
    source_arn = props["SourceArn"]
    assert source_arn != "*"
    assert isinstance(source_arn, dict)
    assert source_arn.get("Fn::GetAtt", [None, None])[1] == "Arn"


# ---- (6) role attached to the function scoped (not '*') -------------------


@requires_standalone
def test_function_role_scoped_for_get_secret_and_publish():
    template = _build_template(_base_notifier())

    functions = template.find_resources("AWS::Lambda::Function")
    assert len(functions) == 1
    fn_props = list(functions.values())[0]["Properties"]
    role_ref = fn_props["Role"]["Fn::GetAtt"][0]  # logical id of the role

    # Find the AWS::IAM::Policy attached to THAT role.
    policies = template.find_resources("AWS::IAM::Policy")
    attached = None
    for policy in policies.values():
        roles = policy["Properties"].get("Roles", [])
        for r in roles:
            if isinstance(r, dict) and r.get("Ref") == role_ref:
                attached = policy
                break
        if attached:
            break
    assert attached is not None, "no IAM::Policy attached to the function's role"

    statements = attached["Properties"]["PolicyDocument"]["Statement"]

    get_secret = [
        s for s in statements if "secretsmanager:GetSecretValue" in _actions(s)
    ]
    assert get_secret, "GetSecretValue statement missing from function role"
    for s in get_secret:
        assert s["Resource"] != "*"
        resource = s["Resource"]
        # Scoped to the secret ARN pattern (ends with the secret name + '*').
        rendered = json.dumps(resource)
        assert SECRET_NAME in rendered
        assert "secretsmanager" in rendered

    publish = [s for s in statements if "sns:Publish" in _actions(s)]
    assert publish, "sns:Publish statement missing from function role"
    for s in publish:
        assert s["Resource"] != "*"
        # The resource is the created topic ARN token (a Ref/GetAtt), not '*'.
        rendered = json.dumps(s["Resource"])
        assert "*" not in _literal_resource_strings(s["Resource"])


def _actions(statement: dict):
    actions = statement.get("Action", [])
    if isinstance(actions, str):
        return [actions]
    return actions


def _literal_resource_strings(resource):
    """Return only the literal string parts of a Resource (ignore Ref/GetAtt tokens)."""
    out = []
    if isinstance(resource, str):
        out.append(resource)
    elif isinstance(resource, list):
        for item in resource:
            if isinstance(item, str):
                out.append(item)
    return "".join(out)


# ---- (7) codebuild rule ---------------------------------------------------


@requires_standalone
def test_codebuild_enabled_adds_codebuild_rule():
    template = _build_template(_base_notifier(codebuild={"enabled": True}))
    cb_rules = _codebuild_rules(template)
    assert len(cb_rules) == 1
    pattern = cb_rules[0]["Properties"]["EventPattern"]
    assert pattern["source"] == ["aws.codebuild"]
    assert pattern["detail-type"] == ["CodeBuild Build State Change"]
    assert pattern["detail"]["build-status"] == ["FAILED"]
    # codepipeline + codebuild = 2 total rules.
    template.resource_count_is("AWS::Events::Rule", 2)


@requires_standalone
def test_codebuild_disabled_by_default_single_rule():
    template = _build_template(_base_notifier())
    template.resource_count_is("AWS::Events::Rule", 1)


# ---- (8) env vars + MONITOR_CHANNELS contains topic ARNs ------------------


@requires_standalone
def test_environment_monitor_channels_contains_topic_arns():
    template = _build_template(_base_notifier())
    functions = template.find_resources("AWS::Lambda::Function")
    fn_props = list(functions.values())[0]["Properties"]
    env = fn_props["Environment"]["Variables"]

    assert env["MONITOR_CENTRAL_CHANNEL"] == "central"
    assert env["MONITOR_SLACK_BOT_TOKEN_SECRET_ID"] == SECRET_NAME
    assert "MONITOR_STATE_PRIORITY_MAP" in env
    assert "MONITOR_DELIVER_PRIORITIES" in env
    assert "MONITOR_PIPELINE_ROUTES" in env
    assert "MONITOR_APPROVAL_REJECTION" in env
    assert "MONITOR_CONSOLE_BASE_URL" in env

    # MONITOR_CHANNELS is a JSON string; the central channel's sns_topic_arn is
    # the created topic's deploy-time token (a CFN intrinsic serialized by CDK).
    channels_raw = env["MONITOR_CHANNELS"]
    assert isinstance(channels_raw, (str, dict))
    rendered = json.dumps(channels_raw)
    assert "central" in rendered
    assert "sns_topic_arn" in rendered
    assert "slack_channel_id" in rendered


@requires_standalone
def test_environment_monitor_channels_carries_mention():
    template = _build_template(
        _base_notifier(
            channels={
                "central": {
                    "slack_channel_id": "C0CENTRAL000",
                    "sns_emails": ["devops-oncall@example.com"],
                    "mention": "channel",
                },
            },
            central="central",
        )
    )
    # MONITOR_CHANNELS is a CFN intrinsic (Fn::Join) because each channel's
    # sns_topic_arn is a deploy-time topic-ARN token; the mention key is emitted
    # as a literal JSON segment inside that join. Assert on the rendered form,
    # same approach as test_environment_monitor_channels_contains_topic_arns.
    functions = template.find_resources("AWS::Lambda::Function")
    fn_props = list(functions.values())[0]["Properties"]
    channels_raw = fn_props["Environment"]["Variables"]["MONITOR_CHANNELS"]
    rendered = json.dumps(channels_raw)
    # The join part is a JSON string, so quotes are escaped in the dumped form.
    assert r"\"mention\": \"channel\"" in rendered


@requires_standalone
def test_environment_monitor_channels_omits_mention_when_absent():
    # A channel without a mention keeps today's exact 2-key shape (no mention
    # segment anywhere in the rendered MONITOR_CHANNELS).
    template = _build_template(_base_notifier())
    functions = template.find_resources("AWS::Lambda::Function")
    fn_props = list(functions.values())[0]["Properties"]
    channels_raw = fn_props["Environment"]["Variables"]["MONITOR_CHANNELS"]
    rendered = json.dumps(channels_raw)
    assert "mention" not in rendered


# ---- (9) invalid config -> ValueError at synth ----------------------------


def test_dangling_central_reference_raises():
    with pytest.raises(ValueError, match="central"):
        _build_template(
            _base_notifier(
                channels={"team": {"slack_channel_id": "C0TEAM0", "sns_emails": []}},
                central="nope",
            )
        )


def test_empty_channel_raises():
    with pytest.raises(ValueError, match="neither"):
        _build_template(
            _base_notifier(
                channels={"central": {"slack_channel_id": "", "sns_emails": []}},
                central="central",
            )
        )


def test_bad_priority_raises():
    with pytest.raises(ValueError, match="priority"):
        _build_template(
            _base_notifier(
                state_priority_map={"FAILED": "urgent"},
            )
        )


def test_dangling_route_channel_raises():
    with pytest.raises(ValueError, match="pipeline_routes"):
        _build_template(
            _base_notifier(
                pipeline_routes={"some-pipeline": ["ghost-channel"]},
            )
        )


def test_no_channels_raises():
    with pytest.raises(ValueError, match="at least one channel"):
        _build_template(
            _base_notifier(channels={}, central="central"),
        )


# ---- (10) both registry aliases resolve -----------------------------------


def test_module_registered_under_both_aliases():
    from cdk_factory.stack.stack_module_registry import modules

    assert (
        modules.registry.get("codepipeline_notifier_stack") is CodePipelineNotifierStack
    )
    assert (
        modules.registry.get("codepipeline_notifier_library_module")
        is CodePipelineNotifierStack
    )


# ---- (11) SSM export fallback literal is 'codepipeline-notifier' ----------


@requires_standalone
def test_ssm_export_uses_notifier_fallback_literal():
    # No ssm.namespace -> fallback literal path.
    template = _build_template(_base_notifier())
    params = template.find_resources("AWS::SSM::Parameter")
    names = {p["Properties"]["Name"] for p in params.values()}
    assert any(
        name.startswith(f"/{WORKLOAD}/{ENV}/codepipeline-notifier/") for name in names
    )
    # And never the monitor module's literal.
    assert not any("/codepipeline-monitor/" in name for name in names)


def _build_template_with_stack_ssm(namespace: str) -> Template:
    """Build the notifier stack with a TOP-LEVEL ``ssm.namespace`` (a sibling of
    ``name`` / ``codepipeline_notifier`` — the placement the monitor config uses).
    """
    wl = WorkloadConfig({"workload": {"name": WORKLOAD, "devops": {"name": "d"}}})
    if _HAS_STANDALONE:
        wl.paths = [_STANDALONE_ROOT]
    stack_dict = _stack_cfg(_base_notifier())
    stack_dict["ssm"] = {"namespace": namespace}
    stack_config = StackConfig(stack_dict, workload=wl.dictionary)
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
    stack = CodePipelineNotifierStack(
        app, "CodePipelineNotifier", env={"account": ACCOUNT, "region": REGION}
    )
    stack.build(stack_config=stack_config, deployment=deployment, workload=wl)
    return Template.from_stack(stack)


@requires_standalone
def test_ssm_export_honors_top_level_namespace():
    # A TOP-LEVEL ssm.namespace (sibling of codepipeline_notifier) MUST be used
    # as the SSM prefix, not silently dropped to the workload/env fallback. This
    # is the tenant-isolation seam: the monitor config places a tenant-segmented
    # namespace here, and dropping it collapses two tenants' SSM parameters to
    # identical names in a shared account.
    namespace = f"{WORKLOAD}/geekcafe/{ENV}/codepipeline-notifier"
    template = _build_template_with_stack_ssm(namespace)
    params = template.find_resources("AWS::SSM::Parameter")
    names = {p["Properties"]["Name"] for p in params.values()}
    assert names, "expected at least one SSM parameter"
    assert all(name.startswith(f"/{namespace}/") for name in names), names
    # And NOT the workload/env fallback that omits the tenant segment.
    assert not any(
        name.startswith(f"/{WORKLOAD}/{ENV}/codepipeline-notifier/") for name in names
    )
