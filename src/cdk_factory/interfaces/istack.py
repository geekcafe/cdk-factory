"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from abc import ABCMeta, abstractmethod
import jsii
from constructs import Construct
from aws_cdk import Stack
from cdk_factory.interfaces.ssm_parameter_mixin import SsmParameterMixin


class StackABCMeta(jsii.JSIIMeta, ABCMeta):
    """StackABCMeta"""


class IStack(Stack, SsmParameterMixin, metaclass=StackABCMeta):
    """
    IStack for Dynamically loaded Factory Stacks
    Only imports from constructs and abc to avoid circular dependencies.
    """

    @abstractmethod
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

    @abstractmethod
    def build(self, *, stack_config, deployment, workload) -> None:
        """
        Build method that every stack must implement.
        Accepts stack_config, deployment, and workload (types are duck-typed to avoid circular imports).
        """
        pass
