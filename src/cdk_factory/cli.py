#!/usr/bin/env python3
"""
CDK Factory CLI

Provides convenience commands for initializing and managing cdk-factory projects.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cdk_factory.bootstrap import needs_install


class CdkFactoryCLI:
    """CLI for cdk-factory project management"""

    def __init__(self):
        self.package_root = Path(__file__).parent.resolve()
        self.templates_dir = self.package_root / "templates"

        # Verify templates directory exists
        if not self.templates_dir.exists():
            raise RuntimeError(
                f"Templates directory not found at {self.templates_dir}. "
                "Please ensure cdk-factory is properly installed."
            )

    def init_project(
        self,
        target_dir: str,
        workload_name: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> None:
        """
        Initialize a new cdk-factory project

        Args:
            target_dir: Directory to initialize (e.g., devops/cdk-iac)
            workload_name: Name of the workload (optional)
            environment: Environment name (optional)
        """
        target_path = Path(target_dir).resolve()

        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created directory: {target_path}")

        # Copy app.py template
        app_template = self.templates_dir / "app.py.template"
        app_dest = target_path / "app.py"

        if app_dest.exists():
            response = input(f"⚠️  {app_dest} already exists. Overwrite? (y/N): ")
            if response.lower() != "y":
                print("Skipped app.py")
            else:
                shutil.copy(app_template, app_dest)
                print(f"✅ Created {app_dest}")
        else:
            shutil.copy(app_template, app_dest)
            print(f"✅ Created {app_dest}")

        # Copy cdk.json template
        cdk_json_template = self.templates_dir / "cdk.json.template"
        cdk_json_dest = target_path / "cdk.json"

        if cdk_json_dest.exists():
            print(f"⚠️  {cdk_json_dest} already exists. Skipping.")
        else:
            shutil.copy(cdk_json_template, cdk_json_dest)
            print(f"✅ Created {cdk_json_dest}")

        # Create minimal config.json
        config_dest = target_path / "config.json"
        if config_dest.exists():
            print(f"⚠️  {config_dest} already exists. Skipping.")
        else:
            self._create_minimal_config(
                config_dest, workload_name=workload_name, environment=environment
            )
            print(f"✅ Created {config_dest}")

        # Copy deploy.sh template
        deploy_sh_template = self.templates_dir / "deploy.sh.template"
        deploy_sh_dest = target_path / "deploy.sh"

        if deploy_sh_dest.exists():
            response = input(f"⚠️  {deploy_sh_dest} already exists. Overwrite? (y/N): ")
            if response.lower() != "y":
                print("Skipped deploy.sh")
            else:
                shutil.copy(deploy_sh_template, deploy_sh_dest)
                os.chmod(deploy_sh_dest, 0o755)
                print(f"✅ Created {deploy_sh_dest}")
        else:
            shutil.copy(deploy_sh_template, deploy_sh_dest)
            os.chmod(deploy_sh_dest, 0o755)
            print(f"✅ Created {deploy_sh_dest}")

        # Copy deploy.py template
        deploy_py_template = self.templates_dir / "deploy.py.template"
        deploy_py_dest = target_path / "deploy.py"

        if deploy_py_dest.exists():
            response = input(f"⚠️  {deploy_py_dest} already exists. Overwrite? (y/N): ")
            if response.lower() != "y":
                print("Skipped deploy.py")
            else:
                shutil.copy(deploy_py_template, deploy_py_dest)
                print(f"✅ Created {deploy_py_dest}")
        else:
            shutil.copy(deploy_py_template, deploy_py_dest)
            print(f"✅ Created {deploy_py_dest}")

        # Create .gitignore
        gitignore_dest = target_path / ".gitignore"
        if not gitignore_dest.exists():
            gitignore_dest.write_text("cdk.out/\n*.swp\n.DS_Store\n__pycache__/\n")
            print(f"✅ Created {gitignore_dest}")

        print("\n✨ Project initialized successfully!")
        print(f"\nNext steps:")
        print(f"1. cd {target_path}")
        print(f"2. Edit config.json to configure your infrastructure")
        print(f"3. Run: cdk synth")
        print(f"4. Run: cdk deploy")

    def _create_minimal_config(
        self,
        path: Path,
        workload_name: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> None:
        """Create a minimal config.json template"""
        config = {
            "cdk": {
                "parameters": [
                    {
                        "placeholder": "{{ENVIRONMENT}}",
                        "env_var_name": "ENVIRONMENT",
                        "cdk_parameter_name": "Environment",
                    },
                    {
                        "placeholder": "{{WORKLOAD_NAME}}",
                        "env_var_name": "WORKLOAD_NAME",
                        "cdk_parameter_name": "WorkloadName",
                    },
                    {
                        "placeholder": "{{AWS_ACCOUNT}}",
                        "env_var_name": "AWS_ACCOUNT",
                        "cdk_parameter_name": "AccountNumber",
                    },
                    {
                        "placeholder": "{{AWS_REGION}}",
                        "env_var_name": "AWS_REGION",
                        "cdk_parameter_name": "AccountRegion",
                    },
                ]
            },
            "workload": {
                "name": workload_name or "{{WORKLOAD_NAME}}",
                "environment": environment or "{{ENVIRONMENT}}",
                "deployments": [],
            },
        }

        import json

        path.write_text(json.dumps(config, indent=2))

    def bootstrap_project(self, requirements_file: str = "requirements.txt") -> int:
        """
        Bootstrap a Python virtual environment for CDK deployments.

        Creates .venv if needed, checks cache, upgrades pip, installs requirements,
        and touches the .venv/.installed marker on success.

        Args:
            requirements_file: Path to the requirements file (default: requirements.txt).

        Returns:
            Exit code: 0 on success, 1 on pre-check failure, or pip's exit code on failure.
        """
        # Verify python3 is on PATH
        if shutil.which("python3") is None:
            print("Error: python3 is required but not found on PATH", file=sys.stderr)
            return 1

        # Verify requirements file exists
        requirements_path = Path(requirements_file)
        if not requirements_path.exists():
            print(
                f"Error: requirements file not found: {requirements_file}",
                file=sys.stderr,
            )
            return 1

        venv_path = Path(".venv")
        marker_path = venv_path / ".installed"

        # Create venv if it does not exist
        if not venv_path.exists():
            print("Creating virtual environment at .venv ...")
            result = subprocess.run(
                ["python3", "-m", "venv", ".venv"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"Error: failed to create venv: {result.stderr}", file=sys.stderr)
                return result.returncode

        # Check cache — if up to date, skip installation
        if not needs_install(requirements_path, marker_path):
            print("Dependencies are up to date, skipping install.")
            return 0

        # Upgrade pip
        pip_path = venv_path / "bin" / "pip"
        result = subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip", "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: pip upgrade failed: {result.stderr}", file=sys.stderr)
            return result.returncode

        # Install requirements
        result = subprocess.run(
            [str(pip_path), "install", "-r", str(requirements_file), "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: pip install failed: {result.stderr}", file=sys.stderr)
            return result.returncode

        # Touch marker file only on success
        marker_path.touch()
        print("Bootstrap complete.")
        return 0

    def list_templates(self) -> None:
        """List available templates"""
        print("Available templates:")
        if self.templates_dir.exists():
            for template in self.templates_dir.glob("*.template"):
                print(f"  - {template.name}")
        else:
            print("  No templates found")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="CDK Factory CLI - Initialize and manage cdk-factory projects"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser(
        "init", help="Initialize a new cdk-factory project"
    )
    init_parser.add_argument(
        "directory", help="Target directory (e.g., devops/cdk-iac)"
    )
    init_parser.add_argument("--workload-name", help="Workload name")
    init_parser.add_argument("--environment", help="Environment (dev, prod, etc.)")

    # List templates command
    subparsers.add_parser("list-templates", help="List available templates")

    # Bootstrap command
    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Create/update Python virtual environment and install dependencies",
    )
    bootstrap_parser.add_argument(
        "--requirements-file",
        default="requirements.txt",
        help="Path to requirements file (default: requirements.txt)",
    )

    args = parser.parse_args()

    cli = CdkFactoryCLI()

    if args.command == "init":
        cli.init_project(
            args.directory,
            workload_name=args.workload_name,
            environment=args.environment,
        )
    elif args.command == "list-templates":
        cli.list_templates()
    elif args.command == "bootstrap":
        sys.exit(cli.bootstrap_project(requirements_file=args.requirements_file))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
