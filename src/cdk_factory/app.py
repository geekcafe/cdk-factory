#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
import os
import aws_cdk
from aws_cdk.cx_api import CloudAssembly

from cdk_factory.utilities.commandline_args import CommandlineArgs
from cdk_factory.workload.workload_factory import WorkloadFactory
from cdk_factory.utilities.configuration_loader import ConfigurationLoader


class CdkAppFactory:
    """CDK App Wrapper"""

    def __init__(
        self,
        args: CommandlineArgs | None = None,
        runtime_directory: str | None = None,
        realtive_config_path: str | None = None,
        outdir: str | None = None,
    ) -> None:
        if not args:
            args = CommandlineArgs()
        self.outdir = outdir or args.outdir
        self.app: aws_cdk.App = aws_cdk.App()
        self.runtime_directory = runtime_directory
        self.config_path = ConfigurationLoader().get_runtime_config(
            realtive_config_path=realtive_config_path,
            args=args,
            app=self.app,
            runtime_directory=runtime_directory,
        )
        self.relative_config_path = realtive_config_path

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

        print("config_path", self.config_path)

        if not paths:
            paths = []

        paths.append(self.app.outdir)
        paths.append(__file__)
        if cdk_app_file:
            paths.append(cdk_app_file)
        workload: WorkloadFactory = WorkloadFactory(
            app=self.app,
            relative_config_path=self.relative_config_path,
            cdk_app_file=cdk_app_file,
            paths=paths,
            runtime_directory=self.runtime_directory,
            outdir=self.outdir,
        )

        assembly: CloudAssembly = workload.synth()

        print("☁️ cloud assembly dir", assembly.directory)

        return assembly


if __name__ == "__main__":
    # deploy_test()
    cmd_args: CommandlineArgs = CommandlineArgs()
    cdkapp: CdkAppFactory = CdkAppFactory(args=cmd_args)
    cdkapp.synth()
