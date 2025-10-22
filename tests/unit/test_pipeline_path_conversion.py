"""
Test that pipeline buildspec paths are always relative, never absolute.

This prevents absolute paths from being baked into the CloudFormation template,
which would cause issues when:
1. Local paths don't exist in CodeBuild
2. Self-mutate detects changes every run due to different CODEBUILD_SRC_DIR paths
"""
import os
import tempfile
from pathlib import Path
import pytest

# Import the actual production function we're testing
from cdk_factory.pipeline.path_utils import convert_app_file_to_relative_directory


class TestPipelinePathConversion:
    """Test path conversion to ensure buildspec always has relative paths"""
    
    def test_local_absolute_path_converted_to_relative(self):
        """Test that absolute local paths are converted to relative"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate a local project structure
            project_root = Path(tmpdir)
            cdk_iac_dir = project_root / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            app_py = cdk_iac_dir / "app.py"
            app_py.touch()
            
            # Set up environment - NO CODEBUILD_SRC_DIR (local dev)
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            if 'CODEBUILD_SRC_DIR' in os.environ:
                del os.environ['CODEBUILD_SRC_DIR']
            
            # Change to project root (simulating where you run cdk from)
            original_cwd = os.getcwd()
            os.chdir(str(project_root))
            
            try:
                # Test the actual production function
                cdk_directory = convert_app_file_to_relative_directory(str(app_py))
                
                # Should be relative path
                assert not os.path.isabs(cdk_directory)
                
                # Should point to devops/cdk-iac
                assert cdk_directory == 'devops/cdk-iac'
                
            finally:
                os.chdir(original_cwd)
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
    
    def test_codebuild_absolute_path_converted_to_relative(self):
        """Test that CodeBuild absolute paths are converted to relative"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate CodeBuild structure
            codebuild_src = Path(tmpdir) / "codebuild" / "output" / "src"
            codebuild_src.mkdir(parents=True)
            
            cdk_iac_dir = codebuild_src / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            app_py = cdk_iac_dir / "app.py"
            app_py.touch()
            
            # Set CODEBUILD_SRC_DIR environment variable
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            os.environ['CODEBUILD_SRC_DIR'] = str(codebuild_src)
            
            try:
                # Test the actual production function
                cdk_directory = convert_app_file_to_relative_directory(str(app_py))
                
                # Should be relative path
                assert not os.path.isabs(cdk_directory)
                
                # Should point to devops/cdk-iac
                assert cdk_directory == 'devops/cdk-iac'
                
            finally:
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
                elif 'CODEBUILD_SRC_DIR' in os.environ:
                    del os.environ['CODEBUILD_SRC_DIR']
    
    def test_relative_path_stays_relative(self):
        """Test that already-relative paths remain relative"""
        # If cdk_app_file is already relative, it should stay that way
        cdk_directory = convert_app_file_to_relative_directory("devops/cdk-iac/app.py")
        
        # Should be relative
        assert not os.path.isabs(cdk_directory)
        
        # Directory should be devops/cdk-iac
        assert cdk_directory == 'devops/cdk-iac'
    
    def test_root_directory_app_py(self):
        """Test app.py at project root (edge case)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            app_py = project_root / "app.py"
            app_py.touch()
            
            # Set up environment
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            if 'CODEBUILD_SRC_DIR' in os.environ:
                del os.environ['CODEBUILD_SRC_DIR']
            
            original_cwd = os.getcwd()
            os.chdir(str(project_root))
            
            try:
                # Test the actual production function
                cdk_directory = convert_app_file_to_relative_directory(str(app_py))
                
                # Should be empty string (root directory)
                assert cdk_directory == ''
                
            finally:
                os.chdir(original_cwd)
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
    
    def test_nested_infrastructure_path(self):
        """Test deeply nested infrastructure directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            infra_dir = project_root / "infrastructure" / "cdk" / "pipeline"
            infra_dir.mkdir(parents=True)
            
            app_py = infra_dir / "app.py"
            app_py.touch()
            
            # Set up environment
            original_codebuild = os.environ.get('CODEBUILD_SRC_DIR')
            os.environ['CODEBUILD_SRC_DIR'] = str(project_root)
            
            try:
                # Test the actual production function
                cdk_directory = convert_app_file_to_relative_directory(str(app_py))
                
                # Should be relative
                assert not os.path.isabs(cdk_directory)
                
                # Directory should be infrastructure/cdk/pipeline
                assert cdk_directory == 'infrastructure/cdk/pipeline'
                
            finally:
                if original_codebuild:
                    os.environ['CODEBUILD_SRC_DIR'] = original_codebuild
                elif 'CODEBUILD_SRC_DIR' in os.environ:
                    del os.environ['CODEBUILD_SRC_DIR']
    
    def test_artifact_path_calculation(self):
        """Test that cdk.out artifact path is correctly calculated"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cdk_iac_dir = project_root / "devops" / "cdk-iac"
            cdk_iac_dir.mkdir(parents=True)
            
            app_py = cdk_iac_dir / "app.py"
            app_py.touch()
            
            os.environ['CODEBUILD_SRC_DIR'] = str(project_root)
            
            try:
                # Test the actual production function
                cdk_directory = convert_app_file_to_relative_directory(str(app_py))
                
                # Calculate cdk.out location
                if cdk_directory:
                    cdk_out_directory = f"{cdk_directory}/cdk.out"
                else:
                    cdk_out_directory = "cdk.out"
                
                # Should be devops/cdk-iac/cdk.out
                assert cdk_out_directory == "devops/cdk-iac/cdk.out"
                
                # This is what goes into the buildspec artifacts section
                # And it should work from the project root in CodeBuild
                assert not os.path.isabs(cdk_out_directory)
                
            finally:
                if 'CODEBUILD_SRC_DIR' in os.environ:
                    del os.environ['CODEBUILD_SRC_DIR']
