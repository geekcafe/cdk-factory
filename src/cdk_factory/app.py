#!/usr/bin/env python3
"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""
import os
from pathlib import Path
import aws_cdk
from aws_cdk.cx_api import CloudAssembly

from cdk_factory.utilities.commandline_args import CommandlineArgs
from cdk_factory.workload.workload_factory import WorkloadFactory
from cdk_factory.utilities.configuration_loader import ConfigurationLoader
from cdk_factory.version import __version__


class CdkAppFactory:
    """CDK App Wrapper"""

    def __init__(
        self,
        args: CommandlineArgs | None = None,
        runtime_directory: str | None = None,
        config_path: str | None = None,
        outdir: str | None = None,
        add_env_context: bool = True,
    ) -> None:

        self.args = args or CommandlineArgs()
        self.outdir = outdir or self.args.outdir
        self.app: aws_cdk.App = aws_cdk.App()
        self.runtime_directory = runtime_directory or str(Path(__file__).parent)
        self.config_path: str | None = config_path
        self.add_env_context = add_env_context

    def synth(
        self,
        cdk_app_file: str | None = None,
        paths: list[str] | None = None,
        **kwargs,
    ) -> CloudAssembly:
        """
        The AWS CDK Deployment pipeline is defined here
        Returns:
            CloudAssembly: CDK CloudAssembly
        """

        print(f"👋 Synthesizing CDK App from the cdk-factory version: {__version__}")

        if not paths:
            paths = []

        paths.append(self.app.outdir)
        paths.append(__file__)
        if cdk_app_file:
            paths.append(cdk_app_file)

        self.config_path = ConfigurationLoader().get_runtime_config(
            relative_config_path=self.config_path,
            args=self.args,
            app=self.app,
            runtime_directory=self.runtime_directory,
        )

        print("config_path", self.config_path)
        if not self.config_path:
            raise Exception("No configuration file provided")
        if not os.path.exists(self.config_path):
            raise Exception("Configuration file does not exist: " + self.config_path)
        workload: WorkloadFactory = WorkloadFactory(
            app=self.app,
            config_path=self.config_path,
            cdk_app_file=cdk_app_file,
            paths=paths,
            runtime_directory=self.runtime_directory,
            outdir=self.outdir,
            add_env_context=self.add_env_context,
        )

        assembly: CloudAssembly = workload.synth()

        print("☁️ cloud assembly dir", assembly.directory)

        return assembly


if __name__ == "__main__":
    # deploy_test()
    cmd_args: CommandlineArgs = CommandlineArgs()
    cdk_app: CdkAppFactory = CdkAppFactory(args=cmd_args)
    cdk_app.synth()
