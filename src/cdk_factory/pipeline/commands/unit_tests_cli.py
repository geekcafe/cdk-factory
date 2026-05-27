"""Unified Unit Test Runner CLI.

Discovers requirements files, installs dependencies, and runs pytest.

Usage:
    python -m cdk_factory.pipeline.commands.unit_tests_cli --project-root <path> --ignore-integration

Ported from aplos_saas_devops_cdk.commands.unit_tests_cli with import paths updated.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_project_root(override_path: str = None) -> str:
    """Get project root directory.

    Resolution order:
      1. Explicit override path (--project-root flag)
      2. CODEBUILD_SRC_DIR environment variable
      3. Current working directory
    """
    if override_path:
        return str(Path(override_path).resolve())

    codebuild_src = os.getenv("CODEBUILD_SRC_DIR")
    if codebuild_src:
        return codebuild_src

    return str(Path.cwd().resolve())


def main():
    """Run unit tests for the project."""
    parser = argparse.ArgumentParser(description="Run unit tests")
    parser.add_argument(
        "--project-root",
        help="Project root directory (defaults to current directory or CODEBUILD_SRC_DIR)",
    )
    parser.add_argument(
        "--ignore-integration",
        action="store_true",
        default=True,
        help="Ignore integration tests (default: True)",
    )
    args = parser.parse_args()

    try:
        project_root = get_project_root(args.project_root)
        os.chdir(project_root)

        print("🧪 Running unit tests 🧪")
        print("##########################")
        print(f"location: {os.getcwd()}")
        print("##########################")

        # Install test dependencies — discover all requirements*.txt files
        requirements = sorted(
            f.name
            for f in Path(project_root).iterdir()
            if f.is_file()
            and f.name.startswith("requirements")
            and f.name.endswith(".txt")
        )

        for requirements_file in requirements:
            test_requirements = os.path.join(project_root, requirements_file)
            print(f"👀 Looking for {requirements_file}")
            if os.path.exists(test_requirements):
                print("📦 Installing test dependencies...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", test_requirements],
                    check=True,
                )
            else:
                print(
                    f"⚠️ No {requirements_file} found. "
                    f"If you get import errors add a {requirements_file}"
                )

        # Install package in editable mode
        print("📦 Installing package in editable mode...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            check=True,
        )

        # Run pytest
        pytest_args = ["pytest", "tests/", "-v", "--tb=short"]
        if args.ignore_integration:
            pytest_args.append("--ignore=tests/integration")

        print(f"🧪 Running: {' '.join(pytest_args)}")
        result = subprocess.run(pytest_args, capture_output=False)

        # Exit code 5 means "no tests collected" - treat as success if no unit tests exist
        if result.returncode == 5:
            print("##########################")
            print("⚠️  No unit tests found (only integration tests exist)")
            print("✓ Skipping unit tests - proceeding with build")
        elif result.returncode == 0:
            print("##########################")
            print("✓ All unit tests passed")
        else:
            print(
                f"❌ Tests failed with exit code {result.returncode}", file=sys.stderr
            )
            sys.exit(result.returncode)

    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(f"❌ Test execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
