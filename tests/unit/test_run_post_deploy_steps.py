"""
Unit tests for CdkDeploymentCommand.run_post_deploy_steps (FEAT-002, DESIGN 8.2).

The runner replays pipeline-defined ``post_steps`` locally after a stack-mode
deploy. It hand-rolls ``subprocess.run`` (exactly one call site per enabled
step) rather than calling ``self._run``, so these tests patch the module-level
``subprocess.run`` in ``deployment_command`` and count/inspect invocations.

No AWS, no MagicMock for AWS resources — the fake just records bash invocations.
"""

import json

import pytest

from cdk_factory.commands import deployment_command
from cdk_factory.commands.deployment_command import CdkDeploymentCommand


# A config.json with ONE pipeline deployment whose single stage has:
#   builds[0]  enabled=true  -> post_steps[0] (one enabled step w/ commands)
#                            -> post_steps[1] (disabled step)
#                            -> post_steps[2] (SECOND enabled step, fail-fast)
#                            -> post_steps[3] (no-commands source/buildspec step)
#   builds[1]  enabled=false -> post_steps[0] (should never run)
def _config_dict() -> dict:
    return {
        "workload": {
            "name": "test-workload",
            "deployments": [
                {
                    "name": "pipeline-deployment",
                    "pipeline": {
                        "stages": [
                            {
                                "name": "assert-stage",
                                "builds": [
                                    {
                                        "name": "enabled-build",
                                        "enabled": True,
                                        "post_steps": [
                                            {
                                                "id": "first-step",
                                                "name": "First Step",
                                                "commands": [
                                                    "export AWS_REGION={{AWS_REGION}}",
                                                    "echo hello $AWS_REGION",
                                                ],
                                            },
                                            {
                                                "id": "disabled-step",
                                                "name": "Disabled Step",
                                                "enabled": False,
                                                "commands": ["echo should-not-run"],
                                            },
                                            {
                                                "id": "second-step",
                                                "name": "Second Step",
                                                "commands": ["echo second"],
                                            },
                                            {
                                                "id": "buildspec-step",
                                                "name": "Buildspec Step",
                                                "source": "some-repo",
                                                "buildspec": "buildspec.yml",
                                            },
                                        ],
                                    },
                                    {
                                        "name": "disabled-build",
                                        "enabled": False,
                                        "post_steps": [
                                            {
                                                "id": "in-disabled-build",
                                                "name": "In Disabled Build",
                                                "commands": ["echo nope"],
                                            }
                                        ],
                                    },
                                ],
                            }
                        ]
                    },
                }
            ],
        }
    }


class _FakeCompleted:
    def __init__(self, returncode: int):
        self.returncode = returncode


class _FakeRun:
    """Records subprocess.run calls and returns a configurable returncode."""

    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.calls = []

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((cmd, args, kwargs))
        return _FakeCompleted(self.returncode)


