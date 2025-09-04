"""
CodeArtifact Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional

import aws_cdk as cdk
from aws_cdk import aws_codeartifact as codeartifact
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.code_artifact import CodeArtifactConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="CodeArtifactStack")


@register_stack("code_artifact_library_module")
@register_stack("code_artifact_stack")
class CodeArtifactStack(IStack, EnhancedSsmParameterMixin):
    """
    Reusable stack for AWS CodeArtifact.
    Supports creating domains and repositories with configurable settings.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.code_artifact_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.domain = None
        self.repositories = {}

    def build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Build the CodeArtifact stack"""
        self._build(stack_config, deployment, workload)

    def _build(self, stack_config: StackConfig, deployment: DeploymentConfig, workload: WorkloadConfig) -> None:
        """Internal build method for the CodeArtifact stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Load CodeArtifact configuration
        self.code_artifact_config = CodeArtifactConfig(
            stack_config.dictionary.get("code_artifact", {}),
            deployment
        )
        
        # Create the domain
        self._create_domain()
        
        # Create repositories
        for repo_config in self.code_artifact_config.repositories:
            self._create_repository(repo_config)
            
        # Add outputs
        self._add_outputs()

    def _create_domain(self) -> codeartifact.CfnDomain:
        """Create a CodeArtifact domain"""
        domain_name = self.code_artifact_config.domain_name
        
        # Configure domain properties
        domain_props = {
            "domain_name": domain_name,
        }
        
        # Add description if provided
        if self.code_artifact_config.domain_description:
            domain_props["domain_description"] = self.code_artifact_config.domain_description
        
        # Create the domain
        self.domain = codeartifact.CfnDomain(
            self,
            f"{domain_name}-domain",
            **domain_props
        )
        
        return self.domain

    def _create_repository(self, repo_config: Dict[str, Any]) -> codeartifact.CfnRepository:
        """Create a CodeArtifact repository"""
        repo_name = repo_config.get("name")
        if not repo_name:
            logger.error("Repository configuration missing name")
            raise ValueError("Repository configuration missing name")
            
        # Build the resource name
        resource_name = self.deployment.build_resource_name(repo_name)
        
        # Configure repository properties
        repo_props = {
            "domain_name": self.code_artifact_config.domain_name,
            "repository_name": resource_name,
            "description": repo_config.get("description"),
        }
        
        # Add external connections if specified
        external_connections = repo_config.get("external_connections", [])
        if external_connections:
            repo_props["external_connections"] = [
                {"external_connection_name": connection} 
                for connection in external_connections
            ]
        
        # Add upstream repositories if specified
        upstream_repos = repo_config.get("upstream_repositories", [])
        if upstream_repos:
            repo_props["upstream_repositories"] = [
                {"repository_name": self.deployment.build_resource_name(repo)} 
                for repo in upstream_repos
            ]
        
        # Remove None values
        repo_props = {k: v for k, v in repo_props.items() if v is not None}
        
        # Create the repository
        repository = codeartifact.CfnRepository(
            self,
            f"{resource_name}-repo",
            **repo_props
        )
        
        # Add dependency on domain
        repository.add_dependency(self.domain)
        
        # Store the repository for later reference
        self.repositories[resource_name] = repository
        
        return repository

    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for the CodeArtifact resources"""
        # Domain outputs
        if self.domain:
            domain_name = self.code_artifact_config.domain_name
            
            # Domain ARN
            cdk.CfnOutput(
                self,
                f"{domain_name}-domain-arn",
                value=self.domain.attr_arn,
                export_name=f"{self.deployment.build_resource_name(domain_name)}-domain-arn"
            )
            
            # Domain URL
            cdk.CfnOutput(
                self,
                f"{domain_name}-domain-url",
                value=f"https://{self.code_artifact_config.account}.d.codeartifact.{self.code_artifact_config.region}.amazonaws.com/",
                export_name=f"{self.deployment.build_resource_name(domain_name)}-domain-url"
            )
        
        # Repository outputs
        for repo_name, repo in self.repositories.items():
            # Repository ARN
            cdk.CfnOutput(
                self,
                f"{repo_name}-repo-arn",
                value=repo.attr_arn,
                export_name=f"{self.deployment.build_resource_name(repo_name)}-repo-arn"
            )
