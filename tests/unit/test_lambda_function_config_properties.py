"""
Property-level unit tests for ``LambdaFunctionConfig``.

Every public property (and setter) declared on
``cdk_factory.configurations.resources.lambda_function.LambdaFunctionConfig``
is exercised here for both the "configured" and the "defaulted" case.

Motivation: the ``name`` setter referenced an undefined ``config`` name instead
of ``value``. It went unnoticed because nothing ever called the setter.
``test_every_property_is_covered`` guards against a new property being added
without a matching test. (``ephemeral_storage_size`` and description truncation
have deeper coverage in their own dedicated test modules.)
"""

import shutil

import pytest
from aws_cdk import Size
from aws_cdk import aws_lambda

from cdk_factory.configurations.resources.cloudwatch_widget import (
    CloudWatchWidgetConfig,
)
from cdk_factory.configurations.resources.docker import DockerConfig
from cdk_factory.configurations.resources.ecr import ECRConfig
from cdk_factory.configurations.resources.image_config import ImageConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.configurations.resources.lambda_triggers import LambdaTriggersConfig
from cdk_factory.configurations.resources.sqs import SQS


def _config(**overrides) -> LambdaFunctionConfig:
    return LambdaFunctionConfig({"name": "test-lambda", **overrides})


# Properties exercised by this module. Keep in sync with LambdaFunctionConfig;
# the coverage guard below fails if one is added/removed without updating it.
COVERED_PROPERTIES = {
    "name",
    "resource_policies",
    "auto_name",
    "src",
    "version_file",
    "version_number",
    "handler",
    "description",
    "memory_size",
    "ephemeral_storage_size",
    "reserved_concurrent_executions",
    "runtime",
    "timeout",
    "stack",
    "dependencies_to_layer",
    "exclude_packages",
    "insights_version",
    "add_common_layer",
    "architecture",
    "tracing",
    "include_power_tools_layer",
    "environment_variables",
    "log_level",
    "powertools_sample_rate",
    "powertools_log_event",
    "permissions",
    "layers",
    "ssm_layer_arns",
    "execution_role_arn",
    "execution_role_name",
    "recursive_loop",
    "raw_ecr_name",
}


def test_every_property_is_covered():
    """Fail loudly when a property is added to LambdaFunctionConfig without a test."""
    actual = {
        k for k, v in vars(LambdaFunctionConfig).items() if isinstance(v, property)
    }
    assert actual == COVERED_PROPERTIES, (
        f"Untested: {sorted(actual - COVERED_PROPERTIES)}; "
        f"stale: {sorted(COVERED_PROPERTIES - actual)}"
    )


def test_every_setter_round_trips():
    """Every property with a setter must accept a value and return it."""
    setters = [
        k
        for k, v in vars(LambdaFunctionConfig).items()
        if isinstance(v, property) and v.fset
    ]
    assert setters, "expected at least one setter"
    for prop in setters:
        cfg = _config()
        setattr(cfg, prop, "override-value")
        assert getattr(cfg, prop) == "override-value", prop


class TestConstruction:
    def test_sub_configs_are_built(self):
        cfg = _config(
            api={"route": "/things", "method": "get"},
            triggers=[{"resource_type": "sqs", "queue_name": "q"}],
        )
        assert isinstance(cfg.docker, DockerConfig)
        assert isinstance(cfg.ecr, ECRConfig)
        assert isinstance(cfg.sqs, SQS)
        assert isinstance(cfg.image_config, ImageConfig)
        assert isinstance(cfg.cloudwatch_widget, CloudWatchWidgetConfig)
        assert cfg.api is not None and cfg.api.route == "/things"
        assert len(cfg.triggers) == 1
        assert isinstance(cfg.triggers[0], LambdaTriggersConfig)

    def test_api_absent_is_none(self):
        assert _config().api is None
        assert _config(api="not-a-dict").api is None

    def test_default_audit_queue_added_when_queues_exist(self):
        cfg = _config(sqs={"queues": [{"type": "consumer", "queue_name": "work"}]})
        names = [q.name for q in cfg.sqs.queues]
        assert names == ["work", "app-audit-logger-sqs-queue"]

    def test_default_audit_queue_not_duplicated(self):
        cfg = _config(
            sqs={
                "queues": [
                    {"type": "producer", "queue_name": "app-audit-logger-sqs-queue"}
                ]
            }
        )
        assert [q.name for q in cfg.sqs.queues] == ["app-audit-logger-sqs-queue"]

    def test_no_sqs_config_adds_no_queues(self):
        assert _config().sqs.queues == []


