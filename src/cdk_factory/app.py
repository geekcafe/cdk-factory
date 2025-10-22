#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
import os
from pathlib import Path
import aws_cdk
from aws_cdk.cx_api import CloudAssembly

from cdk_factory.utilities.commandline_args import CommandlineArgs
from cdk_factory.workload.workload_factory import WorkloadFactory
from cdk_factory.utilities.configuration_loader import ConfigurationLoader
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
        auto_detect_project_root: bool = True,
        is_pipeline: bool = False,
    ) -> None:

        self.args = args or CommandlineArgs()
        self.runtime_directory = runtime_directory or str(Path(__file__).parent)
        self.config_path: str | None = config_path
        self.add_env_context = add_env_context
        self._is_pipeline = is_pipeline
        
        # Auto-detect outdir for CodeBuild compatibility
        if outdir is None and self.args.outdir is None and auto_detect_project_root:
            # For both local dev and CodeBuild: use CDK default (./cdk.out in current directory)
            # This ensures CDK CLI can always find the files where it expects them
            # CodeBuild buildspec handles artifact collection from the correct location
            self.outdir = None
            
            # Log for transparency
            if os.getenv('CODEBUILD_SRC_DIR'):
                print(f"📦 CodeBuild detected: using CDK default (./cdk.out)")
                print(f"   └─ BuildSpec will collect artifacts from correct location")
        else:
            self.outdir = outdir or self.args.outdir
        
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

        print(f"👋 Synthesizing CDK App from the cdk-factory version: {__version__}")
        
        # Log outdir configuration
        if self.outdir:
            resolved_outdir = str(Path(self.outdir).resolve()) if not os.path.isabs(self.outdir) else self.outdir
            print(f"📂 CDK output directory configured: {self.outdir}")
            if not os.path.isabs(self.outdir):
                print(f"   └─ Resolves to: {resolved_outdir}")
        else:
            print(f"📂 CDK output directory: using CDK default (./cdk.out in current directory)")
            print(f"   └─ Current directory: {os.getcwd()}")

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

        assembly: CloudAssembly = workload.synth()

        print("☁️ cloud assembly dir", assembly.directory)
        
        # Validate that the assembly directory exists and has files
        self._validate_synth_output(assembly)

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


if __name__ == "__main__":
    # deploy_test()
    cmd_args: CommandlineArgs = CommandlineArgs()
    cdk_app: CdkAppFactory = CdkAppFactory(args=cmd_args)
    cdk_app.synth()
