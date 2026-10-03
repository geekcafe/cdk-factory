"""
Unit tests for the normalizing SSM-path helper.

Covers ``cdk_factory.utilities.ssm_path_utils.normalize_ssm_path`` and
``join_ssm_path``: the tolerant-input -> canonical-output helper introduced to
replace the brittle strict "must start with '/'" validation that fatally rejected
legitimate bare namespace fragments (e.g. ``lambda_namespace: "geekcafe/prod"``).

The companion synth regression lives in
``tests/unit/test_api_gateway_lambda_namespace_normalization.py``.
"""

import pytest

from cdk_factory.utilities.ssm_path_utils import (
    normalize_ssm_path,
    join_ssm_path,
    build_ssm_path,
)


class TestNormalizeSsmPath:
    """normalize_ssm_path: tolerant input -> canonical full SSM path."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # bare namespace fragment gets a single leading slash (the exact
            # geek-cafe-lambdas failure: lambda_namespace="geekcafe/prod")
            ("geekcafe/prod", "/geekcafe/prod"),
            # already-correct value is unchanged (idempotence / backward compat)
            ("/geekcafe/prod", "/geekcafe/prod"),
            # full user_pool_arn style path must be unchanged
            (
                "/geekcafe/prod/cognito/user-pool/user-pool-arn",
                "/geekcafe/prod/cognito/user-pool/user-pool-arn",
            ),
            # trailing slash stripped
            ("geekcafe/prod/", "/geekcafe/prod"),
            ("/a/b/", "/a/b"),
            # duplicate internal + leading + trailing slashes collapsed
            ("//a//b//", "/a/b"),
            ("///x///y///z///", "/x/y/z"),
            # surrounding whitespace trimmed
            ("  geekcafe/prod  ", "/geekcafe/prod"),
        ],
    )
    def test_canonicalization(self, raw, expected):
        assert normalize_ssm_path(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "geekcafe/prod",
            "/geekcafe/prod",
            "geekcafe/prod/",
            "//a//b//",
            "/geekcafe/prod/cognito/user-pool/user-pool-arn",
        ],
    )
    def test_idempotent(self, raw):
        once = normalize_ssm_path(raw)
        assert normalize_ssm_path(once) == once

    def test_lone_root_preserved(self):
        assert normalize_ssm_path("/") == "/"

    def test_unresolved_template_placeholder_preserved(self):
        # A value still containing {{...}} is resolved elsewhere; it must not be
        # reshaped (no leading slash added, no slash collapsing) here.
        assert normalize_ssm_path("{{WORKLOAD_NAME}}/{{ENVIRONMENT}}") == (
            "{{WORKLOAD_NAME}}/{{ENVIRONMENT}}"
        )
        assert normalize_ssm_path("{{WORKLOAD_NAME}}/x") == "{{WORKLOAD_NAME}}/x"

    def test_cdk_token_preserved(self):
        # A real CDK token must pass through untouched (no corruption at synth).
        from aws_cdk import App, Stack
        from aws_cdk import aws_ssm as ssm

        app = App()
        stack = Stack(app, "tok-stack")
        token = ssm.StringParameter.value_for_string_parameter(
            stack, "/some/param/path"
        )
        assert normalize_ssm_path(token) == token

    def test_non_string_passthrough(self):
        # Defensive: non-strings are returned unchanged (callers may pass None).
        assert normalize_ssm_path(None) is None


class TestJoinSsmPath:
    """join_ssm_path: compose segments into a clean canonical path."""

    def test_bare_namespace_fragment(self):
        assert join_ssm_path("geekcafe/prod", "my-lambda", "arn") == (
            "/geekcafe/prod/my-lambda/arn"
        )

    def test_slash_prefixed_fragment(self):
        assert join_ssm_path("/geekcafe/prod", "my-lambda", "arn") == (
            "/geekcafe/prod/my-lambda/arn"
        )

    def test_trailing_slash_fragment(self):
        assert join_ssm_path("geekcafe/prod/", "my-lambda", "arn") == (
            "/geekcafe/prod/my-lambda/arn"
        )

    def test_slashes_everywhere(self):
        assert join_ssm_path("/geekcafe/prod/", "/my-lambda/", "arn") == (
            "/geekcafe/prod/my-lambda/arn"
        )

    def test_skips_empty_segments(self):
        assert join_ssm_path("geekcafe/prod", "", None, "arn") == (
            "/geekcafe/prod/arn"
        )

    def test_build_ssm_path_alias(self):
        # Backward-compatible alias retained for existing imports/tests.
        assert build_ssm_path is join_ssm_path
        assert build_ssm_path("my-saas-app", "dev", "cognito", "user-pool-id") == (
            "/my-saas-app/dev/cognito/user-pool-id"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