class TestName:
    def test_reads_name(self):
        assert _config().name == "test-lambda"

    def test_missing_returns_empty_string(self):
        assert LambdaFunctionConfig({}).name == ""

    def test_setter_overrides_config(self):
        cfg = _config()
        cfg.name = "renamed-fn"
        assert cfg.name == "renamed-fn"

    def test_setter_value_is_validated(self):
        cfg = _config()
        cfg.name = "bad name!"
        with pytest.raises(ValueError, match="alphanumeric"):
            _ = cfg.name

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="between 1 and 64"):
            _ = LambdaFunctionConfig({"name": "a" * 65}).name

    def test_invalid_characters_raise(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            _ = LambdaFunctionConfig({"name": "has.dot"}).name

    def test_unresolved_placeholder_skips_validation(self):
        value = "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-fn"
        assert LambdaFunctionConfig({"name": value}).name == value


class TestExecutionRole:
    def test_arn_from_config_and_setter(self):
        arn = "arn:aws:iam::123456789012:role/r"
        assert _config(execution_role_arn=arn).execution_role_arn == arn
        assert _config().execution_role_arn is None
        cfg = _config()
        cfg.execution_role_arn = arn
        assert cfg.execution_role_arn == arn

    def test_name_from_config_and_setter(self):
        assert _config(execution_role_name="r").execution_role_name == "r"
        assert _config().execution_role_name is None
        cfg = _config()
        cfg.execution_role_name = "other"
        assert cfg.execution_role_name == "other"


class TestListProperties:
    @pytest.mark.parametrize(
        "prop, value",
        [
            ("resource_policies", [{"principal": "s3.amazonaws.com"}]),
            ("environment_variables", [{"name": "A", "value": "1"}]),
            ("permissions", [{"dynamodb": "read", "table": "t"}]),
            ("layers", [{"arn": "arn:aws:lambda:us-east-1:1:layer:x:1"}]),
            ("ssm_layer_arns", [{"ssm_path": "/a/b"}]),
        ],
    )
    def test_configured_and_default(self, prop, value):
        assert getattr(_config(**{prop: value}), prop) == value
        assert getattr(_config(), prop) == []

    def test_resource_policies_non_list_returns_empty(self):
        assert _config(resource_policies={"not": "a list"}).resource_policies == []


class TestAutoName:
    def test_defaults_true(self):
        assert _config().auto_name is True

    def test_string_values(self):
        assert _config(auto_name="true").auto_name is True
        assert _config(auto_name="false").auto_name is False

    def test_empty_config_returns_false(self):
        assert LambdaFunctionConfig({}).auto_name is False

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known defect: auto_name compares str(value) == 'true' without "
            ".lower(), so a JSON boolean `true` evaluates to False."
        ),
    )
    def test_json_boolean_true(self):
        assert _config(auto_name=True).auto_name is True


class TestSrc:
    def test_configured(self):
        assert _config(src="src/handlers").src == "src/handlers"

    def test_missing_raises(self):
        with pytest.raises(RuntimeError, match="Source Directory was not defined"):
            _ = _config().src


class TestVersion:
    def test_version_file_default(self):
        assert _config().version_file == ""
        assert _config(version_file="v.txt").version_file == "v.txt"

    def test_no_version_file(self):
        assert _config().version_number == "0.0.0_na"

    def test_txt_version_file(self, tmp_path):
        version = tmp_path / "version.txt"
        version.write_text("1.2.3", encoding="utf-8")
        assert _config(version_file=str(version)).version_number == "1.2.3"

    def test_missing_txt_version_file(self, tmp_path):
        missing = tmp_path / "nope.txt"
        assert _config(version_file=str(missing)).version_number == "0.0.0_na"

    def test_unsupported_extension(self, tmp_path):
        other = tmp_path / "version.json"
        other.write_text("{}", encoding="utf-8")
        assert _config(version_file=str(other)).version_number == "0.0.0_na"

    @pytest.mark.skipif(shutil.which("python") is None, reason="`python` not on PATH")
    def test_py_version_file(self, tmp_path):
        script = tmp_path / "version.py"
        script.write_text("print('4.5.6')", encoding="utf-8")
        assert _config(version_file=str(script)).version_number.strip() == "4.5.6"


