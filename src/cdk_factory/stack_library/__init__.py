"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import pkgutil
import importlib


paths = []

try:
    paths = __path__
except:  # noqa: E722, pylint: disable=bare-except
    import os

    paths.append(os.path.dirname(__file__))


def load_stacks():
    """
    Dynamically import all modules in this package.
    """
    for loader, module_name, is_pkg in pkgutil.iter_modules(paths):
        libray = f"{__name__}.{module_name}"
        # print(f"importing library: {libray}")
        importlib.import_module(libray)
