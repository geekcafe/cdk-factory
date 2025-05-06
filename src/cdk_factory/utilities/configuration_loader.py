"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import aws_cdk
from cdk_factory.utilities.commandline_args import CommandlineArgs


class ConfigurationLoader:
    def __init__(self):
        pass

    @property
    def commandline_arg_name(self) -> str:
        return "CdkConfigPath"

    @property
    def environment_variable_name(self) -> str:
        return "CDK_CONFIG_PATH"

    def get_runtime_config(
        self,
        config_path: str | None,
        args: CommandlineArgs | None,
        app: aws_cdk.App | None,
    ) -> str:

        node = app.node if app else None
        config_node_path: str | None = None
        args_config = args.config if args else None

        if node:
            config_node_path = node.try_get_context(self.commandline_arg_name)
        runtime_config = (
            config_path
            or args_config
            or config_node_path
            or os.getenv(self.environment_variable_name, None)
        )

        if not runtime_config:
            raise Exception("No configuration file provided")

        if str(runtime_config).startswith("/"):
            print(
                "WARNING: a full config path was found, switching to default config.json"
            )
            print(f"Path: {runtime_config}")
            return "config.json"

        return runtime_config
