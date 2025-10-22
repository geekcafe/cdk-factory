"""
Pipeline path utility functions.

This module contains path conversion utilities used by the pipeline factory.
Separated from pipeline_factory.py to avoid circular import issues.
"""
import os
from pathlib import Path


def convert_app_file_to_relative_directory(cdk_app_file: str) -> str:
    """
    Convert a CDK app.py file path to a relative directory path.
    
    CRITICAL: This ensures paths are ALWAYS relative before being baked into the buildspec.
    This prevents:
    1. Local absolute paths from being baked into CloudFormation templates
    2. Self-mutate loops due to changing CODEBUILD_SRC_DIR paths
    
    Args:
        cdk_app_file: Path to app.py (can be absolute or relative)
        
    Returns:
        Relative directory path (e.g., "devops/cdk-iac") or empty string for root
        
    Examples:
        >>> convert_app_file_to_relative_directory("/project/devops/cdk-iac/app.py")
        "devops/cdk-iac"
        
        >>> convert_app_file_to_relative_directory("devops/cdk-iac/app.py")
        "devops/cdk-iac"
        
        >>> convert_app_file_to_relative_directory("/project/app.py")
        ""
    """
    cdk_app_file_path = Path(cdk_app_file)
    
    # If absolute path, try to make it relative
    if cdk_app_file_path.is_absolute():
        # Check if we have a project root hint (CODEBUILD_SRC_DIR or current working directory)
        codebuild_src = os.getenv('CODEBUILD_SRC_DIR')
        base_dir = codebuild_src if codebuild_src else os.getcwd()
        
        try:
            # Resolve symlinks (important for macOS where /var -> /private/var)
            resolved_file = str(Path(cdk_app_file_path).resolve())
            resolved_base = str(Path(base_dir).resolve())
            
            # Make it relative to base directory
            rel_path = os.path.relpath(resolved_file, resolved_base)
            # If we ended up going outside (../), that's probably wrong
            if not rel_path.startswith('..'):
                cdk_app_file_path = Path(rel_path)
        except ValueError:
            # Different drives on Windows - can't make relative
            pass
    
    # Remove /app.py to get directory
    cdk_directory = str(cdk_app_file_path.parent if cdk_app_file_path.name == 'app.py' else cdk_app_file_path.parent)
    
    # Normalize to use forward slashes (works on Windows and Linux)
    cdk_directory = cdk_directory.replace('\\', '/')
    
    # If it's just '.' (current directory), use empty string
    if cdk_directory in ('.', './'):
        cdk_directory = ""
    
    return cdk_directory
