"""
Shape-level unit test for the monitoring stack-mode config (FEAT-002, DESIGN 8.4).

Resolves a representative config (a pipeline deployment gated
``enabled={{PIPELINE_ENABLED}}`` and a stack deployment gated
``enabled={{STACK_ENABLED}}`` whose ``stacks[]`` use ``__inherits__`` + a
``depends_on`` sibling) through ``CdkConfig``/``JsonLoadingUtility`` with
``STACK_ENABLED=true``/``PIPELINE_ENABLED=false`` and asserts:

  (a) only the stack deployment is enabled,
  (b) the inherited stack names + depends_on resolved,
  (c) ``__inherits__`` was expanded under ``deployment.stacks``.

This is a consumer-shaped fixture living under cdk-factory tests/unit/files/
(not a reach into the consumer repo). No AWS.
"""

import os
import shutil
from pathlib import Path

import pytest

from cdk_factory.configurations.cdk_config import CdkConfig
from cdk_factory.configurations.deployment import DeploymentConfig


_FIXTURE_DIR = Path(__file__).parent / "files" / "monitoring_stack_mode"


@pytest.fixture
def resolved_config(tmp_path, monkeypatch):
    """Copy the fixture tree into a temp dir and resolve it via CdkConfig.

    Copying keeps the generated ``.dynamic/`` artifacts out of the repo. The
    gate env vars select stack mode.
    """
    # Copy fixture tree (config.json + stacks/) into tmp.
    dst = tmp_path / "monitoring_stack_mode"
    shutil.copytree(_FIXTURE_DIR, dst)

    monkeypatch.setenv("STACK_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_ENABLED", "false")
    monkeypatch.setenv("DEPLOYMENT_MODE", "stack")
    monkeypatch.setenv("WORKLOAD_NAME", "geekcafe-devops-monitoring")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    cdk_config = CdkConfig(
        config_path="config.json",
        cdk_context={},
        runtime_directory=str(dst),
    )
    return cdk_config.config


def _deployments(config: dict) -> list:
    return config.get("workload", {}).get("deployments", [])


def test_only_stack_deployment_enabled(resolved_config):
    """(a) STACK_ENABLED=true / PIPELINE_ENABLED=false => only stack enabled."""
    workload = resolved_config["workload"]
    deployments = _deployments(resolved_config)
    assert len(deployments) == 2

    by_mode = {}
    for d in deployments:
        dc = DeploymentConfig(workload=workload, deployment=d)
        by_mode[d.get("mode", "pipeline")] = dc.enabled

    assert by_mode["stack"] is True
    assert by_mode["pipeline"] is False


def test_inherits_expanded_under_deployment_stacks(resolved_config):
    """(c) __inherits__ expanded: the stack deployment has concrete stacks[]."""
    deployments = _deployments(resolved_config)
    stack_dep = next(d for d in deployments if d.get("mode") == "stack")

    stacks = stack_dep.get("stacks", [])
    assert len(stacks) == 2
    for stack in stacks:
        # __inherits__ key must be popped during resolution.
        assert "__inherits__" not in stack
        # Inherited content merged in (module came from the inherited file).
        assert "module" in stack
        assert "name" in stack


def test_inherited_names_and_depends_on_resolved(resolved_config):
    """(b) inherited names + depends_on resolved to concrete values."""
    workload = resolved_config["workload"]
    deployments = _deployments(resolved_config)
    stack_dep = next(d for d in deployments if d.get("mode") == "stack")

    dc = DeploymentConfig(workload=workload, deployment=stack_dep)
    stack_configs = dc.stacks
    names = [sc.name for sc in stack_configs]

    secrets_name = "geekcafe-devops-monitoring-prod-codepipeline-notifier-secrets"
    notifier_name = "geekcafe-devops-monitoring-prod-codepipeline-notifier"

    assert secrets_name in names
    assert notifier_name in names
    # No unresolved placeholders survived.
    for name in names:
        assert "{{" not in name

    # The notifier stack declares a resolved depends_on on the secrets stack.
    notifier = next(sc for sc in stack_configs if sc.name == notifier_name)
    assert notifier.dependencies == [secrets_name]
