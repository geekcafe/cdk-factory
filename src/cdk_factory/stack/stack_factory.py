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


class StackFactory:
    """Stack Factory"""

    def __init__(self):
        ml: ModuleLoader = ModuleLoader()

        ml.load_known_modules()

    def load_module(
        self,
        module_name: str,
        scope,
        id: str,  # pylint: disable=redefined-builtin
        deployment: Optional[DeploymentConfig] = None,
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

        module = stack_class(scope=scope, id=id, **kwargs)

        return module
        
    def _get_environment_kwargs(self, deployment: DeploymentConfig) -> Dict[str, Any]:
        """Get environment kwargs from deployment config"""
        env = Environment(
            account=deployment.account,
            region=deployment.region
        )
        return {"env": env}
