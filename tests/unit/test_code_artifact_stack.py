"""
Unit tests for CodeArtifact Stack
"""

import unittest
from unittest.mock import patch, MagicMock

from aws_cdk import App
from aws_cdk import aws_codeartifact as codeartifact

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.code_artifact import CodeArtifactConfig
from cdk_factory.stack_library.code_artifact.code_artifact_stack import CodeArtifactStack
from cdk_factory.workload.workload_factory import WorkloadConfig


def test_code_artifact_stack_minimal():
    """Test CodeArtifact stack with minimal configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "code_artifact": {
                "domain_name": "test-domain"
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create the stack
    stack = CodeArtifactStack(app, "TestCodeArtifactStack")
    
    # Mock the _build method directly
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
        
        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)


def test_code_artifact_stack_full_config():
    """Test CodeArtifact stack with full configuration"""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "code_artifact": {
                "domain_name": "test-domain",
                "domain_description": "Test domain for artifacts",
                "repositories": [
                    {
                        "name": "npm-repo",
                        "description": "NPM repository",
                        "external_connections": ["public:npm"]
                    },
                    {
                        "name": "python-repo",
                        "description": "Python repository",
                        "external_connections": ["public:pypi"],
                        "upstream_repositories": ["npm-repo"]
                    }
                ]
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    
    # Create the stack
    stack = CodeArtifactStack(app, "FullCodeArtifactStack")
    
    # Test the config loading
    with patch.object(stack, "_build") as mock_build:
        # Build the stack
        stack.build(stack_config, deployment, dummy_workload)
        
        # Verify _build was called with the correct arguments
        mock_build.assert_called_once_with(stack_config, deployment, dummy_workload)
        
    # Create a new stack for testing the internal build logic
    stack = CodeArtifactStack(app, "FullCodeArtifactStackInternal")
    
    # Set up the config directly
    stack.stack_config = stack_config
    stack.deployment = deployment
    stack.workload = dummy_workload
    stack.code_artifact_config = CodeArtifactConfig(stack_config.dictionary.get("code_artifact", {}), deployment)
    
    # Mock the internal methods
    with patch.object(stack, "_create_domain") as mock_create_domain:
        with patch.object(stack, "_create_repository") as mock_create_repository:
            with patch.object(stack, "_add_outputs") as mock_add_outputs:
                # Create mock domain and repositories
                mock_domain = MagicMock()
                mock_repo1 = MagicMock()
                mock_repo2 = MagicMock()
                
                # Set up mock returns
                mock_create_domain.return_value = mock_domain
                mock_create_repository.side_effect = [mock_repo1, mock_repo2]
                
                # Call the internal _build method directly
                stack._build(stack_config, deployment, dummy_workload)
                
                # Verify the methods were called
                mock_create_domain.assert_called_once()
                assert mock_create_repository.call_count == 2
                mock_add_outputs.assert_called_once()


def test_create_domain():
    """Test domain creation"""
    app = App()
    stack = CodeArtifactStack(app, "TestDomainCreation")
    
    # Set up deployment config with mock
    deployment = MagicMock()
    domain_name = "test-domain"
    # Mock the build_resource_name method to return the domain name directly
    deployment.build_resource_name.return_value = domain_name
    
    # Create a mock config
    code_artifact_config = MagicMock()
    code_artifact_config.domain_name = domain_name
    code_artifact_config.domain_description = "Test domain description"
    
    # Set the config on the stack
    stack.code_artifact_config = code_artifact_config
    
    # Mock the CfnDomain constructor
    with patch("aws_cdk.aws_codeartifact.CfnDomain") as mock_domain_constructor:
        # Create a mock domain
        mock_domain = MagicMock()
        mock_domain_constructor.return_value = mock_domain
        
        # Call the create domain method
        result = stack._create_domain()
        
        # Verify the domain was created with the correct properties
        mock_domain_constructor.assert_called_once()
        args, kwargs = mock_domain_constructor.call_args
        
        # Check that the domain was created with the correct properties
        assert kwargs["domain_name"] == domain_name
        assert kwargs["domain_description"] == "Test domain description"
        
        # Verify the result is the mock domain
        assert result == mock_domain
        
        # Verify the domain was stored in the stack
        assert stack.domain == mock_domain


def test_create_repository():
    """Test repository creation"""
    app = App()
    stack = CodeArtifactStack(app, "TestRepositoryCreation")
    
    # Set up deployment config with mock
    deployment = MagicMock()
    repo_name = "test-repo"
    domain_name = "test-domain"
    # Mock the build_resource_name method to return the name directly
    deployment.build_resource_name.return_value = repo_name
    
    # Create a mock domain
    mock_domain = MagicMock()
    
    # Set up the stack
    stack.deployment = deployment
    stack.domain = mock_domain
    
    # Create a mock config
    code_artifact_config = MagicMock()
    code_artifact_config.domain_name = domain_name
    
    # Set the config on the stack
    stack.code_artifact_config = code_artifact_config
    
    # Create a repository config
    repo_config = {
        "name": repo_name,
        "description": "Test repository",
        "external_connections": ["public:npm"],
        "upstream_repositories": ["other-repo"]
    }
    
    # Mock the CfnRepository constructor
    with patch("aws_cdk.aws_codeartifact.CfnRepository") as mock_repo_constructor:
        # Create a mock repository
        mock_repo = MagicMock()
        mock_repo_constructor.return_value = mock_repo
        
        # Call the create repository method
        result = stack._create_repository(repo_config)
        
        # Verify the repository was created with the correct properties
        mock_repo_constructor.assert_called_once()
        args, kwargs = mock_repo_constructor.call_args
        
        # Check that the repository was created with the correct properties
        assert kwargs["domain_name"] == domain_name
        assert kwargs["repository_name"] == repo_name
        assert kwargs["description"] == "Test repository"
        assert "external_connections" in kwargs
        assert "upstream_repositories" in kwargs
        
        # Verify the result is the mock repository
        assert result == mock_repo
        
        # Verify the repository was stored in the stack's repositories dictionary
        assert repo_name in stack.repositories
        assert stack.repositories[repo_name] == mock_repo
        
        # Verify dependency was added to the domain
        mock_repo.add_dependency.assert_called_once_with(mock_domain)


def test_add_outputs():
    """Test adding outputs"""
    app = App()
    stack = CodeArtifactStack(app, "TestOutputs")
    
    # Set up deployment config with mock
    deployment = MagicMock()
    # Mock the build_resource_name method to return the input with a prefix
    deployment.build_resource_name.side_effect = lambda x: f"test-{x}"
    
    # Set the deployment on the stack
    stack.deployment = deployment
    
    # Create mock domain and repository
    mock_domain = MagicMock()
    mock_domain.attr_arn = "arn:aws:codeartifact:us-east-1:123456789012:domain/test-domain"
    
    mock_repo = MagicMock()
    mock_repo.attr_arn = "arn:aws:codeartifact:us-east-1:123456789012:repository/test-domain/test-repo"
    
    # Create a mock config
    code_artifact_config = MagicMock()
    code_artifact_config.domain_name = "test-domain"
    code_artifact_config.account = "123456789012"
    code_artifact_config.region = "us-east-1"
    
    # Set up the stack
    stack.domain = mock_domain
    stack.repositories = {"test-repo": mock_repo}
    stack.code_artifact_config = code_artifact_config
    
    # Mock the CfnOutput constructor
    with patch("aws_cdk.CfnOutput") as mock_cfn_output:
        # Call the add outputs method
        stack._add_outputs()
        
        # Verify CfnOutput was called for domain and repository
        assert mock_cfn_output.call_count == 3  # Domain ARN, Domain URL, Repository ARN


def test_code_artifact_config():
    """Test CodeArtifactConfig class"""
    # Test with minimal configuration
    deployment = MagicMock()
    deployment.build_resource_name.side_effect = lambda x: f"test-{x}"
    deployment.account = "123456789012"
    deployment.region = "us-east-1"
    
    minimal_config = CodeArtifactConfig({
        "domain_name": "minimal-domain"
    }, deployment)
    
    # Check that the domain name was loaded
    assert minimal_config.domain_name == "test-minimal-domain"
    assert minimal_config.domain_description is None
    assert minimal_config.repositories == []
    assert minimal_config.upstream_repositories == []
    assert minimal_config.external_connections == []
    assert minimal_config.account == "123456789012"
    assert minimal_config.region == "us-east-1"
    
    # Test with full configuration
    full_config = CodeArtifactConfig({
        "domain_name": "full-domain",
        "domain_description": "Full domain description",
        "repositories": [
            {
                "name": "npm-repo",
                "description": "NPM repository",
                "external_connections": ["public:npm"]
            },
            {
                "name": "python-repo",
                "description": "Python repository",
                "external_connections": ["public:pypi"],
                "upstream_repositories": ["npm-repo"]
            }
        ],
        "upstream_repositories": ["other-domain/repo"],
        "external_connections": ["public:npm", "public:pypi"],
        "account": "987654321098",
        "region": "us-west-2"
    }, deployment)
    
    # Check that the configuration was loaded
    assert full_config.domain_name == "test-full-domain"
    assert full_config.domain_description == "Full domain description"
    assert len(full_config.repositories) == 2
    assert full_config.repositories[0]["name"] == "npm-repo"
    assert full_config.repositories[1]["name"] == "python-repo"
    assert full_config.upstream_repositories == ["other-domain/repo"]
    assert full_config.external_connections == ["public:npm", "public:pypi"]
    assert full_config.account == "987654321098"
    assert full_config.region == "us-west-2"
