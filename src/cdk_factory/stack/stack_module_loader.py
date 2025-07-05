"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import importlib
import importlib.util
import os
import pkgutil
from importlib.machinery import FileFinder
from pathlib import Path
from typing import cast


class ModuleLoader:
    """Load Dynamic Modules"""

    def __init__(self):
        pass

    def load_known_modules(self):
        """Load the known modules"""
        path = str(Path(__file__).parents[1].resolve())
        path = os.path.join(path, "stack_library")

        # get all files in the directory
        paths = [os.path.join(path, name) for name in os.listdir(path)]

        for loader, module_name, _ in pkgutil.iter_modules(paths):

            loader_with_path = cast(FileFinder, loader)
            module_path = str(loader_with_path.path)

            # get everything after cdk_factory
            namespaces = module_path.split("cdk_factory")[1].split(os.sep)[1:]
            module_path = ".".join(namespaces)
            library = f"cdk_factory.{module_path}.{module_name}"
            # import the library
            importlib.import_module(library)
