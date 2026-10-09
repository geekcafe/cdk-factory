"""
Unit tests for cross-platform Lambda dependency packaging.

These cover the packaging fix that shrinks the synth artifact:
  * the pip install command targets Linux (manylinux) wheels for the configured
    runtime/architecture (so native .so files are correct on any build host);
  * runtime-provided packages (boto3/botocore) are pruned from the install
    target after install, with a config-overridable exclusion set;
  * a package with no manylinux wheel triggers a relaxed (sdist-allowed) retry.

The actual ``subprocess.check_call`` is never invoked — the ``_run_pip_install``
seam is monkeypatched to capture argv — so no real install runs.
"""

import os
import subprocess

import pytest
from aws_cdk import aws_lambda

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.utilities.lambda_function_utilities import (
    DEFAULT_RUNTIME_PROVIDED_PACKAGES,
    LambdaFunctionUtilities,
)


@pytest.fixture
def utilities():
    deployment = DeploymentConfig(
        workload={"name": "test-workload"},
        deployment={
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
        },
    )
    workload = WorkloadConfig(config={"name": "test-workload", "devops": {"name": "d"}})
    return LambdaFunctionUtilities(deployment=deployment, workload=workload)


class TestBuildPipInstallCommand:
    def test_strict_wheel_only_command_contains_linux_flags(self):
        cmd = LambdaFunctionUtilities._build_pip_install_command(
            "req.txt",
            "/tmp/target",
            python_version="3.12",
            platform_tag="manylinux2014_x86_64",
            only_binary=True,
        )
        assert cmd[:4] == ["pip", "install", "-r", "req.txt"]
        assert "--target" in cmd and cmd[cmd.index("--target") + 1] == "/tmp/target"
        assert "--platform" in cmd
        assert cmd[cmd.index("--platform") + 1] == "manylinux2014_x86_64"
        assert "--implementation" in cmd
        assert cmd[cmd.index("--implementation") + 1] == "cp"
        assert "--python-version" in cmd
        assert cmd[cmd.index("--python-version") + 1] == "3.12"
        assert "--only-binary=:all:" in cmd

    def test_relaxed_command_omits_only_binary(self):
        cmd = LambdaFunctionUtilities._build_pip_install_command(
            "req.txt",
            "/tmp/target",
            python_version="3.11",
            platform_tag="manylinux2014_aarch64",
            only_binary=False,
        )
        assert "--only-binary=:all:" not in cmd
        # Platform/python targeting is preserved even on the relaxed retry.
        assert cmd[cmd.index("--platform") + 1] == "manylinux2014_aarch64"
        assert cmd[cmd.index("--python-version") + 1] == "3.11"


class TestRunPipInstallSeam:
    def test_skip_pip_env_skips_subprocess(self, utilities, monkeypatch):
        called = {"n": 0}

        def fake_check_call(cmd):  # pragma: no cover - should not run
            called["n"] += 1

        monkeypatch.setattr(subprocess, "check_call", fake_check_call)
        monkeypatch.setenv("SKIP_PIP", "1")
        utilities._run_pip_install(["pip", "install", "-r", "req.txt"])
        assert called["n"] == 0

    def test_runs_subprocess_without_skip(self, utilities, monkeypatch):
        captured = {}

        def fake_check_call(cmd):
            captured["cmd"] = cmd

        monkeypatch.setattr(subprocess, "check_call", fake_check_call)
        monkeypatch.delenv("SKIP_PIP", raising=False)
        utilities._run_pip_install(["pip", "install", "-r", "req.txt"])
        assert captured["cmd"] == ["pip", "install", "-r", "req.txt"]


class TestPipInstallRequirementFallback:
    def test_wheel_only_success_no_retry(self, utilities, monkeypatch):
        calls = []
        monkeypatch.setattr(utilities, "_run_pip_install", lambda cmd: calls.append(cmd))
        utilities._pip_install_requirement(
            "req.txt", "/tmp/target", python_version="3.12", platform_tag="manylinux2014_x86_64"
        )
        assert len(calls) == 1
        assert "--only-binary=:all:" in calls[0]

    def test_sdist_fallback_on_called_process_error(self, utilities, monkeypatch):
        calls = []

        def fake_run(cmd):
            calls.append(cmd)
            # First (strict) call fails to simulate a package with no manylinux wheel.
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(utilities, "_run_pip_install", fake_run)
        utilities._pip_install_requirement(
            "req.txt", "/tmp/target", python_version="3.12", platform_tag="manylinux2014_x86_64"
        )
        assert len(calls) == 2
        assert "--only-binary=:all:" in calls[0]
        assert "--only-binary=:all:" not in calls[1]
        # Linux targeting preserved on the retry.
        assert calls[1][calls[1].index("--platform") + 1] == "manylinux2014_x86_64"


