"""Producer-side import-graph guard (design §2.11, AC-10 / NFR-2).

Asserts that importing ``cdk_factory.commands.deployment_command`` (the module
on the synth/Lambda-adjacent path) does NOT transitively pull
``cdk_factory.wizard``, ``questionary``, or ``rich``. The lazy-import boundary
(run_wizard / main()'s monitor branch) is what keeps those operator-only deps
off the synth path; if that regresses, the poisoned import below fails and the
subprocess exits non-zero.
"""

import subprocess
import sys


_PREAMBLE = r"""
import sys
import importlib.abc
import importlib.machinery

# Poison questionary/rich so any eager import of them blows up.
sys.modules["questionary"] = None
sys.modules["rich"] = None


class _WizardBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "cdk_factory.wizard" or fullname.startswith("cdk_factory.wizard."):
            raise ImportError(
                f"cdk_factory.wizard must NOT be imported on the synth path: {fullname}"
            )
        return None


sys.meta_path.insert(0, _WizardBlocker())

import cdk_factory.commands.deployment_command  # noqa: F401

print("clean")
"""


def test_deployment_command_import_clean_of_wizard_deps():
    result = subprocess.run(
        [sys.executable, "-c", _PREAMBLE],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Importing cdk_factory.commands.deployment_command pulled a poisoned "
        f"wizard dependency.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "clean" in result.stdout
