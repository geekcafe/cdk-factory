"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from abc import ABCMeta, abstractmethod

import jsii
from aws_cdk import Stack
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# Create a combined metaclass inheriting from jsii.JSIIMeta and ABCMeta.
class StackABCMeta(jsii.JSIIMeta, ABCMeta):
    """StackABCMeta"""


class IStack(Stack, metaclass=StackABCMeta):
    """IStack for Dynamically loaded Factory Stacks"""

    @abstractmethod
    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=redefined-builtin
        **kwargs,
    ) -> None:
        """
        Constructor that every stack must implement.
        You can document here the required signature.
        """
        super().__init__(scope, id, **kwargs)

    @abstractmethod
    def build(
        self,
        *,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """
        Build method that every stack must implement.
        """
