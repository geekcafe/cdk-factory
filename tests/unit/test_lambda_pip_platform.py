"""
Unit tests for the cross-platform pip target-platform resolver.

The AWS Lambda Python runtime runs on Linux, so Lambda dependencies must be
pip-installed with a manylinux ``--platform`` tag and the runtime's python
version regardless of the build host. These tests assert the resolver derives
both values GENERICALLY from the configured runtime/architecture — nothing is
hardcoded to a single app or a single runtime.
"""

import pytest
from aws_cdk import aws_lambda

from cdk_factory.utilities.lambda_pip_platform import (
    DEFAULT_MANYLINUX_FAMILY,
    platform_tag_from_architecture,
    python_version_from_runtime,
    resolve_pip_target_platform,
)


class TestPythonVersionFromRuntime:
    def test_python_312(self):
        assert python_version_from_runtime(aws_lambda.Runtime.PYTHON_3_12) == "3.12"

    def test_python_311(self):
        assert python_version_from_runtime(aws_lambda.Runtime.PYTHON_3_11) == "3.11"

    def test_python_39(self):
        assert python_version_from_runtime(aws_lambda.Runtime.PYTHON_3_9) == "3.9"

    def test_non_python_runtime_raises(self):
        with pytest.raises(ValueError):
            python_version_from_runtime(aws_lambda.Runtime.NODEJS_18_X)


class TestPlatformTagFromArchitecture:
    def test_x86_64(self):
        assert (
            platform_tag_from_architecture(aws_lambda.Architecture.X86_64)
            == "manylinux2014_x86_64"
        )

    def test_arm64(self):
        assert (
            platform_tag_from_architecture(aws_lambda.Architecture.ARM_64)
            == "manylinux2014_aarch64"
        )

    def test_overridable_manylinux_family(self):
        assert (
            platform_tag_from_architecture(
                aws_lambda.Architecture.X86_64, manylinux_family="manylinux_2_28"
            )
            == "manylinux_2_28_x86_64"
        )

    def test_default_family_constant(self):
        assert DEFAULT_MANYLINUX_FAMILY == "manylinux2014"


class TestResolvePipTargetPlatform:
    def test_default_runtime_arch(self):
        assert resolve_pip_target_platform(
            aws_lambda.Runtime.PYTHON_3_12, aws_lambda.Architecture.X86_64
        ) == ("3.12", "manylinux2014_x86_64")

    def test_non_default_runtime_and_arm(self):
        assert resolve_pip_target_platform(
            aws_lambda.Runtime.PYTHON_3_11, aws_lambda.Architecture.ARM_64
        ) == ("3.11", "manylinux2014_aarch64")
