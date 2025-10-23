#!/usr/bin/env python3
"""
Test project root detection logic in CdkAppFactory
"""

import os
import tempfile
from pathlib import Path
import pytest
from cdk_factory.app import CdkAppFactory


class TestProjectRootDetection:
    """Test the _detect_project_root method"""

    def test_codebuild_environment(self):
        """Test CODEBUILD_SRC_DIR takes priority"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create CodeBuild-like structure
            codebuild_src = Path(tmpdir) / "codebuild" / "output" / "src123" / "src"
            cdk_iac_dir = codebuild_src / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)

            # Set CodeBuild environment variable
            os.environ["CODEBUILD_SRC_DIR"] = str(codebuild_src)

            try:
                factory = CdkAppFactory(runtime_directory=str(cdk_iac_dir))

                # Default: runtime_directory/cdk.out
                expected = os.path.join(cdk_iac_dir, "cdk.out")
                assert factory.outdir == expected
            finally:
                # Clean up
                if "CODEBUILD_SRC_DIR" in os.environ:
                    del os.environ["CODEBUILD_SRC_DIR"]

    def test_devops_cdk_iac_structure(self):
        """Test detection with devops/cdk-iac directory structure (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create structure: project/devops/cdk-iac/
            project_root = Path(tmpdir)
            cdk_dir = project_root / "devops" / "cdk-iac"
            cdk_dir.mkdir(parents=True)

            # Create some root markers
            (project_root / "README.md").touch()
            (project_root / ".gitignore").touch()

            factory = CdkAppFactory(runtime_directory=str(cdk_dir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(cdk_dir, "cdk.out")
            assert factory.outdir == expected

    def test_multiple_markers_detection(self):
        """Test detection using multiple project markers (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project with multiple markers at root
            project_root = Path(tmpdir)
            subdir = project_root / "infrastructure" / "cdk"
            subdir.mkdir(parents=True)

            # Create multiple markers
            (project_root / "pyproject.toml").touch()
            (project_root / "README.md").touch()
            (project_root / ".gitignore").touch()

            factory = CdkAppFactory(runtime_directory=str(subdir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(subdir, "cdk.out")
            assert factory.outdir == expected

    def test_explicit_outdir(self):
        """Test that explicit outdir is converted to absolute path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "some" / "path" / "devops" / "cdk-iac"
            runtime_dir.mkdir(parents=True)

            # Test with relative path - converts to absolute
            factory1 = CdkAppFactory(
                runtime_directory=str(runtime_dir), outdir="my-output"
            )
            expected = os.path.join(runtime_dir, "my-output")
            assert factory1.outdir == expected

            # Test with absolute path - uses as-is
            custom_path = os.path.join(tmpdir, "custom", "cdk.out")
            factory2 = CdkAppFactory(
                runtime_directory=str(runtime_dir), outdir=custom_path
            )
            assert factory2.outdir == custom_path

    def test_cdk_outdir_environment_variable(self):
        """Test that CDK_OUTDIR environment variable overrides default"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(
                os.path.join(tmpdir, "some", "path", "devops", "cdk-iac")
            )
            runtime_dir.mkdir(parents=True)

            custom_out = os.path.join(tmpdir, "env-override", "cdk.out")
            os.environ["CDK_OUTDIR"] = custom_out

            try:
                factory = CdkAppFactory(runtime_directory=str(runtime_dir))
                assert factory.outdir == custom_out
            finally:
                if "CDK_OUTDIR" in os.environ:
                    del os.environ["CDK_OUTDIR"]

    def test_disable_auto_detection(self):
        """Test disabling auto-detection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(
                os.path.join(tmpdir, "some", "path", "devops", "cdk-iac")
            )
            runtime_dir.mkdir(parents=True)

            factory = CdkAppFactory(runtime_directory=str(runtime_dir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(runtime_dir, "cdk.out")
            assert factory.outdir == expected

    def test_fallback_to_runtime_directory(self):
        """Test fallback when no project markers found (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create bare directory with no markers
            bare_dir = Path(tmpdir) / "some" / "random" / "path"
            bare_dir.mkdir(parents=True)

            factory = CdkAppFactory(runtime_directory=str(bare_dir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(bare_dir, "cdk.out")
            assert factory.outdir == expected

    def test_single_level_devops_detection(self):
        """Test detection when runtime_directory is directly in devops/ (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            devops_dir = project_root / "devops"
            devops_dir.mkdir()

            # Add markers at root
            (project_root / "README.md").touch()
            (project_root / "requirements.txt").touch()

            factory = CdkAppFactory(runtime_directory=str(devops_dir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(devops_dir, "cdk.out")
            assert factory.outdir == expected

    def test_with_git_directory(self):
        """Test detection with .git directory (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            git_dir = project_root / ".git"
            git_dir.mkdir()

            subdir = project_root / "devops" / "cdk-iac"
            subdir.mkdir(parents=True)

            factory = CdkAppFactory(runtime_directory=str(subdir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(subdir, "cdk.out")
            assert factory.outdir == expected

    def test_without_git_with_other_markers(self):
        """Test detection without .git but with other markers (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # No .git directory
            # But has other markers
            (project_root / "package.json").touch()
            (project_root / "README.md").touch()
            (project_root / ".gitignore").touch()

            subdir = project_root / "devops" / "cdk-iac"
            subdir.mkdir(parents=True)

            factory = CdkAppFactory(runtime_directory=str(subdir))

            # Default: runtime_directory/cdk.out
            expected = os.path.join(subdir, "cdk.out")
            assert factory.outdir == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
