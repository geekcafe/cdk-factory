"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Type, Dict, Any, Optional

from aws_cdk import Environment
from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_loader import ModuleLoader
from cdk_factory.stack.stack_module_registry import modules
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig


class StackFactory:
    """Stack Factory"""
    
    # Default descriptions by module type
    DEFAULT_DESCRIPTIONS = {
        "vpc_stack": "VPC infrastructure with public and private subnets across multiple availability zones",
        "security_group_stack": "Security groups for network access control",
        "security_group_full_stack": "Security groups for ALB, ECS, RDS, and monitoring",
        "rds_stack": "Managed relational database instance with automated backups",
        "s3_bucket_stack": "S3 bucket for object storage",
        "media_bucket_stack": "S3 bucket for media asset storage with CDN integration",
        "static_website_stack": "Static website hosted on S3 with CloudFront distribution",
        "ecs_service_stack": "ECS service with auto-scaling and load balancing",
        "lambda_stack": "Lambda function for serverless compute",
        "api_gateway_stack": "API Gateway for REST API endpoints",
        "cloudfront_stack": "CloudFront CDN distribution",
        "monitoring_stack": "CloudWatch monitoring, alarms, and dashboards",
        "ecr_stack": "Elastic Container Registry for Docker images",
    }

    def __init__(self):
        ml: ModuleLoader = ModuleLoader()

        ml.load_known_modules()

    def load_module(
        self,
        module_name: str,
        scope,
        id: str,  # pylint: disable=redefined-builtin
        deployment: Optional[DeploymentConfig] = None,
        stack_config: Optional[StackConfig] = None,
        add_env_context: bool = True,
        **kwargs,
    ) -> IStack:
        """Loads a particular module"""
        # print(f"loading module: {module_name}")
        stack_class: Type[IStack] = modules.get(module_name)
        if not stack_class:
            raise ValueError(f"Failed to load module: {module_name}")

        # Add environment information if deployment is provided and add_env_context is True
        if deployment and add_env_context:
            env_kwargs = self._get_environment_kwargs(deployment)
            kwargs.update(env_kwargs)
        
        # Add description if not already provided in kwargs
        if "description" not in kwargs:
            description = self._get_stack_description(module_name, stack_config)
            if description:
                kwargs["description"] = description

        module = stack_class(scope=scope, id=id, **kwargs)

        return module
        
    def _get_environment_kwargs(self, deployment: DeploymentConfig) -> Dict[str, Any]:
        """Get environment kwargs from deployment config"""
        env = Environment(
            account=deployment.account,
            region=deployment.region
        )
        return {"env": env}
    
    def _get_stack_description(self, module_name: str, stack_config: Optional[StackConfig] = None) -> Optional[str]:
        """Get stack description from config or default"""
        # First check if stack_config has a description
        if stack_config and stack_config.description:
            return stack_config.description
        
        # Otherwise use default description based on module type
        return self.DEFAULT_DESCRIPTIONS.get(module_name)
