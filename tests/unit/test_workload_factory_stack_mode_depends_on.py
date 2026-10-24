"""
Unit tests for WorkloadFactory stack-mode depends_on wiring (FEAT-001).

These tests exercise the depends_on wiring added to
WorkloadFactory.__build_stacks for mode:"stack" deployments. They use real
config objects and a real aws_cdk.App (no AWS, no MagicMock), following the
convention in tests/unit/test_lambda_stack.py.

The build is driven through the name-mangled private method
`_WorkloadFactory__build_stacks`, which is the method FEAT-001 edits. Each
"stack" uses the already-registered `secrets_manager_stack` module seeded with a
single placeholder secret, keeping the synthesized stacks resource-light.
"""

import json
import os
import tempfile

import pytest
from aws_cdk import App

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadFactory


WORKLOAD_DICT = {
    "name": "test-workload",
    "description": "Test workload for stack-mode depends_on testing",
    "stacks": [],
}


def _make_secrets_stack_dict(name: str, depends_on=None) -> dict:
    """A trivial, resource-light secrets_manager_stack config (one secret)."""
    stack: dict = {
        "name": name,
        "module": "secrets_manager_stack",
        "enabled": True,
        "secrets": [{"name": f"{name}/placeholder", "placeholder": "REPLACE_ME"}],
    }
    if depends_on is not None:
        stack["depends_on"] = depends_on
    return stack


def _build_workload_factory() -> WorkloadFactory:
    """Create a WorkloadFactory backed by a minimal temp config (no stacks).

    We then drive __build_stacks directly with a hand-built DeploymentConfig,
    so the on-disk config only needs to satisfy construction.
    """
    app = App()
    with tempfile.TemporaryDirectory() as tmp:
        config_path = os.path.join(tmp, "config.json")
        # Include an explicit devops section with a dummy account/region so the
        # factory never depends on ambient AWS_ACCOUNT/DEVOPS_AWS_ACCOUNT/
        # CDK_DEFAULT_ACCOUNT env vars. This keeps the test self-contained and
        # credential-free (no live AWS; the dummy account is never contacted).
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "workload": {
                        "name": "test-workload",
                        "devops": {
                            "account": "123456789012",
                            "region": "us-east-1",
                        },
                        "stacks": [],
                    }
                },
                f,
            )
        factory = WorkloadFactory(
            app=app,
            config_path=config_path,
            runtime_directory=tmp,
            add_env_context=False,
        )
    return factory


def _build_stack_deployment(stack_dicts) -> DeploymentConfig:
    deployment_dict = {
        "name": "test-stack-deployment",
        "mode": "stack",
        "enabled": True,
        "account": "123456789012",
        "region": "us-east-1",
        "environment": "test",
        "stacks": stack_dicts,
    }
    return DeploymentConfig(workload=WORKLOAD_DICT, deployment=deployment_dict)


def _run_build(stack_dicts):
    """Build the given stacks via the FEAT-001 code path and return the built
    {name: aws_cdk.Stack} map by reading back from the deployment stacks."""
    factory = _build_workload_factory()
    deployment = _build_stack_deployment(stack_dicts)
    # Name-mangled access to the private method under test.
    factory._WorkloadFactory__build_stacks(deployment)

    # The built aws_cdk.Stack objects are the app's children keyed by stack name.
    built = {}
    for child in factory.app.node.children:
        node_id = child.node.id
        built[node_id] = child
    return built


class TestStackModeDependsOn:
    """All five FEAT-001 / DESIGN 8.1 cases."""

    def test_positive_dependency_wired(self):
        """(positive) A_stack appears in B_stack.dependencies after the fix.

        This assertion is red before the fix (no wiring) and green after.
        """
        stack_a = _make_secrets_stack_dict("stack-a")
        stack_b = _make_secrets_stack_dict("stack-b", depends_on=["stack-a"])
        built = _run_build([stack_a, stack_b])

        a = built["stack-a"]
        b = built["stack-b"]
        assert a in b.dependencies

    def test_single_wire_exactly_once(self):
        """(single-wire) B depends on A exactly once."""
        stack_a = _make_secrets_stack_dict("stack-a")
        stack_b = _make_secrets_stack_dict("stack-b", depends_on=["stack-a"])
        built = _run_build([stack_a, stack_b])

        a = built["stack-a"]
        b = built["stack-b"]
        assert b.dependencies.count(a) == 1

    def test_negative_control_no_depends_on(self):
        """(negative control) no depends_on -> no dependency wired."""
        stack_a = _make_secrets_stack_dict("stack-a")
        stack_b = _make_secrets_stack_dict("stack-b")
        built = _run_build([stack_a, stack_b])

        a = built["stack-a"]
        b = built["stack-b"]
        assert a not in b.dependencies
        assert b not in a.dependencies

    def test_non_list_depends_on_raises_value_error(self):
        """(non-list depends_on) a string value raises ValueError from
        StackConfig.dependencies."""
        bad = StackConfig(
            stack=_make_secrets_stack_dict("stack-bad", depends_on="stack-a"),
            workload=WORKLOAD_DICT,
        )
        with pytest.raises(ValueError, match="depends_on must be a list of strings"):
            _ = bad.dependencies

    def test_ordering_agnostic(self):
        """(ordering agnosticism) declare B before A in stacks[] and assert the
        dependency still wires, proving the two-pass build-then-wire structure."""
        stack_b = _make_secrets_stack_dict("stack-b", depends_on=["stack-a"])
        stack_a = _make_secrets_stack_dict("stack-a")
        # B declared BEFORE A on purpose.
        built = _run_build([stack_b, stack_a])

        a = built["stack-a"]
        b = built["stack-b"]
        assert a in b.dependencies
