"""
Unit tests for the shared ssm-location resolver
(``cdk_factory.utilities.ssm_path_utils.resolve_nested_ssm_config`` and the
``StackConfig.resolved_ssm_config`` delegate).

Background: an api-gateway stack may carry its ``ssm`` block at the stack top
level (``{"ssm": {...}}``) OR nested inside the module block
(``{"api_gateway": {"ssm": {...}}}``). Real configs do BOTH and even split keys
across the two blocks (one carries ``lambda_namespace``, the other
``user_pool_arn`` / ``namespace``). The resolver reconciles them by merging
per-key with the nested block winning, so every read site resolves the same
block regardless of shape.
"""

from cdk_factory.configurations.stack import StackConfig
from cdk_factory.utilities.ssm_path_utils import resolve_nested_ssm_config


class TestResolveNestedSsmConfig:
    """Direct tests of the standalone resolver."""

    def test_nested_only(self):
        cfg = {"api_gateway": {"ssm": {"imports": {"lambda_namespace": "a/b"}}}}
        resolved = resolve_nested_ssm_config(cfg, "api_gateway")
        assert resolved["imports"]["lambda_namespace"] == "a/b"

    def test_top_level_only(self):
        cfg = {"ssm": {"imports": {"lambda_namespace": "a/b"}}}
        resolved = resolve_nested_ssm_config(cfg, "api_gateway")
        assert resolved["imports"]["lambda_namespace"] == "a/b"

    def test_neither_present_returns_empty(self):
        assert resolve_nested_ssm_config({}, "api_gateway") == {}
        assert resolve_nested_ssm_config({"api_gateway": {}}, "api_gateway") == {}

    def test_nested_wins_on_conflicting_key(self):
        cfg = {
            "ssm": {"imports": {"lambda_namespace": "top/level"}},
            "api_gateway": {"ssm": {"imports": {"lambda_namespace": "nested/win"}}},
        }
        resolved = resolve_nested_ssm_config(cfg, "api_gateway")
        assert resolved["imports"]["lambda_namespace"] == "nested/win"

    def test_imports_merge_per_key_across_both_blocks(self):
        """The real sample_config.json shape: lambda_namespace at the top level,
        other import keys nested. Both must survive the merge."""
        cfg = {
            "ssm": {"imports": {"lambda_namespace": "factory-lambda/dev"}},
            "api_gateway": {
                "ssm": {
                    "enabled": True,
                    "imports": {
                        "namespace": "factory-lambda/dev",
                        "workload": "/factory-lambda/dev/lambda",
                        "environment": "/factory-lambda/dev/environment",
                    },
                }
            },
        }
        resolved = resolve_nested_ssm_config(cfg, "api_gateway")
        imports = resolved["imports"]
        # top-level-only key preserved
        assert imports["lambda_namespace"] == "factory-lambda/dev"
        # nested-only keys preserved
        assert imports["namespace"] == "factory-lambda/dev"
        assert imports["workload"] == "/factory-lambda/dev/lambda"
        # non-imports nested key merged in
        assert resolved["enabled"] is True

    def test_does_not_mutate_inputs(self):
        top = {"imports": {"a": "1"}}
        nested_ssm = {"imports": {"b": "2"}}
        cfg = {"ssm": top, "api_gateway": {"ssm": nested_ssm}}
        resolve_nested_ssm_config(cfg, "api_gateway")
        # Originals untouched.
        assert top == {"imports": {"a": "1"}}
        assert nested_ssm == {"imports": {"b": "2"}}

    def test_non_dict_input_is_safe(self):
        assert resolve_nested_ssm_config(None, "api_gateway") == {}
        assert resolve_nested_ssm_config("nope", "api_gateway") == {}


class TestStackConfigResolvedSsmConfig:
    """The StackConfig delegate must behave identically."""

    def test_delegates_to_shared_helper(self):
        stack_dict = {
            "name": "x",
            "ssm": {"imports": {"lambda_namespace": "top/level"}},
            "api_gateway": {"ssm": {"imports": {"user_pool_arn": "/full/arn"}}},
        }
        sc = StackConfig(stack=stack_dict, workload={"name": "w"})
        resolved = sc.resolved_ssm_config("api_gateway")
        # merged: lambda_namespace from top, user_pool_arn from nested
        assert resolved["imports"]["lambda_namespace"] == "top/level"
        assert resolved["imports"]["user_pool_arn"] == "/full/arn"
