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
                
                # In CodeBuild, should use CDK default (./cdk.out)
                # BuildSpec handles artifact collection from the correct location
                assert factory.outdir is None
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
            
            # For local dev, should use CDK default (None)
            # This allows CDK CLI to use ./cdk.out in current directory
            assert factory.outdir is None
    
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
            
            # For local dev, should use CDK default (None)
            assert factory.outdir is None
    
    def test_explicit_outdir_overrides_detection(self):
        """Test that explicit outdir overrides auto-detection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_outdir = str(Path(tmpdir) / 'custom' / 'cdk.out')
            runtime_dir = Path(tmpdir) / 'some' / 'path' / 'devops' / 'cdk-iac'
            runtime_dir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                outdir=custom_outdir
            )
            
            assert factory.outdir == custom_outdir
    
    def test_disable_auto_detection(self):
        """Test disabling auto-detection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / 'some' / 'path' / 'devops' / 'cdk-iac'
            runtime_dir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(runtime_dir),
                auto_detect_project_root=False
            )
            
            # Should be None (CDK default behavior)
            assert factory.outdir is None
    
    def test_fallback_to_runtime_directory(self):
        """Test fallback when no project markers found (local dev)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create bare directory with no markers
            bare_dir = Path(tmpdir) / 'some' / 'random' / 'path'
            bare_dir.mkdir(parents=True)
            
            factory = CdkAppFactory(
                runtime_directory=str(bare_dir)
            )
            
            # For local dev, should use CDK default (None)
            assert factory.outdir is None
    
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
            
            # For local dev, should use CDK default (None)
            assert factory.outdir is None
    
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
            
            # For local dev, should use CDK default (None)
            assert factory.outdir is None
    
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
            
            # For local dev, should use CDK default (None)
            assert factory.outdir is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
