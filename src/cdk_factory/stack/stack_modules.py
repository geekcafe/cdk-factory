"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Dict, Type

from cdk_factory.interfaces.istack import IStack


class Modules:
    """Dynamic Modules"""

    def __init__(self) -> None:
        self.registry: Dict[str, Type[IStack]] = {}

    def get(self, module_name: str) -> Type[IStack]:
        """Get a module from the registry"""
        module = self.registry.get(module_name)

        if not module:
            raise ValueError(f"Failed to load module: {module_name}")

        if not hasattr(module, "build") or not callable(module.build):
            raise ValueError(
                f"Module {module_name} does not implement the required 'build' method"
            )

        return module
