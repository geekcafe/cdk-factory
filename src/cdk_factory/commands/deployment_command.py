"""
CdkDeploymentCommand — generic base class for local / CI deployment scripts.

Projects subclass this, define their ``environments`` and ``required_vars``,
and get env-file loading, env-var propagation, validation, and CDK
synth/deploy/diff for free.

Usage::

    from cdk_factory.commands.deployment_command import CdkDeploymentCommand, EnvironmentConfig

    class MyDeployment(CdkDeploymentCommand):
        @property
        def environments(self):
            return {
                'prod': EnvironmentConfig('prod', '.env.deploy.prod', 'main'),
                'dev':  EnvironmentConfig('dev',  '.env.deploy.dev',  'develop'),
            }

        @property
        def required_vars(self):
            return [
                ('AWS_ACCOUNT', 'AWS Account ID'),
                ('ECR_REPOSITORY_NAME', 'ECR Repository Name'),
            ]

    if __name__ == '__main__':
        MyDeployment.main()
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentConfig:
    """Describes one deployment environment (e.g., dev, uat, prod)."""

    name: str
    env_file: str
    git_branch: str
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Base command
# ---------------------------------------------------------------------------


class CdkDeploymentCommand:
    """
    Generic base class for CDK deployment commands.

    Subclasses must implement :py:attr:`environments` and may optionally
    override :py:attr:`required_vars` and
    :py:meth:`display_configuration_summary`.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, script_dir: Optional[Path] = None):
        """
        Args:
            script_dir: Directory that contains the deploy script and ``.env``
                files.  Defaults to the current working directory.
        """
        self.script_dir: Path = script_dir or Path.cwd()

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @property
    def environments(self) -> Dict[str, EnvironmentConfig]:
        """Return a mapping of environment name → :class:`EnvironmentConfig`.

        Subclasses *must* override this.
        """
        raise NotImplementedError("Subclasses must define `environments`.")

    @property
    def required_vars(self) -> List[Tuple[str, str]]:
        """Return a list of ``(VAR_NAME, description)`` tuples to validate.

        The base implementation checks the four most-common variables.
        Subclasses may override or extend this list.
        """
        return [
            ("AWS_ACCOUNT", "AWS Account ID"),
            ("AWS_REGION", "AWS Region"),
            ("AWS_PROFILE", "AWS CLI Profile"),
            ("WORKLOAD_NAME", "Workload Name"),
        ]

    def display_configuration_summary(self, config_file: str) -> None:
        """Print a deployment summary.  Override for project-specific output."""
        self._print("", "white")
        self._print("Configuration Summary", "blue")
        self._print(f"  Config file : {config_file}", "white")
        self._print(f"  Environment : {os.environ.get('ENVIRONMENT', 'N/A')}", "white")
        self._print(f"  AWS Account : {os.environ.get('AWS_ACCOUNT', 'N/A')}", "white")
        self._print(f"  AWS Region  : {os.environ.get('AWS_REGION', 'N/A')}", "white")
        self._print(f"  Git Branch  : {os.environ.get('GIT_BRANCH', 'N/A')}", "white")
        self._print("", "white")

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    def load_env_file(self, env_file: str) -> Dict[str, str]:
        """Load ``KEY=VALUE`` pairs from *env_file* (relative to script_dir)."""
        env_path = self.script_dir / env_file
        if not env_path.exists():
            self._print(f"Configuration file '{env_file}' not found!", "red")
            self._print("", "white")
            self._print(f"  1. Copy an example file and edit it:", "white")
            self._print(f"     cp .env.deploy.example {env_file}", "white")
            self._print(f"  2. Run this script again.", "white")
            self._print("Note: .env files should be in .gitignore", "yellow")
            sys.exit(1)

        self._print(f"Loading configuration from {env_file}...", "blue")
        env_vars: Dict[str, str] = {}
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip("\"'")
        return env_vars

    def set_environment_variables(
        self,
        env_config: EnvironmentConfig,
        env_vars: Dict[str, str],
    ) -> None:
        """Apply environment defaults then override with values from *env_vars*.

        After merging, every value that references another env var
        (``$VAR_NAME`` or ``${VAR_NAME}``) is expanded.
        """
        # Defaults from the EnvironmentConfig
        os.environ.setdefault("ENVIRONMENT", env_config.name)
        os.environ.setdefault("GIT_BRANCH", env_config.git_branch)

        # Values from the env file take precedence
        for key, value in env_vars.items():
            os.environ[key] = value

        # Common alias mappings (env file values already set above)
        _aliases = {
            "WORKLOAD_NAME": "CDK_WORKLOAD_NAME",
            "AWS_ACCOUNT": "AWS_ACCOUNT_NUMBER",
            "AWS_REGION": "DEVOPS_REGION",
        }
        for src, dst in _aliases.items():
            if src in os.environ and dst not in os.environ:
                os.environ[dst] = os.environ[src]

        # Expand variable references (e.g. VALUE=${OTHER_VAR}-suffix)
        for key in list(os.environ.keys()):
            original = os.environ[key]
            expanded = os.path.expandvars(original)
            if expanded != original:
                os.environ[key] = expanded

    def validate_required_variables(self) -> None:
        """Raise SystemExit if any required variable is missing or placeholder."""
        self._print("Validating configuration...", "blue")
        missing = [
            f"  - {name} ({desc})"
            for name, desc in self.required_vars
            if not os.environ.get(name) or os.environ[name].startswith("YOUR_")
        ]
        if missing:
            self._print("Missing required configuration variables:", "red")
            for m in missing:
                print(m)
            self._print("Please update your environment file.", "yellow")
            sys.exit(1)
        self._print("Configuration validated", "green")

    # ------------------------------------------------------------------
    # CDK operations
    # ------------------------------------------------------------------

    def run_cdk_synth(self, config_file: str) -> None:
        """Run ``python3 app.py --config <config_file>`` in script_dir."""
        self._print("Running CDK synthesis...", "blue")
        self._run(["python3", "app.py", "--config", config_file])
        self._print("CDK synthesis completed successfully", "green")

    def run_cdk_deploy(self, config_file: str) -> None:
        """Synthesise then deploy all stacks."""
        self.run_cdk_synth(config_file)
        self._print("Running CDK deployment...", "blue")
        self._run(
            [
                "cdk",
                "deploy",
                "--all",
                "--require-approval",
                "never",
                "--app",
                f"python3 app.py --config {config_file}",
            ]
        )
        self._print("CDK deployment completed successfully", "green")

    def run_cdk_diff(self, config_file: str) -> None:
        """Synthesise then diff all stacks."""
        self.run_cdk_synth(config_file)
        self._print("Running CDK diff...", "blue")
        self._run(["cdk", "diff", "--all"])
        self._print("CDK diff completed successfully", "green")

    def run_cdk_destroy(self, config_file: str) -> None:
        """Destroy all stacks."""
        self._print("Running CDK destroy...", "red")
        self._run(
            [
                "cdk",
                "destroy",
                "--all",
                "--force",
                "--app",
                f"python3 app.py --config {config_file}",
            ]
        )
        self._print("CDK destroy completed successfully", "green")

    # ------------------------------------------------------------------
    # Interactive helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _interactive_select(title: str, options: List[str]) -> int:
        """Present an arrow-key scrollable menu if possible, else numbered fallback.

        Returns the 0-based index of the selected option.
        """
        try:
            from simple_term_menu import TerminalMenu

            menu = TerminalMenu(options, title=title)
            idx = menu.show()
            if idx is None:
                # User pressed Escape / Ctrl-C
                print("\nAborted.")
                sys.exit(1)
            return idx
        except ImportError:
            # Fallback: numbered list
            print(title)
            for i, opt in enumerate(options, 1):
                print(f"  {i}) {opt}")
            raw = input(f"Enter choice [default 1]: ").strip() or "1"
            try:
                return int(raw) - 1
            except (ValueError, IndexError):
                print("Invalid choice.")
                sys.exit(1)

    def select_environment(self) -> EnvironmentConfig:
        """Prompt the user to select an environment (arrow-key menu)."""
        envs = self.environments
        keys = list(envs.keys())
        options = [key for key in keys]
        idx = self._interactive_select("Select deployment environment:", options)
        name = keys[idx]
        self._print(f"Using {name.upper()} environment...", "blue")
        return envs[name]

    def select_operation(self) -> str:
        """Prompt the user to select synth / deploy / diff (arrow-key menu)."""
        ops = ["synth", "deploy", "diff", "destroy"]
        idx = self._interactive_select("Select operation:", ops)
        op = ops[idx]
        self._print(f"Using {op.upper()}...", "blue")
        return op

    def select_config_file(self, config_files: Optional[Dict[str, Dict]] = None) -> str:
        """Prompt the user to select a config file.

        Args:
            config_files: Mapping of ``"1"`` → ``{"name": "...", "file": "..."}``
                dicts.  Defaults to a single ``config.json`` option.
        """
        if not config_files:
            return "config.json"

        self._print("Select configuration:", "blue")
        for key, info in config_files.items():
            print(f"  {key}) {info['name']}")
        raw = input("Enter choice [default 1]: ").strip() or "1"
        info = config_files.get(raw, config_files.get("1"))
        self._print(f"Using {info['name']}...", "blue")
        return info["file"]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        config_file: Optional[str] = None,
        environment_name: Optional[str] = None,
        operation: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """Execute the full deployment flow.

        Args:
            config_file: Path to config JSON.  Prompts if None.
            environment_name: Pre-selected environment name.  Prompts if None.
            operation: ``"synth"``, ``"deploy"``, ``"diff"``, or ``"destroy"``.  Prompts if None.
            dry_run: Validate and display config without running CDK.
        """
        # Select environment
        if environment_name:
            if environment_name not in self.environments:
                self._print(f"Unknown environment '{environment_name}'.", "red")
                sys.exit(1)
            env_config = self.environments[environment_name]
            self._print(f"Using {environment_name.upper()} environment...", "blue")
        else:
            env_config = self.select_environment()

        # Load and apply env file
        env_vars = self.load_env_file(env_config.env_file)
        self.set_environment_variables(env_config, env_vars)

        # Select config file
        selected_config = config_file or "config.json"

        # Select operation
        selected_op = operation or self.select_operation()

        # Validate
        self.validate_required_variables()

        # Summary
        self.display_configuration_summary(selected_config)

        if dry_run:
            self._print("Dry run — skipping CDK execution.", "yellow")
            return

        # Execute
        if selected_op == "synth":
            self.run_cdk_synth(selected_config)
            self._print("To deploy: cdk deploy --all --require-approval never", "blue")
        elif selected_op == "deploy":
            self.run_cdk_deploy(selected_config)
        elif selected_op == "diff":
            self.run_cdk_diff(selected_config)
            self._print("To apply: cdk deploy --all --require-approval never", "blue")
        elif selected_op == "destroy":
            self.run_cdk_destroy(selected_config)

    @classmethod
    def main(cls) -> None:
        """Parse args and run.  Call as ``MyCommand.main()`` from ``__main__``."""
        instance = cls()
        env_choices = list(instance.environments.keys())

        parser = argparse.ArgumentParser(
            description=f"CDK Deployment Command ({cls.__name__})"
        )
        parser.add_argument("--config", "-c", help="Configuration file to use")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate configuration without running CDK",
        )
        parser.add_argument(
            "--environment",
            "-e",
            choices=env_choices,
            help="Skip environment selection prompt",
        )
        parser.add_argument(
            "--operation",
            "-o",
            choices=["synth", "deploy", "diff", "destroy"],
            help="Skip operation selection prompt",
        )
        args = parser.parse_args()

        try:
            instance.run(
                config_file=args.config,
                environment_name=args.environment,
                operation=args.operation,
                dry_run=args.dry_run,
            )
        except KeyboardInterrupt:
            print()
            instance._print("Deployment cancelled by user.", "yellow")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _print(self, message: str, color: str = "white") -> None:
        _colors = {
            "red": "\033[0;31m",
            "green": "\033[0;32m",
            "yellow": "\033[0;33m",
            "blue": "\033[0;34m",
            "cyan": "\033[0;36m",
            "white": "\033[0m",
        }
        prefix = {"red": "✗ ", "green": "✓ ", "yellow": "⚠ ", "blue": "ℹ "}.get(
            color, ""
        )
        code = _colors.get(color, _colors["white"])
        reset = _colors["white"]
        print(f"{code}{prefix}{message}{reset}")

    def _run(self, cmd: List[str]) -> None:
        """Run *cmd* in script_dir, streaming output.  Raises SystemExit on failure."""
        try:
            result = subprocess.run(cmd, cwd=self.script_dir, env=os.environ.copy())
            if result.returncode != 0:
                self._print(f"Command failed: {' '.join(cmd)}", "red")
                sys.exit(result.returncode)
        except FileNotFoundError:
            self._print(f"Command not found: {cmd[0]}", "red")
            sys.exit(1)