class TestScalarDefaults:
    def test_handler(self):
        assert _config().handler == "app.lambda_handler"
        assert _config(handler="x.main").handler == "x.main"

    def test_description(self):
        assert _config(description="Does a thing").description == "Does a thing"
        assert _config().description == "Lambda Function for test-lambda"
        assert len(_config(description="x" * 300).description) == 256

    def test_memory_size(self):
        assert _config().memory_size == 128
        assert _config(memory_size="1024").memory_size == 1024

    def test_ephemeral_storage_size(self):
        assert _config().ephemeral_storage_size is None
        size = _config(ephemeral_storage_size=1024).ephemeral_storage_size
        assert isinstance(size, Size) and size.to_mebibytes() == 1024

    def test_reserved_concurrent_executions(self):
        assert _config().reserved_concurrent_executions is None
        assert _config(reserved_concurrent_executions="5").reserved_concurrent_executions == 5

    def test_stack(self):
        assert _config().stack == "primary"
        assert _config(stack="secondary").stack == "secondary"
        assert LambdaFunctionConfig({}).stack is None

    def test_log_level(self):
        assert _config().log_level == "INFO"
        assert _config(log_level="DEBUG").log_level == "DEBUG"

    def test_powertools_sample_rate(self):
        assert _config().powertools_sample_rate == pytest.approx(0.1)
        assert _config(powertools_sample_rate="0.5").powertools_sample_rate == pytest.approx(0.5)

    def test_recursive_loop(self):
        assert _config().recursive_loop is None
        assert _config(recursive_loop="Allow").recursive_loop == "Allow"

    def test_raw_ecr_name(self):
        assert _config().raw_ecr_name == ""
        assert _config(ecr={"name": "org/repo"}).raw_ecr_name == "org/repo"


class TestBooleanProperties:
    @pytest.mark.parametrize(
        "prop, default",
        [
            ("dependencies_to_layer", False),
            ("add_common_layer", True),
            ("include_power_tools_layer", True),
            ("powertools_log_event", True),
        ],
    )
    def test_default(self, prop, default):
        assert getattr(_config(), prop) is default

    @pytest.mark.parametrize(
        "prop",
        [
            "dependencies_to_layer",
            "add_common_layer",
            "include_power_tools_layer",
            "powertools_log_event",
        ],
    )
    @pytest.mark.parametrize(
        "value, expected",
        [(True, True), ("true", True), ("TRUE", True), (False, False), ("false", False)],
    )
    def test_configured(self, prop, value, expected):
        assert getattr(_config(**{prop: value}), prop) is expected


class TestExcludePackages:
    def test_absent_returns_none(self):
        assert _config().exclude_packages is None

    def test_list(self):
        assert _config(exclude_packages=["boto3"]).exclude_packages == ["boto3"]
        assert _config(exclude_packages=[]).exclude_packages == []

    def test_non_list_raises(self):
        with pytest.raises(ValueError, match="must be a list"):
            _ = _config(exclude_packages="boto3").exclude_packages


class TestCdkMappedProperties:
    def test_runtime(self):
        assert _config().runtime.name == aws_lambda.Runtime.PYTHON_3_12.name
        assert _config(runtime="python3.11").runtime.name == "python3.11"

    def test_architecture(self):
        assert _config().architecture.name == aws_lambda.Architecture.X86_64.name
        assert (
            _config(architecture="arm64").architecture.name
            == aws_lambda.Architecture.ARM_64.name
        )

    @pytest.mark.parametrize(
        "value, expected",
        [
            (None, aws_lambda.Tracing.ACTIVE),
            ("active", aws_lambda.Tracing.ACTIVE),
            ("disabled", aws_lambda.Tracing.DISABLED),
            ("unknown", aws_lambda.Tracing.DISABLED),
        ],
    )
    def test_tracing(self, value, expected):
        overrides = {} if value is None else {"tracing": value}
        assert _config(**overrides).tracing == expected

    def test_insights_version(self):
        assert _config().insights_version is None
        version = _config(insights_version="version_1_0_229_0").insights_version
        assert isinstance(version, aws_lambda.LambdaInsightsVersion)


class TestTimeout:
    def test_default(self):
        assert _config().timeout.to_seconds() == 30

    def test_configured_without_api(self):
        assert _config(timeout=300).timeout.to_seconds() == 300

    def test_api_route_caps_timeout(self):
        cfg = _config(timeout=300, api={"route": "/x", "method": "get"})
        assert cfg.timeout.to_seconds() == 30


def test_arn_helper():
    arn = _config().arn("us-east-1", "123456789012", "my-fn")
    assert arn == "arn:aws:lambda:us-east-1:123456789012:function:my-fn"
