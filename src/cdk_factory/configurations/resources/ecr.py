"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class ECRConfig(EnhancedBaseConfig):
    """ECR Configuration"""

    def __init__(
        self, config: dict, deployment: DeploymentConfig | None = None
    ) -> None:
        super().__init__(config, resource_type="ecr", resource_name=config.get("name", "ecr") if config else "ecr")
        self.__config = config
        self.__deployment = deployment
        self.__ssm_prefix_template = config.get("ssm_prefix_template", None)

    @property
    def name(self) -> str:
        """Repository Name"""
        if self.__config and isinstance(self.__config, dict):
            name = self.__config.get("name", "")
            if not self.__deployment:
                raise RuntimeError("Deployment is not defined")

            return self.__deployment.build_resource_name(name)

        raise RuntimeError('ECR Configuration is missing the "name" key/value pair')

    @property
    def uri(self) -> str:
        """Repository Uri"""
        uri = None
        if self.__config and isinstance(self.__config, dict):
            uri = self.__config.get("uri")

        if not uri:
            uri = f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{self.name}"
        return uri

    @property
    def arn(self) -> str:
        """Repository Arn"""
        arn = None
        if self.__config and isinstance(self.__config, dict):
            arn = self.__config.get("arn")
        if not arn:
            arn = f"arn:aws:ecr:{self.region}:{self.account}:repository/{self.name}"
        return arn

    @property
    def image_scan_on_push(self) -> bool:
        """Perform an image scan on Push"""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("image_scan_on_push")).lower() == "true"

        return False

    @property
    def empty_on_delete(self) -> bool:
        """Empty a repository on a detele request."""
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("empty_on_delete")).lower() == "true"

        return False

    @property
    def auto_delete_untagged_images_in_days(self) -> int | None:
        """
        Clear out untagged images after x days.  This helps save costs.
        Untagged images will stay forever if you don't clean them out.
        """
        days = None
        if self.__config and isinstance(self.__config, dict):
            days = self.__config.get("auto_delete_untagged_images_in_days")
            if days:
                days = int(days)

        return days

    @property
    def use_existing(self) -> bool:
        """
        Use Existing Repository
        """
        if self.__config and isinstance(self.__config, dict):
            return str(self.__config.get("use_existing")).lower() == "true"

        return False

    @property
    def account(self) -> str:
        """Account"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("account")

        if not value and self.__deployment:
            value = self.__deployment.account

        if not value:
            raise RuntimeError("Account is not defined")
        return value

    @property
    def region(self) -> str:
        """Region"""
        value: str | None = None
        if self.__config and isinstance(self.__config, dict):
            value = self.__config.get("region")

        if not value and self.__deployment:
            value = self.__deployment.region

        if not value:
            raise RuntimeError("Region is not defined")
        return value

    @property
    def cross_account_access(self) -> dict:
        """
        Cross-account access configuration.
        
        Example:
        {
            "enabled": true,
            "accounts": [os.environ.get("ECR_ALLOWED_ACCOUNT_1"), os.environ.get("ECR_ALLOWED_ACCOUNT_2")],
            "services": [
                {
                    "name": "lambda",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                    "condition": {
                        "StringLike": {
                            "aws:sourceArn": "arn:aws:lambda:*:*:function:*"
                        }
                    }
                },
                {
                    "name": "ecs-tasks",
                    "service_principal": "ecs-tasks.amazonaws.com",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
                },
                {
                    "name": "codebuild",
                    "service_principal": "codebuild.amazonaws.com",
                    "actions": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
                }
            ]
        }
        """
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("cross_account_access", {})
        return {}

    @property
    def cross_account_enabled(self) -> bool:
        """Whether cross-account access is explicitly enabled"""
        access_config = self.cross_account_access
        if access_config:
            return str(access_config.get("enabled", "true")).lower() == "true"
        return True  # Default to enabled for backward compatibility
        
    # SSM properties are now inherited from EnhancedBaseConfig
    # Keeping these for any direct access patterns in existing code
    @property
    def ssm_parameters(self) -> dict:
        """Get legacy SSM parameter paths (for backward compatibility)"""
        if self.__config and isinstance(self.__config, dict):
            return self.__config.get("ssm_parameters", {})
        return {}
        
    def format_ssm_path(self, path: str, resource_type: str, resource_name: str, attribute: str, context: dict = None) -> str:
        """Format an SSM parameter path using the configured template
        
        Args:
            path: The path or attribute name to format
            resource_type: The type of resource (e.g., 'ecr')
            resource_name: The name of the resource
            attribute: The attribute name (e.g., 'name', 'uri', 'arn')
            context: Additional context variables for template formatting
            
        Returns:
            Formatted SSM parameter path
        """
        # If path starts with '/', it's already a full path
        if path.startswith('/'):
            return path
            
        # Get the template from config, or use deployment default
        template = self.__ssm_prefix_template
        
        # If no template is defined at the resource level, check if deployment has one
        if not template and self.__deployment:
            # This would need to be implemented in DeploymentConfig
            if hasattr(self.__deployment, 'ssm_prefix_template'):
                template = self.__deployment.ssm_prefix_template
                
        # If still no template, use the default format
        if not template:
            return self.__deployment.get_ssm_parameter_name(resource_type, resource_name, attribute)
            
        # Format the template with available variables
        context = context or {}
        format_vars = {
            'deployment_name': self.__deployment.name if self.__deployment else '',
            'environment': self.__deployment.environment if self.__deployment else '',
            'workload_name': self.__deployment.workload_name if self.__deployment else '',
            'resource_type': resource_type,
            'resource_name': resource_name,
            'attribute': path,  # Use the path as the attribute if it's a simple name
        }
        
        # Add any additional context variables
        format_vars.update(context)
        
        # Format the template
        formatted_path = template.format(**format_vars)
        
        # Ensure the path starts with '/'
        if not formatted_path.startswith('/'):
            formatted_path = f'/{formatted_path}'
            
        return formatted_path
