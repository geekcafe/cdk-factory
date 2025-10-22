#!/usr/bin/env python3
"""
CDK Factory CLI

Provides convenience commands for initializing and managing cdk-factory projects.
"""

import argparse
import os
import shutil
from pathlib import Path
from typing import Optional


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
            if response.lower() != 'y':
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
                config_dest,
                workload_name=workload_name,
                environment=environment
            )
            print(f"✅ Created {config_dest}")
        
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
        environment: Optional[str] = None
    ) -> None:
        """Create a minimal config.json template"""
        config = {
            "cdk": {
                "parameters": [
                    {
                        "placeholder": "{{ENVIRONMENT}}",
                        "env_var_name": "ENVIRONMENT",
                        "cdk_parameter_name": "Environment"
                    },
                    {
                        "placeholder": "{{WORKLOAD_NAME}}",
                        "env_var_name": "WORKLOAD_NAME",
                        "cdk_parameter_name": "WorkloadName"
                    },
                    {
                        "placeholder": "{{AWS_ACCOUNT}}",
                        "env_var_name": "AWS_ACCOUNT",
                        "cdk_parameter_name": "AccountNumber"
                    },
                    {
                        "placeholder": "{{AWS_REGION}}",
                        "env_var_name": "AWS_REGION",
                        "cdk_parameter_name": "AccountRegion"
                    }
                ]
            },
            "workload": {
                "name": workload_name or "{{WORKLOAD_NAME}}",
                "environment": environment or "{{ENVIRONMENT}}",
                "deployments": []
            }
        }
        
        import json
        path.write_text(json.dumps(config, indent=2))
    
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
        "init",
        help="Initialize a new cdk-factory project"
    )
    init_parser.add_argument(
        "directory",
        help="Target directory (e.g., devops/cdk-iac)"
    )
    init_parser.add_argument(
        "--workload-name",
        help="Workload name"
    )
    init_parser.add_argument(
        "--environment",
        help="Environment (dev, prod, etc.)"
    )
    
    # List templates command
    subparsers.add_parser(
        "list-templates",
        help="List available templates"
    )
    
    args = parser.parse_args()
    
    cli = CdkFactoryCLI()
    
    if args.command == "init":
        cli.init_project(
            args.directory,
            workload_name=args.workload_name,
            environment=args.environment
        )
    elif args.command == "list-templates":
        cli.list_templates()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
