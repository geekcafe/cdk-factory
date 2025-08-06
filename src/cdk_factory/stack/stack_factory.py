"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Type

from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_loader import ModuleLoader
from cdk_factory.stack.stack_module_registry import modules


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
        **kwargs,
    ) -> IStack:
        """Loads a particular module"""
        # print(f"loading module: {module_name}")
        stack_class: Type[IStack] = modules.get(module_name)
        if not stack_class:
            raise ValueError(f"Failed to load module: {module_name}")

        module = stack_class(scope=scope, id=id, **kwargs)

        return module
