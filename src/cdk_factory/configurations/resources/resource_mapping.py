"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_cdk import aws_lambda


class ResourceMapping:
    @staticmethod
    def get_architecture(arch_string: str) -> aws_lambda.Architecture:
        """get the architecture from a string"""
        architecture_mapping = {
            "x86_64": aws_lambda.Architecture.X86_64,
            "x8664": aws_lambda.Architecture.X86_64,
            "arm_64": aws_lambda.Architecture.ARM_64,
            "arm64": aws_lambda.Architecture.ARM_64,
        }
        return architecture_mapping.get(arch_string.lower(), None)

    @staticmethod
    def get_tracing(tracing_string: str) -> aws_lambda.Tracing:
        """get the tracing from a string"""
        tracing_mapping = {
            "disabled": aws_lambda.Tracing.DISABLED,
            "active": aws_lambda.Tracing.ACTIVE,
            "enabled": aws_lambda.Tracing.ACTIVE,
            "enable": aws_lambda.Tracing.ACTIVE,
        }
        tracing = tracing_mapping.get(tracing_string.lower(), None)
        if not tracing:
            tracing = aws_lambda.Tracing.DISABLED
        return tracing

    @staticmethod
    def get_runtime(runtime: str) -> aws_lambda.Runtime:
        """get the insights version from a string"""
        # todo: add additional mappings for other runtimes
        runtime_mapping = {
            "python3.8": aws_lambda.Runtime.PYTHON_3_8,
            "python3.9": aws_lambda.Runtime.PYTHON_3_9,
            "python3.10": aws_lambda.Runtime.PYTHON_3_10,
            "python3.11": aws_lambda.Runtime.PYTHON_3_11,
            "python3.12": aws_lambda.Runtime.PYTHON_3_12,
        }
        return runtime_mapping.get(runtime.lower(), None)

    @staticmethod
    def get_insights_version(insights_version: str) -> aws_lambda.LambdaInsightsVersion:
        """get the insights version from a string"""
        insights_version_mapping = {
            "version_1_0_229_0": aws_lambda.LambdaInsightsVersion.VERSION_1_0_229_0,
            "VERSION_1_0_178_0": aws_lambda.LambdaInsightsVersion.VERSION_1_0_178_0,
        }
        return insights_version_mapping.get(insights_version.lower(), None)
