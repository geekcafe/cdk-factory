"""
Tests for the ``ephemeral_storage_size`` Lambda config setting.

The setting is configured in MB and maps to the CDK ``ephemeral_storage_size``
argument (CloudFormation ``EphemeralStorage.Size``). When absent, nothing is
emitted so existing stacks produce no diff.
"""

import pytest
from aws_cdk import App, Stack, Size
from aws_cdk import aws_lambda
from aws_cdk.assertions import Match, Template

from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig


def _config(**overrides) -> LambdaFunctionConfig:
    return LambdaFunctionConfig({"name": "test-lambda", **overrides})


class TestEphemeralStorageSizeConfig:
    def test_absent_returns_none(self):
        assert _config().ephemeral_storage_size is None

    def test_empty_string_returns_none(self):
        assert _config(ephemeral_storage_size="").ephemeral_storage_size is None

    @pytest.mark.parametrize("value", [512, 4096, 10240, "2048"])
    def test_valid_value_returns_size_in_mb(self, value):
        size = _config(ephemeral_storage_size=value).ephemeral_storage_size
        assert isinstance(size, Size)
        assert size.to_mebibytes() == int(value)

    @pytest.mark.parametrize("value", [0, 511, 10241, -1])
    def test_out_of_range_raises(self, value):
        with pytest.raises(ValueError, match="between 512 and 10240 MB"):
            _ = _config(ephemeral_storage_size=value).ephemeral_storage_size

    def test_non_integer_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _ = _config(ephemeral_storage_size="lots").ephemeral_storage_size


class TestEphemeralStorageSizeSynth:
    """Confirm the property value synthesizes as expected when passed to CDK."""

    @staticmethod
    def _synth(lambda_config: LambdaFunctionConfig) -> Template:
        stack = Stack(App(), "TestStack")
        aws_lambda.Function(
            stack,
            "Fn",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=aws_lambda.Code.from_inline("def handler(e, c): pass"),
            memory_size=lambda_config.memory_size,
            ephemeral_storage_size=lambda_config.ephemeral_storage_size,
        )
        return Template.from_stack(stack)

    def test_configured_value_emits_ephemeral_storage(self):
        template = self._synth(_config(ephemeral_storage_size=4096))
        template.has_resource_properties(
            "AWS::Lambda::Function", {"EphemeralStorage": {"Size": 4096}}
        )

    def test_absent_value_omits_ephemeral_storage(self):
        template = self._synth(_config())
        template.has_resource_properties(
            "AWS::Lambda::Function", {"EphemeralStorage": Match.absent()}
        )