def _make_installed_target(tmp_path):
    """Create a simulated pip install target dir with boto3/botocore + a kept pkg."""
    target = tmp_path / "target"
    target.mkdir()
    for pkg in ("boto3", "botocore", "httpx"):
        (target / pkg).mkdir()
        (target / pkg / "__init__.py").write_text("")
    # dist-info metadata (varied naming / version suffixes).
    (target / "boto3-1.34.0.dist-info").mkdir()
    (target / "botocore-1.34.0.dist-info").mkdir()
    (target / "httpx-0.27.0.dist-info").mkdir()
    return target


class TestPruneRuntimeProvidedPackages:
    def test_default_prunes_boto3_botocore_keeps_others(self, tmp_path):
        target = _make_installed_target(tmp_path)
        LambdaFunctionUtilities._prune_runtime_provided_packages(
            str(target), DEFAULT_RUNTIME_PROVIDED_PACKAGES
        )
        assert not (target / "boto3").exists()
        assert not (target / "botocore").exists()
        assert not (target / "boto3-1.34.0.dist-info").exists()
        assert not (target / "botocore-1.34.0.dist-info").exists()
        # Non-runtime packages are untouched.
        assert (target / "httpx").exists()
        assert (target / "httpx-0.27.0.dist-info").exists()

    def test_config_override_changes_prune_set(self, tmp_path):
        target = _make_installed_target(tmp_path)
        # Override: only prune httpx; keep boto3/botocore.
        LambdaFunctionUtilities._prune_runtime_provided_packages(str(target), ["httpx"])
        assert not (target / "httpx").exists()
        assert not (target / "httpx-0.27.0.dist-info").exists()
        assert (target / "boto3").exists()
        assert (target / "botocore").exists()

    def test_empty_exclude_list_prunes_nothing(self, tmp_path):
        target = _make_installed_target(tmp_path)
        LambdaFunctionUtilities._prune_runtime_provided_packages(str(target), [])
        assert (target / "boto3").exists()
        assert (target / "botocore").exists()
        assert (target / "httpx").exists()

    def test_idempotent_on_missing_dir(self, tmp_path):
        # Should not raise when target dir does not exist.
        LambdaFunctionUtilities._prune_runtime_provided_packages(
            str(tmp_path / "does-not-exist"), DEFAULT_RUNTIME_PROVIDED_PACKAGES
        )

    def test_idempotent_when_already_pruned(self, tmp_path):
        target = _make_installed_target(tmp_path)
        LambdaFunctionUtilities._prune_runtime_provided_packages(
            str(target), DEFAULT_RUNTIME_PROVIDED_PACKAGES
        )
        # Running again is a no-op (does not raise).
        LambdaFunctionUtilities._prune_runtime_provided_packages(
            str(target), DEFAULT_RUNTIME_PROVIDED_PACKAGES
        )
        assert not (target / "boto3").exists()


class TestExcludePackagesConfig:
    def test_absent_key_returns_none_for_default(self):
        cfg = LambdaFunctionConfig({"name": "fn"})
        assert cfg.exclude_packages is None

    def test_explicit_list_returned(self):
        cfg = LambdaFunctionConfig({"name": "fn", "exclude_packages": ["boto3"]})
        assert cfg.exclude_packages == ["boto3"]

    def test_empty_list_opts_out(self):
        cfg = LambdaFunctionConfig({"name": "fn", "exclude_packages": []})
        assert cfg.exclude_packages == []

    def test_non_list_raises(self):
        cfg = LambdaFunctionConfig({"name": "fn", "exclude_packages": "boto3"})
        with pytest.raises(ValueError):
            _ = cfg.exclude_packages


class TestDependenciesToLayerDefault:
    def test_absent_key_defaults_false(self):
        cfg = LambdaFunctionConfig({"name": "fn"})
        assert cfg.dependencies_to_layer is False

    def test_true_string(self):
        cfg = LambdaFunctionConfig({"name": "fn", "dependencies_to_layer": "true"})
        assert cfg.dependencies_to_layer is True

    def test_false_string(self):
        cfg = LambdaFunctionConfig({"name": "fn", "dependencies_to_layer": "false"})
        assert cfg.dependencies_to_layer is False
