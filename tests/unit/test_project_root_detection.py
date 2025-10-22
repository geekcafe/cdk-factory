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
            codebuild_src = Path(tmpdir) / 'codebuild' / 'output' / 'src123' / 'src'
            cdk_iac_dir = codebuild_src / 'devops' / 'cdk-iac'
            cdk_iac_dir.mkdir(parents=True)
            
            # Set CodeBuild environment variable
            os.environ['CODEBUILD_SRC_DIR'] = str(codebuild_src)
            
            try:
                factory = CdkAppFactory(
                    runtime_directory=str(cdk_iac_dir)
                )
                
                # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
                # BuildSpec now collects from absolute path
                assert factory.outdir == "/tmp/cdk-factory/cdk.out"
            finally:
                # Clean up
                if 'CODEBUILD_SRC_DIR' in os.environ:
                    del os.environ['CODEBUILD_SRC_DIR']
    
    def test_devops_cdk_iac_structure(self):
        """Test detection with devops/cdk-iac directory structure (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create structure: project/devops/cdk-iac/
            project_root = Path(tmpdir)
            cdk_dir = project_root / 'devops' / 'cdk-iac'
            cdk_dir.mkdir(parents=True)
            
            # Create some root markers
            (project_root / 'README.md').touch()
            (project_root / '.gitignore').touch()
            
            factory = CdkAppFactory(
                runtime_directory=str(cdk_dir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_multiple_markers_detection(self):
        """Test detection using multiple project markers (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project with multiple markers at root
            project_root = Path(tmpdir)
            subdir = project_root / 'infrastructure' / 'cdk'
            subdir.mkdir(parents=True)
            
            # Create multiple markers
            (project_root / 'pyproject.toml').touch()
            (project_root / 'README.md').touch()
            (project_root / '.gitignore').touch()
            
            factory = CdkAppFactory(
                runtime_directory=str(subdir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_explicit_outdir_as_namespace(self):
        """Test that explicit outdir is used as namespace within /tmp/cdk-factory (v0.9.7+)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / 'some' / 'path' / 'devops' / 'cdk-iac'
            runtime_dir.mkdir(parents=True)
            
            # Test with simple directory name
            factory1 = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                outdir="my-app"
            )
            assert factory1.outdir == "/tmp/cdk-factory/my-app/cdk.out"
            
            # Test with full path (should extract basename)
            factory2 = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                outdir="/custom/path/my-project"
            )
            assert factory2.outdir == "/tmp/cdk-factory/my-project/cdk.out"
            
            # Test with trailing slash
            factory3 = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                outdir="my-deployment/"
            )
            assert factory3.outdir == "/tmp/cdk-factory/my-deployment/cdk.out"
    
    def test_disable_auto_detection(self):
        """Test disabling auto-detection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / 'some' / 'path' / 'devops' / 'cdk-iac'
            runtime_dir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                auto_detect_project_root=False
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            # (auto_detect_project_root no longer affects outdir)
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_fallback_to_runtime_directory(self):
        """Test fallback when no project markers found (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create bare directory with no markers
            bare_dir = Path(tmpdir) / 'some' / 'random' / 'path'
            bare_dir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(bare_dir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_single_level_devops_detection(self):
        """Test detection when runtime_directory is directly in devops/ (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            devops_dir = project_root / 'devops'
            devops_dir.mkdir()
            
            # Add markers at root
            (project_root / 'README.md').touch()
            (project_root / 'requirements.txt').touch()
            
            factory = CdkAppFactory(
                runtime_directory=str(devops_dir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_with_git_directory(self):
        """Test detection with .git directory (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            git_dir = project_root / '.git'
            git_dir.mkdir()
            
            subdir = project_root / 'devops' / 'cdk-iac'
            subdir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(subdir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"
    
    def test_without_git_with_other_markers(self):
        """Test detection without .git but with other markers (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            
            # No .git directory
            # But has other markers
            (project_root / 'package.json').touch()
            (project_root / 'README.md').touch()
            (project_root / '.gitignore').touch()
            
            subdir = project_root / 'devops' / 'cdk-iac'
            subdir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(subdir)
            )
            
            # v0.9.7+: Always uses consistent /tmp/cdk-factory/cdk.out
            assert factory.outdir == "/tmp/cdk-factory/cdk.out"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
