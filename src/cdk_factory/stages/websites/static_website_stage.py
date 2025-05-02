"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk
from constructs import Construct
from cdk_factory.stack_library.websites.static_website_stack import StaticWebSiteStack


class StaticWebsiteStage(aws_cdk.Stage):
    """
    Pipeline Stage for deployment of a static web site

    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=redefined-builtin
        config: dict,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)
        # Create the website stack with the given deployment configuration.
        StaticWebSiteStack(self, "WebsiteStack", config=config)


if __name__ == "__main__":
    print("Testing")
