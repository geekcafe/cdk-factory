"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk
from constructs import Construct


class PipelineStage(aws_cdk.Stage):
    """
    Generic Stage to load one or more stacks
    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=W0622
        **kwargs,
    ):
        super().__init__(scope=scope, id=id, **kwargs)
