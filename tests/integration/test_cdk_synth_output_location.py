"""
Integration test for CDK synthesis output location.

Tests that:
1. cdk.out is created in the expected location
2. The location is consistent whether running from project root or subdirectory
3. CDK CLI can find the synthesized files
"""
import os
import tempfile
import warnings
from pathlib import Path
import pytest
from aws_cdk import App
from cdk_factory.app import CdkAppFactory


@pytest.mark.integration
class TestCdkSynthOutputLocation:
    """Integration tests for CDK synthesis output directory location"""
    
    def test_synth_creates_cdk_out_in_tmp_cdk_factory(self):
        """Test that synthesis creates cdk.out in /tmp/cdk-factory (v0.9.7+ behavior)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project structure
            project_root = Path(tmpdir)
            cdk_iac_dir = project_root / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            # Create a minimal config
            config_file = cdk_iac_dir / "config.json"
            config_file.write_text('''
{
    "workload": {
        "name": "test-app",
        "devops": {
            "ci_cd": {
                "enabled": false
            }
        },
        "stacks": []
    }
}
            ''')
            
            # Save original environment and cwd
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            if 'CODEBUILD_SRC_DIR' in os.environ:
                del os.environ['CODEBUILD_SRC_DIR']
            
            original_cwd = os.getcwd()
            
            try:
                # Change to the cdk-iac directory (simulating local dev)
                os.chdir(str(cdk_iac_dir))
                
                # Create factory with no outdir specified (should use default)
                factory = CdkAppFactory(
                    runtime_directory=str(cdk_iac_dir),
                    config_path=str(config_file)
                )
                
                # Synth should create cdk.out in /tmp/cdk-factory
                assembly = factory.synth()
                
                # Verify cdk.out was created in /tmp/cdk-factory
                expected_cdk_out = Path("/tmp/cdk-factory/cdk.out")
                assert expected_cdk_out.exists(), f"cdk.out not found at {expected_cdk_out}"
                
                # Verify the assembly directory matches
                assert Path(assembly.directory).resolve() == expected_cdk_out.resolve()
                
                # Verify manifest.json exists (CDK CLI needs this)
                manifest = expected_cdk_out / "manifest.json"
                assert manifest.exists(), "manifest.json not found in cdk.out"
                
            finally:
                os.chdir(original_cwd)
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
    
    def test_synth_in_codebuild_creates_cdk_out_in_tmp(self):
        """Test that synthesis in CodeBuild creates cdk.out in /tmp/cdk-factory (consistent behavior)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a CodeBuild-like structure
            codebuild_src = Path(tmpdir) / "codebuild" / "output" / "src"
            codebuild_src.mkdir(parents=True)
            
            cdk_iac_dir = codebuild_src / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            # Create a minimal config
            config_file = cdk_iac_dir / "config.json"
            config_file.write_text('''
{
    "workload": {
        "name": "test-app",
        "devops": {
            "ci_cd": {
                "enabled": false
            }
        },
        "stacks": []
    }
}
            ''')
            
            # Set CODEBUILD_SRC_DIR
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            os.environ['CODEBUILD_SRC_DIR'] = str(codebuild_src)
            
            original_cwd = os.getcwd()
            
            try:
                # Change to the cdk-iac directory
                os.chdir(str(cdk_iac_dir))
                
                # Create factory
                factory = CdkAppFactory(
                    runtime_directory=str(cdk_iac_dir),
                    config_path=str(config_file)
                )
                
                # Synth
                assembly = factory.synth()
                
                # Verify cdk.out was created in /tmp/cdk-factory (NOT in source tree)
                expected_cdk_out = Path("/tmp/cdk-factory/cdk.out")
                assert expected_cdk_out.exists(), f"cdk.out not found at {expected_cdk_out}"
                
                # Verify it was NOT created in the source directory
                source_cdk_out = cdk_iac_dir / "cdk.out"
                assert not source_cdk_out.exists(), f"cdk.out should not be in source tree {source_cdk_out}"
                
                # Verify the assembly directory matches
                assert Path(assembly.directory).resolve() == expected_cdk_out.resolve()
                
                # Verify manifest.json exists
                manifest = expected_cdk_out / "manifest.json"
                assert manifest.exists(), "manifest.json not found in cdk.out"
                
            finally:
                os.chdir(original_cwd)
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
                elif 'CODEBUILD_SRC_DIR' in os.environ:
                    del os.environ['CODEBUILD_SRC_DIR']
    
    def test_synth_with_explicit_outdir_as_namespace(self):
        """Test that explicit outdir parameter is used as namespace within /tmp/cdk-factory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cdk_iac_dir = project_root / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            # Create custom output directory
            custom_out_dir = project_root / "custom-output"
            
            # Create a minimal config
            config_file = cdk_iac_dir / "config.json"
            config_file.write_text('''
{
    "workload": {
        "name": "test-app",
        "devops": {
            "ci_cd": {
                "enabled": false
            }
        },
        "stacks": []
    }
}
            ''')
            
            original_cwd = os.getcwd()
            os.chdir(str(cdk_iac_dir))
            
            try:
                # Create factory with explicit outdir (used as namespace)
                factory = CdkAppFactory(
                    runtime_directory=str(cdk_iac_dir),
                    config_path=str(config_file),
                    outdir="my-project"  # This becomes the namespace
                )
                
                # Synth
                assembly = factory.synth()
                
                # Verify cdk.out was created in /tmp/cdk-factory/my-project/
                expected_cdk_out = Path("/tmp/cdk-factory/my-project/cdk.out").resolve()
                assert expected_cdk_out.exists(), f"cdk.out not found at {expected_cdk_out}"
                
                # Verify the assembly directory matches
                assert Path(assembly.directory).resolve() == expected_cdk_out
                
                # Verify manifest.json exists
                manifest = expected_cdk_out / "manifest.json"
                assert manifest.exists(), "manifest.json not found in cdk.out"
                
            finally:
                os.chdir(original_cwd)
    
    def test_cdk_out_location_is_always_tmp_cdk_factory(self):
        """Test that cdk.out location is always /tmp/cdk-factory regardless of working directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cdk_iac_dir = project_root / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            config_file = cdk_iac_dir / "config.json"
            config_file.write_text('''
{
    "workload": {
        "name": "test-app",
        "devops": {
            "ci_cd": {
                "enabled": false
            }
        },
        "stacks": []
    }
}
            ''')
            
            original_cwd = os.getcwd()
            os.chdir(str(cdk_iac_dir))
            
            try:
                factory = CdkAppFactory(
                    runtime_directory=str(cdk_iac_dir),
                    config_path=str(config_file)
                )
                
                # Check what outdir was configured (should always be /tmp/cdk-factory/cdk.out)
                configured_outdir = factory.app.outdir
                assert configured_outdir == "/tmp/cdk-factory/cdk.out"
                
                # Synth
                assembly = factory.synth()
                
                # The assembly directory should always be /tmp/cdk-factory/cdk.out
                expected = Path("/tmp/cdk-factory/cdk.out").resolve()  # Resolve symlinks (macOS /tmp -> /private/tmp)
                actual = Path(assembly.directory).resolve()
                
                assert actual == expected, f"Assembly directory {actual} doesn't match expected {expected}"
                assert expected.exists(), "Output directory doesn't exist"
                
            finally:
                os.chdir(original_cwd)
