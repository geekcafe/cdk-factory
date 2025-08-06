"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class StackConfig:
    """A Cloud Formation Stack built by the CDK"""

    def __init__(self, stack: dict, workload: dict) -> None:
        self.__stack: dict = stack
        self.__workload: dict = workload

    @property
    def workload(self) -> dict:
        """
        Returns the workload
        """
        return self.__workload

    @property
    def dictionary(self) -> dict:
        """
        Returns the dictionary of the stack
        """
        return self.__stack

    @property
    def name(self) -> str:
        """
        Returns the stack name
        """
        value = self.dictionary.get("name")
        if not value:
            raise ValueError("Stack name is not defined in the configuration")
        return value

    @property
    def description(self) -> str | None:
        """
        Returns the stack description
        """
        return self.dictionary.get("description")

    @property
    def module(self) -> str:
        """
        Returns the module name
        """
        value = self.dictionary.get("module")
        if not value:
            raise ValueError(
                "Stack module is required but it is not defined in the configuration"
            )
        return value

    @property
    def kwargs(self) -> dict:
        """
        Returns the kwargs
        """
        return self.__stack.get("kwargs", {})

    @property
    def enabled(self) -> bool:
        """
        Returns if the stack is enabled
        """
        value = self.dictionary.get("enabled")
        return str(value).lower() == "true" or value is True

    @property
    def dependencies(self) -> List[str]:
        """
        Returns the stack dependencies
        """
        value = self.dictionary.get("dependencies")
        if value is None:
            return []
        if isinstance(value, list):
            return value
        else:
            raise ValueError("Stack dependencies must be a list of strings")

    def build_id(self) -> str:
        """
        Returns the stack name
        """
        return f"{self.name}"
