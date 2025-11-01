"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from abc import ABCMeta, abstractmethod
import jsii
from constructs import Construct
from aws_cdk import Stack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin


class StackABCMeta(jsii.JSIIMeta, ABCMeta):
    """StackABCMeta"""


class IStack(Stack, StandardizedSsmMixin, metaclass=StackABCMeta):
    """
    IStack for Dynamically loaded Factory Stacks
    Only imports from constructs and abc to avoid circular dependencies.
    """

    @abstractmethod
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        # Initialize Stack first
        Stack.__init__(self, scope, id, **kwargs)
        # Initialize StandardizedSsmMixin (no super() call to avoid MRO issues)
        StandardizedSsmMixin.__init__(self, **kwargs)

    @abstractmethod
    def build(self, *, stack_config, deployment, workload) -> None:
        """
        Build method that every stack must implement.
        Accepts stack_config, deployment, and workload (types are duck-typed to avoid circular imports).
        """
        pass
