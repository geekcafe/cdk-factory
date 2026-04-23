#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
import json
import os
import shutil
import sys
import warnings
from pathlib import Path
from typing import Optional
import aws_cdk
from aws_cdk.cx_api import CloudAssembly
from aws_lambda_powertools import Logger

from cdk_factory.utilities.commandline_args import CommandlineArgs
from cdk_factory.workload.workload_factory import WorkloadFactory
from cdk_factory.utilities.configuration_loader import ConfigurationLoader
from cdk_factory.utilities.file_operations import FileOperations
from cdk_factory.version import __version__


class CdkAppFactory:
    """CDK App Wrapper"""

    def __init__(
        self,
        args: CommandlineArgs | None = None,
        runtime_directory: str | None = None,
        config_path: str | None = None,
        outdir: str | None = None,
        add_env_context: bool = True,
    ) -> None:

        self.args = args or CommandlineArgs()
        self.runtime_directory = runtime_directory
        self.config_path: str | None = config_path
        self.add_env_context = add_env_context

        # Auto-detect runtime_directory if not provided
        if not self.runtime_directory:
            self.runtime_directory = FileOperations.caller_app_dir()

        # Determine output directory with clear priority order:
        # 1. Explicit outdir parameter (highest priority)
        # 2. CDK_OUTDIR environment variable
        # 3. Default: {runtime_directory}/cdk.out

        supplied_outdir = outdir or (
            self.args.outdir if hasattr(self.args, "outdir") else None
        )

        if supplied_outdir:
            # Explicit outdir: if relative, resolve against runtime_directory
            # If absolute, use as-is
            if os.path.isabs(supplied_outdir):
                self.outdir = supplied_outdir
            else:
                # Relative path: resolve against runtime_directory, not cwd
                self.outdir = os.path.join(self.runtime_directory, supplied_outdir)
        elif os.getenv("CDK_OUTDIR"):
            # Environment variable override
            self.outdir = os.path.abspath(os.getenv("CDK_OUTDIR"))
        else:
            # Default: cdk.out in runtime_directory
            # This resolves correctly in both local and CodeBuild environments
            self.outdir = os.path.join(self.runtime_directory, "cdk.out")

        # Clean and recreate directory for fresh synthesis
        if os.path.exists(self.outdir):
            shutil.rmtree(self.outdir)
        os.makedirs(self.outdir, exist_ok=True)

        self.app: aws_cdk.App = aws_cdk.App(outdir=self.outdir)

    def synth(
        self,
        cdk_app_file: str | None = None,
        paths: list[str] | None = None,
        **kwargs,
    ) -> CloudAssembly:
        """
        The AWS CDK Deployment pipeline is defined here
        Returns:
            CloudAssembly: CDK CloudAssembly
        """

        print(f"👋 Synthesizing CDK App from cdk-factory v{__version__}")
        print(f"📂 Runtime directory: {self.runtime_directory}")
        print(f"📂 Output directory: {self.outdir}")

        if not paths:
            paths = []

        paths.append(self.app.outdir)
        paths.append(__file__)
        if cdk_app_file:
            paths.append(cdk_app_file)

        self.config_path = ConfigurationLoader().get_runtime_config(
            relative_config_path=self.config_path,
            args=self.args,
            app=self.app,
            runtime_directory=self.runtime_directory,
        )

        print("config_path", self.config_path)
        if not self.config_path:
            raise Exception("No configuration file provided")
        if not os.path.exists(self.config_path):
            raise Exception("Configuration file does not exist: " + self.config_path)
        workload: WorkloadFactory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            cdk_app_file=cdk_app_file,
            paths=paths,
            runtime_directory=self.runtime_directory,
            outdir=self.outdir,
            add_env_context=self.add_env_context,
        )

        try:
            assembly: CloudAssembly = workload.synth()
        except RuntimeError as e:
            error_msg = str(e)
            # Catch JSII validation errors and present them cleanly
            if "ValidationError" in error_msg or "jsii" in str(
                type(e).__module__ or ""
            ):
                print(f"\n  ✗ CDK Synthesis Failed\n")
                for line in error_msg.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("at "):
                        print(f"    {line}")
                print()
                sys.exit(1)
            # Unknown RuntimeError
            self._print_unexpected_error(e)
            sys.exit(1)
        except ValueError as e:
            print(f"\n  ✗ Configuration Error\n")
            print(f"    {e}")
            print()
            sys.exit(1)
        except Exception as e:
            self._print_unexpected_error(e)
            sys.exit(1)
            sys.exit(1)

        print("☁️ cloud assembly dir", assembly.directory)

        # Validate that the assembly directory exists and has files
        self._validate_synth_output(assembly)

        self._copy_cdk_out_to_project_root()

        return assembly

    def _validate_synth_output(self, assembly: CloudAssembly) -> None:
        """
        Validate that CDK synthesis actually created the expected files.

        Args:
            assembly: The CloudAssembly returned from synth

        Raises:
            RuntimeError: If the output directory doesn't exist or is empty
        """
        assembly_dir = Path(assembly.directory)

        # Check if directory exists
        if not assembly_dir.exists():
            raise RuntimeError(
                f"❌ CDK synthesis failed: Output directory does not exist!\n"
                f"   Expected: {assembly_dir}\n"
                f"   Configured outdir: {self.outdir}\n"
                f"   Current directory: {os.getcwd()}"
            )

        # Check if directory has files
        files = list(assembly_dir.iterdir())
        if not files:
            raise RuntimeError(
                f"❌ CDK synthesis failed: Output directory is empty!\n"
                f"   Directory: {assembly_dir}\n"
                f"   This usually means CDK failed to write files."
            )

        # Check for manifest.json (key CDK file)
        manifest = assembly_dir / "manifest.json"
        if not manifest.exists():
            raise RuntimeError(
                f"❌ CDK synthesis incomplete: manifest.json not found!\n"
                f"   Directory: {assembly_dir}\n"
                f"   Files found: {[f.name for f in files]}\n"
                f"   CDK may have failed during synthesis."
            )

        # Success - log details
        print(f"✅ CDK synthesis successful!")
        print(f"   └─ Output directory: {assembly_dir}")
        print(f"   └─ Files created: {len(files)}")
        print(f"   └─ Stacks: {len(assembly.stacks)}")

        # Log stack names
        if assembly.stacks:
            stack_names = [stack.stack_name for stack in assembly.stacks]
            for stack_name in stack_names:
                print(f"      • {stack_name}")

        # Resource summary report
        self._print_resource_summary(assembly)

        # Synth messages summary (warnings, info collected during synthesis)
        from cdk_factory.utilities.synth_messages import synth_messages

        synth_messages.print_summary()

    def _print_unexpected_error(self, error: Exception) -> None:
        """Format an unexpected error with a clean, readable output."""
        import re
        import traceback

        error_type = type(error).__name__
        error_msg = str(error)

        # Extract clean message, filtering JS/JSII noise
        clean_lines = []
        for line in error_msg.split("\n"):
            stripped = line.strip()
            if stripped.startswith("at ") and (
                "program.js" in stripped or "node:" in stripped
            ):
                continue
            if stripped:
                clean_lines.append(stripped)

        message = clean_lines[0] if clean_lines else error_msg
        details = clean_lines[1:] if len(clean_lines) > 1 else []

        # Color codes
        red = "\033[0;31m"
        yellow = "\033[0;33m"
        cyan = "\033[0;36m"
        dim = "\033[2m"
        reset = "\033[0m"

        print(f"\n{red}{'━' * 60}{reset}")
        print(f"{red}  ✗ CDK Synthesis Failed{reset}")
        print(f"{red}{'━' * 60}{reset}")
        print(f"\n  {message}")
        for line in details:
            print(f"  {line}")

        # Actionable context for known error patterns
        if "Stack name must match" in error_msg:
            match = re.search(r"got '([^']+)'", error_msg)
            bad_name = match.group(1) if match else "unknown"
            print(f"\n{yellow}  Cause:{reset}")
            print(f"    The stack name '{bad_name}' contains invalid characters.")
            print(f"    Stack names can only use letters, numbers, and hyphens.")
            print(f"\n{cyan}  Fix:{reset}")
            print(
                f"    Check naming.prefix and naming.stack_pattern in your deployment config,"
            )
            print(f"    or add a stack_name override in the stack config.")
        elif "Unable to determine ARN separator" in error_msg:
            print(f"\n{yellow}  Cause:{reset}")
            print(f"    An SSM parameter name contains an unresolved CDK token.")
            print(f"\n{cyan}  Fix:{reset}")
            print(
                f"    Check SSM export configs — parameter_name should be a path string,"
            )
            print(f"    not a resource attribute.")
        elif "Invalid S3 bucket name" in error_msg:
            print(f"\n{yellow}  Cause:{reset}")
            print(
                f"    A bucket name has invalid characters (likely a <TODO> placeholder)."
            )
            print(f"\n{cyan}  Fix:{reset}")
            print(f"    Fill in all <TODO> values in your deployment JSON.")
        elif "Failed to get value for" in error_msg:
            print(f"\n{cyan}  Fix:{reset}")
            print(f"    Add the missing value to your deployment JSON parameters.")
        else:
            print(f"\n{yellow}  Error type: {error_type}{reset}")

        # Show only project-relevant frames, skip library internals
        tb_lines = traceback.format_tb(error.__traceback__)
        project_frames = [
            f
            for f in tb_lines
            if "site-packages" not in f and "jsii" not in f and "node:" not in f
        ]
        if project_frames:
            print(f"\n{dim}  Origin:{reset}")
            for line in project_frames[-1].strip().split("\n"):
                print(f"    {dim}{line}{reset}")

        print(f"\n{dim}  Tip: set CDK_FACTORY_DEBUG=1 for full traceback{reset}")
        print(f"{red}{'━' * 60}{reset}\n")

        if os.environ.get("CDK_FACTORY_DEBUG") == "1":
            print("--- Full Traceback ---")
            traceback.print_exc()

    def _print_resource_summary(self, assembly: CloudAssembly) -> None:
        """Print a summary of CloudFormation resources by type across all stacks."""
        import json as _json
        from collections import Counter

        # Friendly display names for common AWS resource types
        FRIENDLY_NAMES = {
            "AWS::Lambda::Function": "Lambda Functions",
            "AWS::SQS::Queue": "SQS Queues",
            "AWS::DynamoDB::Table": "DynamoDB Tables",
            "AWS::S3::Bucket": "S3 Buckets",
            "AWS::ApiGateway::RestApi": "API Gateways",
            "AWS::ApiGatewayV2::Api": "API Gateways (v2)",
            "AWS::Cognito::UserPool": "Cognito User Pools",
            "AWS::StepFunctions::StateMachine": "Step Functions",
            "AWS::CloudWatch::Alarm": "CloudWatch Alarms",
            "AWS::CloudWatch::Dashboard": "CloudWatch Dashboards",
            "AWS::ECR::Repository": "ECR Repositories",
            "AWS::Route53::HostedZone": "Route53 Hosted Zones",
            "AWS::Route53::RecordSet": "Route53 Records",
            "AWS::SSM::Parameter": "SSM Parameters",
            "AWS::IAM::Role": "IAM Roles",
            "AWS::IAM::Policy": "IAM Policies",
            "AWS::Lambda::EventSourceMapping": "Lambda Event Source Mappings",
            "AWS::Lambda::LayerVersion": "Lambda Layers",
            "AWS::CertificateManager::Certificate": "ACM Certificates",
            "AWS::ECS::Service": "ECS Services",
            "AWS::ECS::TaskDefinition": "ECS Task Definitions",
            "AWS::ElasticLoadBalancingV2::LoadBalancer": "Load Balancers",
            "AWS::CloudFront::Distribution": "CloudFront Distributions",
            "AWS::CodePipeline::Pipeline": "CodePipelines",
        }

        resource_counts: Counter = Counter()
        total_resources = 0
        stack_resource_counts: dict = {}

        assembly_dir = Path(assembly.directory)

        # Walk all template files in the assembly (including nested assemblies)
        for template_file in assembly_dir.rglob("*.template.json"):
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    template = _json.load(f)
                resources = template.get("Resources", {})
                stack_name = template_file.stem.replace(".template", "")
                stack_count = 0
                for _logical_id, resource in resources.items():
                    resource_type = resource.get("Type", "Unknown")
                    resource_counts[resource_type] += 1
                    total_resources += 1
                    stack_count += 1
                stack_resource_counts[stack_name] = stack_count
            except (ValueError, _json.JSONDecodeError):
                continue

        if not resource_counts:
            return

        print(f"\n📊 Resource Summary ({total_resources} total resources)")
        print(f"   {'─' * 45}")

        # Sort by count descending, show friendly names
        for resource_type, count in resource_counts.most_common():
            friendly = FRIENDLY_NAMES.get(resource_type, resource_type)
            print(f"   {count:>4}  {friendly}")

        # Per-stack breakdown (warn if any stack is near the 500 limit)
        print(f"\n   📦 Per-Stack Resource Counts:")
        for stack_name, count in sorted(
            stack_resource_counts.items(), key=lambda x: -x[1]
        ):
            warning = " ⚠️  approaching 500 limit!" if count > 400 else ""
            print(f"   {count:>4}  {stack_name}{warning}")

    def _detect_project_root(self) -> str:
        """
        Detect project root directory for proper cdk.out placement

        Priority:
        1. CODEBUILD_SRC_DIR (CodeBuild environment)
        2. Find project markers (pyproject.toml, package.json, .git, etc.)
        3. Assume devops/cdk-iac structure (go up 2 levels)
        4. Fallback to runtime_directory

        Returns:
            str: Absolute path to project root
        """
        # Priority 1: CodeBuild environment (most reliable)
        codebuild_src = os.getenv("CODEBUILD_SRC_DIR")
        if codebuild_src:
            return str(Path(codebuild_src).resolve())

        # Priority 2: Look for project root markers
        # CodeBuild often gets zip without .git, so check multiple markers
        current = Path(self.runtime_directory).resolve()

        # Walk up the directory tree looking for root markers
        for parent in [current] + list(current.parents):
            # Check for common project root indicators
            root_markers = [
                ".git",  # Git repo (local dev)
                "pyproject.toml",  # Python project root
                "package.json",  # Node project root
                "Cargo.toml",  # Rust project root
                ".gitignore",  # Often at root
                "README.md",  # Often at root
                "requirements.txt",  # Python dependencies
            ]

            # If we find multiple markers at this level, it's likely the root
            markers_found = sum(
                1 for marker in root_markers if (parent / marker).exists()
            )
            if markers_found >= 2 and parent != current:
                return str(parent)

        # Priority 3: Assume devops/cdk-iac structure
        # If runtime_directory ends with devops/cdk-iac, go up 2 levels
        parts = current.parts
        if len(parts) >= 2 and parts[-2:] == ("devops", "cdk-iac"):
            return str(current.parent.parent)

        # Also try just 'cdk-iac' or 'devops'
        if len(parts) >= 1 and parts[-1] in (
            "cdk-iac",
            "devops",
            "infrastructure",
            "iac",
        ):
            # Go up until we're not in these directories
            potential_root = current.parent
            while potential_root.name in ("devops", "cdk-iac", "infrastructure", "iac"):
                potential_root = potential_root.parent
            return str(potential_root)

        # Priority 4: Fallback to runtime_directory
        return str(current)

    def _copy_cdk_out_to_project_root(self):
        # Copy the cdk.out directory to the project root so it can be picked up by CodeBuild
        # Source: the actual CDK output directory from the synthesis (e.g., /tmp/cdk-factory/cdk.out)
        cdk_out_source = self.outdir

        # raise Exception(f"cdk_out_source: {cdk_out_source}")

        # Destination: project root (two directories up from devops/cdk-iac where this file lives)
        project_root = os.getenv("CODEBUILD_SRC_DIR")
        if not project_root:
            return

        cdk_out_dest = os.path.join(project_root, "cdk.out")

        print(f"👉 Project root: {project_root}")
        print(f"👉 CDK output source: {cdk_out_source}")
        print(f"👉 CDK output destination: {cdk_out_dest}")

        if os.path.exists(cdk_out_dest):
            print("❌ CDK output directory already exists, skipping copy")
            return
        else:
            print("✅ CDK output directory does not exist, copying")

        shutil.copytree(cdk_out_source, cdk_out_dest)
        print(f"✅  Copied CDK output to {cdk_out_dest}")


if __name__ == "__main__":
    # deploy_test()
    cmd_args: CommandlineArgs = CommandlineArgs()
    cdk_app: CdkAppFactory = CdkAppFactory(args=cmd_args)
    cdk_app.synth()
