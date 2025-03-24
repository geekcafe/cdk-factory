"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from pathlib import Path
from typing import Any, Dict

from aws_lambda_powertools import Logger
from boto3_assist.ssm.parameter_store.parameter_store import ParameterStore

from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility

logger = Logger()

parameters = ParameterStore()


class CdkConfig:
    """
    Cdk Configuration
    """

    def __init__(self, config: str | dict, cdk_context: dict | None) -> None:
        self.cdk_context = cdk_context
        self.config = self.__load(config)
        self.__config_file_path: str | None = None

    def __load(self, config: str | dict) -> Dict[str, Any]:
        config = self.__load_config(config)
        if config is None:
            raise ValueError("Failed to load Config")

        config = self.__resolved_config(config)

        return config

    def __load_config(self, config: str | dict) -> Dict[str, Any]:
        if isinstance(config, str):
            self.__config_file_path = config
            if not os.path.exists(self.__config_file_path):
                raise FileNotFoundError(self.__config_file_path)

            ju = JsonLoadingUtility(self.__config_file_path)
            config = ju.load()
            return config

        if isinstance(config, dict):
            return config

        if not isinstance(config, dict):
            raise ValueError(
                "Failed to load Config. Config must be a dictionary at this point."
            )

    def __resolved_config(self, config: str | dict) -> Dict[str, Any]:
        replacements = {}
        if "cdk" in config:
            if "paramaters" in config["cdk"]:
                paramaters = config.get("cdk", {}).get("paramaters", [])
                parameter: Dict[str, Any]
                for parameter in paramaters:
                    placeholder = parameter.get("placeholder", None)
                    value = self.__get_cdk_parameter_value(parameter)
                    replacements[placeholder] = value or ""
                    # do a find replace on the config
                    print(f"replacing {placeholder} with {value}")

        file_name = f".dynamic_{os.path.basename(self.__config_file_path)}"
        path = os.path.join(Path(self.__config_file_path).parent, file_name)

        cdk = config.get("cdk", {})
        if replacements and len(replacements) > 0:
            config = JsonLoadingUtility.recursive_replace(config, replacements)
            print(f"Saving config to {path}")
            # add the original cdk back
            config["cdk"] = cdk

        JsonLoadingUtility.save(config, path)
        return config

    def __get_cdk_parameter_value(self, parameter: Dict[str, Any]) -> str | None:
        cdk_parameter_name = parameter.get("cdk_parameter_name", None)
        ssm_parameter_name = parameter.get("ssm_parameter_name", None)
        static_value = parameter.get("value", None)
        value: str | None = None
        # see if we have a place holder

        if self.cdk_context is None:
            raise ValueError("cdk_context is None")
        context_value = self.cdk_context.get(cdk_parameter_name)
        if cdk_parameter_name is not None and context_value:
            # store this in the parameter store later
            if ssm_parameter_name:
                parameters.put_parameter(ssm_parameter_name, context_value)
            else:
                print(
                    "WARNING: there is a config value without a parameter store location. "
                    "If this is going into a CI/CD, this operation will mostlikely fail unless the parameter is "
                    "also added to the CI/CD synth command. "
                )
            value = self.cdk_context.get(cdk_parameter_name, "TBD")
            print("todo: store in parameter store")
        elif ssm_parameter_name is not None:
            # we need to get the value from cdk
            try:
                value = parameters.get_parameter(ssm_parameter_name, True)
            except parameters.client.exceptions.ParameterNotFound:
                logger.warning(
                    f"Parameter {ssm_parameter_name} not found in Parameter Store"
                )
                value = None

        elif static_value is not None:
            value = static_value

        if value is None:
            raise ValueError(
                f"Failed to get value for parameter {parameter.get('placeholder', '')}"
            )
        return value
