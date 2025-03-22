#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import aws_cdk
from aws_cdk.cx_api import CloudAssembly

try:
    # helper to get our paths set
    import __paths__  # noqa: F401, pylint: disable=w0611
except ImportError:
    pass

from cdk_factory.utilities.commandline_args import CommandlineArgs
from cdk_factory.workload.workload_factory import WorkloadFactory


class CdkAppFactory:
    """CDK App Wrapper"""

    def __init__(
        self,
        args: CommandlineArgs | None = None,
        config: str | dict | None = None,
        outdir: str | None = None,
    ) -> None:
        if not args:
            args = CommandlineArgs()
        self.outdir = outdir or args.outdir
        self.app: aws_cdk.App = aws_cdk.App(outdir=outdir)

        self.config = config or args.config or self.app.node.try_get_context("config")

    def synth(
        self,
        cdk_app_file: str | None = None,
        paths: list[str] | None = None,
        **kwargs,
    ) -> CloudAssembly:
        """
        The AWS CDK Deployment pipeline is defined here
        Returns:
            CloudAssembly: CDK CloudAssemby
        """

        print("config", self.config)

        if not paths:
            paths = []

        paths.append(self.app.outdir)
        paths.append(__file__)
        if cdk_app_file:
            paths.append(cdk_app_file)
        workload: WorkloadFactory = WorkloadFactory(
            app=self.app, config=self.config, cdk_app_file=cdk_app_file, paths=paths
        )
        # add any external stacks to the app

        ca: CloudAssembly = workload.synth()

        # print("output dir", self.app.outdir)
        print("☁️ cloud assembly dir", ca.directory)

        return ca


if __name__ == "__main__":
    # deploy_test()
    cmd_args: CommandlineArgs = CommandlineArgs()
    cdkapp: CdkAppFactory = CdkAppFactory(args=cmd_args)
    cdkapp.synth()
