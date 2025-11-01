"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, List

from aws_lambda_powertools import Logger
from boto3_assist.ssm.parameter_store.parameter_store import ParameterStore
from boto3_assist.s3.s3_object import S3Object
from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility

logger = Logger()

parameters = ParameterStore()


class CdkConfig:
    """
    Cdk Configuration
    """

    def __init__(
        self,
        config_path: str,
        cdk_context: dict | None,
        runtime_directory: str | None,
        paths: Optional[List[str]] = None,
    ) -> None:
        self.cdk_context = cdk_context

        self._config_file_path: str | None = config_path
        self._resolved_config_file_path: str | None = None
        self._env_vars: Dict[str, str] = {}
        self._runtime_directory = runtime_directory
        self._paths: List[str] = paths or []  # type: ignore
        self.config = self.__load(config_path)

    def get_config_path_environment_setting(self) -> str:
        """
        This should be a relative config or an S3
        """

        if not self._config_file_path:
            raise ValueError("Config file path is not set")
        # check for a string, which should be a path
        if isinstance(self._config_file_path, str):
            # resolve the path
            self._resolved_config_file_path = self.__resolve_config_file_path(
                config_file=self._config_file_path
            )

            if not self._resolved_config_file_path:
                raise FileNotFoundError(self._config_file_path)

            if not os.path.exists(self._resolved_config_file_path):
                raise FileNotFoundError(self._resolved_config_file_path)

        config_path = self._config_file_path
        runtime_directory = self._runtime_directory
        print(f"👉 Config Path: {config_path}")
        print(f"👉 Runtime Directory: {runtime_directory}")

        if not runtime_directory:
            raise ValueError("Missing Runtime Directory")

        relative_config_path = ""
        # is this a relative path or a real path
        if not config_path.startswith("."):
            # Ensure both paths are absolute to avoid mixing absolute and relative paths
            abs_config_path = os.path.abspath(config_path)
            abs_runtime_directory = os.path.abspath(runtime_directory)
            
            root_path = os.path.commonpath([abs_config_path, abs_runtime_directory])
            if root_path in abs_config_path:
                relative_config_path = abs_config_path.replace(root_path, ".")

            print(f"👉 Relative Config: {relative_config_path}")
        else:
            relative_config_path = config_path

        if relative_config_path.startswith("/"):
            print("🚨 Warning this will probably fail in CI/CD.")

        return relative_config_path

    def __load(self, config_path: str | dict) -> Dict[str, Any]:
        config = self.__load_config(config_path)
        if config is None:
            raise ValueError("Failed to load Config")

        config = self.__resolved_config(config)

        return config

    def __load_config(self, config: str | dict) -> Dict[str, Any]:
        """Loads the configuration"""

        # check for a string, which should be a path
        if isinstance(config, str):
            # resolve the path
            self._resolved_config_file_path = self.__resolve_config_file_path(
                config_file=config
            )

            if not self._resolved_config_file_path:
                raise FileNotFoundError(config)

            if not os.path.exists(self._resolved_config_file_path):
                raise FileNotFoundError(self._resolved_config_file_path)

            ju = JsonLoadingUtility(self._resolved_config_file_path)
            config_dict: dict = ju.load()
            return config_dict

        if isinstance(config, dict):
            return config

        if not isinstance(config, dict):
            raise ValueError(
                "Failed to load Config. Config must be a dictionary at this point."
            )

    def __resolve_config_file_path(self, config_file: str):
        """Resolve the config file path (locally or s3://)"""

        paths = self._paths
        paths.append(self._runtime_directory)
        # is this a local path
        for path in paths:
            tmp = str(Path(os.path.join(path, config_file)).resolve())
            if os.path.exists(tmp):
                return tmp

        local_path_runtime = self._runtime_directory
        if config_file.startswith("s3://"):
            # download the file to a local temp file
            # NOTE: this is a live call to boto3 to get the config
            file = self.__get_file_from_s3(s3_path=config_file)
            if file is None:
                raise FileNotFoundError(config_file)
            else:
                config_file = file

        if not os.path.exists(config_file):
            config_file = os.path.join(local_path_runtime, config_file)

        if not os.path.exists(config_file):
            raise FileNotFoundError(config_file)
        return config_file

    def __get_file_from_s3(self, s3_path: str) -> str | None:
        s3_object = S3Object(connection=None)
        bucket = s3_path.replace("s3://", "").split("/")[0]
        key = s3_path.replace(f"s3://{bucket}/", "")

        try:
            logger.info(f"⬇️ Downloading {s3_path} from S3")
            config_path = s3_object.download_file(bucket=bucket, key=key)
        except Exception as e:
            error = f"🚨 Failed to download {s3_path} from S3. {e}"
            logger.error(error)
            raise FileNotFoundError(error)

        return config_path

    def __resolved_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        replacements = {}
        if "cdk" in config:
            if "parameters" in config["cdk"]:
                parameters = config.get("cdk", {}).get("parameters", [])
                parameter: Dict[str, Any]
                for parameter in parameters:
                    placeholder = parameter.get("placeholder", None)
                    value = self.__get_cdk_parameter_value(parameter)
                    replacements[placeholder] = value or ""
                    # do a find replace on the config
                    print(f"\t\t👉 Replacing {placeholder} with {value}")

        if self._resolved_config_file_path is None:
            raise ValueError("Config file path is not set")

        file_name = os.path.join(".dynamic", os.path.basename(self._resolved_config_file_path))
        path = os.path.join(Path(self._resolved_config_file_path).parent, file_name)
        
        if not os.path.exists(Path(path).parent):
            os.makedirs(Path(path).parent)
        cdk = config.get("cdk", {})
        if replacements:
            config = JsonLoadingUtility.recursive_replace(config, replacements)
            print(f"📀 Saving config to {path}")
            # add the original cdk back
            config["cdk"] = cdk

        JsonLoadingUtility.save(config, path)
        return config

    def __get_cdk_parameter_value(self, parameter: Dict[str, Any]) -> str | None:
        cdk_parameter_name = parameter.get("cdk_parameter_name", None)
        # ssm_parameter_name = parameter.get("ssm_parameter_name", None)
        environment_variable_name = parameter.get("env_var_name", None)
        static_value = parameter.get("value", None)
        required = str(parameter.get("required", True)).lower() == "true"
        value: str | None = None

        if self.cdk_context is None:
            raise ValueError("cdk_context is None")

        value = self.cdk_context.get(cdk_parameter_name)

        print(f"\t📦 Value for {cdk_parameter_name}: {value}")
        if static_value is not None:
            value = static_value
        elif environment_variable_name is not None and not value:
            value = os.environ.get(environment_variable_name, None)
            if (value is None or str(value).strip() == "") and required:
                raise ValueError(
                    f"Failed to get value for environment variable {environment_variable_name}"
                )

        if environment_variable_name is not None and value is not None:
            self._env_vars[environment_variable_name] = value

        if value is None and not required:
            return None

        if value is None:
            raise ValueError(
                f"Failed to get value for parameter {parameter.get('placeholder', '')}"
            )
        return value

    @property
    def environment_vars(self) -> Dict[str, str]:
        """
        Gets the environment variables
        """
        return self._env_vars
