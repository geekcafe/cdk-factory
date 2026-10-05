"""
Unit tests for SSM import validation of name-component keys.

Name-component keys under `ssm.imports` (namespace, lambda_namespace,
cognito_namespace, route53_namespace, ...) are used to BUILD SSM paths, not
as paths themselves, so they must be skipped by SSM path validation (which
requires a leading "/"). These tests lock in that behavior and guard against
regressing the inconsistency where different validators skipped different keys.
"""

import pytest

from cdk_factory.interfaces.standardized_ssm_mixin import (
    StandardizedSsmMixin,
    SsmStandardValidator,
    SSM_NAME_COMPONENT_KEYS,
)


def _mixin_with_imports(imports: dict) -> StandardizedSsmMixin:
    m = StandardizedSsmMixin()
    # _validate_ssm_configuration reads self.ssm_config
    m.ssm_config = {"imports": imports, "exports": {}}
    return m


class TestSsmNameComponentValidation:
    def test_namespace_keys_are_recognized(self):
        for key in (
            "namespace",
            "lambda_namespace",
            "cognito_namespace",
            "route53_namespace",
            "workload",
            "environment",
            "organization",
        ):
            assert key in SSM_NAME_COMPONENT_KEYS, f"{key} should be a name component"

    def test_slashless_namespace_components_pass_validation(self):
        """Slash-less namespace values must NOT be rejected as SSM paths."""
        mixin = _mixin_with_imports(
            {
                "workload": "geekcafe",
                "environment": "prod",
                "lambda_namespace": "geekcafe/prod/lambda",
                "cognito_namespace": "geekcafe/prod/cognito",
                "route53_namespace": "geekcafe/prod/route53",
            }
        )
        # Should not raise
        mixin._validate_ssm_configuration()

    def test_real_ssm_path_import_still_validated(self):
        """A genuine path-valued import is still validated (must start with '/')."""
        mixin = _mixin_with_imports(
            {
                "lambda_namespace": "geekcafe/prod/lambda",
                "user_pool_arn": "no-leading-slash/path",
            }
        )
        with pytest.raises(ValueError, match="must start with '/'"):
            mixin._validate_ssm_configuration()

    def test_valid_full_path_import_passes(self):
        mixin = _mixin_with_imports(
            {
                "lambda_namespace": "geekcafe/prod/lambda",
                "user_pool_arn": "/geekcafe/prod/cognito/user-pool/user-pool-arn",
            }
        )
        mixin._validate_ssm_configuration()

    def test_standard_validator_skips_name_components(self):
        """SsmStandardValidator also skips name-component keys (was inconsistent before)."""
        validator = SsmStandardValidator()
        config = {
            "ssm": {
                "imports": {
                    "lambda_namespace": "geekcafe/prod/lambda",
                    "cognito_namespace": "geekcafe/prod/cognito",
                    "route53_namespace": "geekcafe/prod/route53",
                    "namespace": "geekcafe/prod",
                },
                "exports": {},
            }
        }
        result = validator.validate_configuration(config)
        assert result.valid, result.errors

    def test_standard_validator_still_flags_bad_paths(self):
        validator = SsmStandardValidator()
        config = {
            "ssm": {
                "imports": {
                    "lambda_namespace": "geekcafe/prod/lambda",
                    "user_pool_arn": "no-slash/path",
                },
                "exports": {},
            }
        }
        result = validator.validate_configuration(config)
        assert not result.valid
        assert any("must start with '/'" in e for e in result.errors)