def _make_command(tmp_path, config: dict) -> CdkDeploymentCommand:
    """Build a CdkDeploymentCommand rooted at a temp dir with the given config."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return CdkDeploymentCommand(script_dir=tmp_path)


@pytest.fixture(autouse=True)
def _region_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")


def test_happy_path_runs_single_enabled_step(tmp_path, monkeypatch, capsys):
    """Exactly ONE enabled step runs; placeholders resolve; disabled skipped.

    Note: 'second-step' is also enabled, so with a succeeding fake BOTH enabled
    steps run. To assert the single-step shape the config's second step is
    temporarily removed here.
    """
    config = _config_dict()
    # Keep only the first (enabled) step + disabled step + no-commands step to
    # isolate the "one enabled command step" assertion.
    steps = config["workload"]["deployments"][0]["pipeline"]["stages"][0]["builds"][0][
        "post_steps"
    ]
    del steps[2]  # drop the second enabled step for this isolation test

    cmd = _make_command(tmp_path, config)
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    cmd.run_post_deploy_steps("config.json")

    # Exactly one bash invocation (the single enabled command step).
    assert len(fake.calls) == 1
    invoked_cmd = fake.calls[0][0]
    assert invoked_cmd[:4] == ["bash", "-euo", "pipefail", "-c"]
    script = invoked_cmd[4]
    # {{AWS_REGION}} resolved from os.environ.
    assert "export AWS_REGION=us-west-2" in script
    assert "{{AWS_REGION}}" not in script
    assert "echo hello $AWS_REGION" in script

    out = capsys.readouterr().out
    # No-commands step produced a skip warning.
    assert "buildspec-step" in out
    assert "cannot replay locally" in out
    # Disabled step not mentioned as running.
    assert "should-not-run" not in script


def test_fail_fast_stops_later_steps(tmp_path, monkeypatch, capsys):
    """A non-zero returncode exits with that code; later enabled step never runs."""
    config = _config_dict()
    cmd = _make_command(tmp_path, config)
    fake = _FakeRun(returncode=7)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    with pytest.raises(SystemExit) as excinfo:
        cmd.run_post_deploy_steps("config.json")

    assert excinfo.value.code == 7
    # Only the FIRST enabled step ran — fail-fast prevented the second.
    assert len(fake.calls) == 1

    out = capsys.readouterr().out
    # Red failure line names the failing step id/name.
    assert "first-step" in out
    assert "First Step" in out
    # The later enabled step never printed a running line.
    assert "second-step" not in out


def test_no_commands_step_skipped_with_warning(tmp_path, monkeypatch, capsys):
    """A source/buildspec step (no commands) is skipped with a yellow warning."""
    config = {
        "workload": {
            "name": "test-workload",
            "deployments": [
                {
                    "name": "pipeline-deployment",
                    "pipeline": {
                        "stages": [
                            {
                                "name": "s",
                                "builds": [
                                    {
                                        "name": "b",
                                        "enabled": True,
                                        "post_steps": [
                                            {
                                                "id": "only-buildspec",
                                                "name": "Only Buildspec",
                                                "source": "repo",
                                                "buildspec": "buildspec.yml",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                }
            ],
        }
    }
    cmd = _make_command(tmp_path, config)
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    cmd.run_post_deploy_steps("config.json")

    # No subprocess invocation at all.
    assert len(fake.calls) == 0
    out = capsys.readouterr().out
    assert "only-buildspec" in out
    assert "cannot replay locally" in out


def test_missing_config_returns_cleanly(tmp_path, monkeypatch, capsys):
    """A missing config file prints the note and returns (no crash)."""
    cmd = CdkDeploymentCommand(script_dir=tmp_path)  # no config.json written
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    cmd.run_post_deploy_steps("config.json")

    assert len(fake.calls) == 0
    out = capsys.readouterr().out
    assert "No post_steps found" in out


def test_malformed_config_returns_cleanly(tmp_path, monkeypatch, capsys):
    """A malformed config file prints the note and returns (no crash)."""
    (tmp_path / "config.json").write_text("{ not json", encoding="utf-8")
    cmd = CdkDeploymentCommand(script_dir=tmp_path)
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    cmd.run_post_deploy_steps("config.json")

    assert len(fake.calls) == 0
    out = capsys.readouterr().out
    assert "No post_steps found" in out


def test_no_pipeline_deployment_returns_cleanly(tmp_path, monkeypatch, capsys):
    """A config with no pipeline stages prints the note and returns."""
    config = {
        "workload": {
            "name": "test-workload",
            "deployments": [{"name": "stack-only", "mode": "stack", "stacks": []}],
        }
    }
    cmd = _make_command(tmp_path, config)
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(deployment_command.subprocess, "run", fake)

    cmd.run_post_deploy_steps("config.json")

    assert len(fake.calls) == 0
    out = capsys.readouterr().out
    assert "No post_steps found" in out
