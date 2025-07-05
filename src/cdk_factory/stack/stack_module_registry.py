"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from cdk_factory.stack.stack_modules import Modules

modules = Modules()


def register_stack(module_name):
    """Register a module to the global registry"""

    def decorator(cls):
        modules.registry[module_name] = cls
        return cls

    return decorator
