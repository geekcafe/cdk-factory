"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, List

from aws_lambda_powertools import Logger
from boto3_assist.ssm.parameter_store.parameter_store import ParameterStore
from boto3_assist.s3.s3_object import S3Object
from cdk_factory.utilities.json_loading_utility import JsonLoadingUtility

logger = Logger(__name__)

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
        self._dynamic_config_path: str | None = None
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

        # Pre-resolve chained references in replacement values
        # (e.g., TARGET_ACCOUNT_ROLE_ARN value contains {{AWS_ACCOUNT}})
        for _ in range(5):  # max passes to prevent infinite loops on circular refs
            changed = False
            for key, value in replacements.items():
                if isinstance(value, str) and "{{" in value:
                    new_value = value
                    for find_str, replace_str in replacements.items():
                        if isinstance(replace_str, str):
                            new_value = new_value.replace(find_str, replace_str)
                    if new_value != value:
                        replacements[key] = new_value
                        changed = True
            if not changed:
                break

        if self._resolved_config_file_path is None:
            raise ValueError("Config file path is not set")

        file_name = os.path.join(
            ".dynamic", os.path.basename(self._resolved_config_file_path)
        )
        path = os.path.join(Path(self._resolved_config_file_path).parent, file_name)
        self._dynamic_config_path = path

        if not os.path.exists(Path(path).parent):
            os.makedirs(Path(path).parent)
        cdk = config.get("cdk", {})
        if replacements:
            config = JsonLoadingUtility.recursive_replace(config, replacements)
            print(f"📀 Saving config to {path}")
            # add the original cdk back
            config["cdk"] = cdk

        # Check for unresolved placeholders after resolution
        self._check_unresolved_placeholders(config, self._resolved_config_file_path)

        # Resolve lambda_config_paths: walk the config and find SQS stacks that
        # reference lambda stacks for consumer queue discovery. Extract the consumer
        # queues from the already-resolved lambda stack configs and populate the
        # SQS stack's sqs.queues array. This happens here so that by the time
        # any stack build() runs, the queues are already plain resolved data.
        self._resolve_lambda_config_paths(config)

        JsonLoadingUtility.save(config, path)
        return config

    @staticmethod
    def _resolve_lambda_config_paths(config: Dict[str, Any]) -> None:
        """Resolve lambda_config_paths references in SQS stack configs.

        Walks the fully-resolved config tree. For any stack with module == "sqs_stack"
        and a "lambda_config_paths" key, finds the referenced lambda stacks (by matching
        module == "lambda_stack" in the same deployment), extracts consumer queue
        definitions, and appends them to the SQS stack's sqs.queues array.

        This runs after __inherits__ resolution and placeholder substitution, so all
        queue_name values are fully resolved.
        """
        workload = config.get("workload", {})
        for deployment in workload.get("deployments", []):
            pipeline = deployment.get("pipeline", {})
            if not isinstance(pipeline, dict):
                continue
            # Build a lookup of all lambda stacks by name across all stages
            all_lambda_stacks: Dict[str, dict] = {}
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                for stack in stage.get("stacks", []):
                    if not isinstance(stack, dict):
                        continue
                    if stack.get("module") == "lambda_stack":
                        all_lambda_stacks[stack.get("name", "")] = stack

            # Now find SQS stacks with lambda_config_paths and resolve them
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                for stack in stage.get("stacks", []):
                    if not isinstance(stack, dict):
                        continue
                    if stack.get("module") != "sqs_stack":
                        continue
                    lambda_paths = stack.get("lambda_config_paths", [])
                    if not lambda_paths:
                        continue

                    # Extract consumer queues from all lambda stacks
                    # (we match by scanning all lambda stacks, not by path)
                    discovered: Dict[str, dict] = {}
                    for _ls_name, ls_dict in all_lambda_stacks.items():
                        resources = ls_dict.get("resources", [])
                        if not isinstance(resources, list):
                            continue
                        for resource in resources:
                            if not isinstance(resource, dict):
                                continue
                            sqs_block = resource.get("sqs", {})
                            if not isinstance(sqs_block, dict):
                                continue
                            for queue in sqs_block.get("queues", []):
                                if queue.get("type") == "consumer":
                                    qname = queue.get("queue_name", "")
                                    if qname and qname not in discovered:
                                        discovered[qname] = dict(queue)

                    # Merge into the SQS stack's sqs.queues
                    if discovered:
                        sqs_section = stack.setdefault("sqs", {})
                        existing_queues = sqs_section.get("queues", [])
                        existing_names = {
                            q.get("queue_name", "") for q in existing_queues
                        }
                        for qname, qdict in discovered.items():
                            if qname not in existing_names:
                                existing_queues.append(qdict)
                        sqs_section["queues"] = existing_queues
                        print(
                            f"📦 Resolved {len(discovered)} consumer queues into "
                            f"SQS stack '{stack.get('name', '')}'"
                        )

    @staticmethod
    def _check_unresolved_placeholders(
        data: Any, file_path: str, _path: str = ""
    ) -> None:
        """Scan resolved config for remaining {{...}} tokens and raise if found."""
        # Keys to skip — these contain placeholders resolved by a different pipeline:
        # - cdk: contains placeholder definitions
        # - deployments: contains stack configs with deployment-level placeholders
        #   resolved later by deploy.py from deployment.*.json parameters
        SKIP_KEYS = {"cdk", "deployments"}

        pattern = re.compile(r"\{\{([^}]+)\}\}")
        if isinstance(data, dict):
            for key, value in data.items():
                if key in SKIP_KEYS:
                    continue
                current_path = f"{_path}.{key}" if _path else key
                CdkConfig._check_unresolved_placeholders(value, file_path, current_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{_path}[{i}]"
                CdkConfig._check_unresolved_placeholders(item, file_path, current_path)
        elif isinstance(data, str):
            match = pattern.search(data)
            if match:
                placeholder = match.group(0)
                raise ValueError(
                    f"Unresolved placeholder '{placeholder}' found at '{_path}' "
                    f"in config file '{file_path}'. "
                    f"Add this parameter to your deployment JSON or config.json."
                )

    def __get_cdk_parameter_value(self, parameter: Dict[str, Any]) -> str | None:
        cdk_parameter_name = parameter.get("cdk_parameter_name", None)
        placeholder = parameter.get("placeholder", "")
        environment_variable_name = parameter.get("env_var_name", None)
        static_value = parameter.get("value", None)
        required = str(parameter.get("required", True)).lower() == "true"
        value: str | None = None

        if self.cdk_context is None:
            raise ValueError("cdk_context is None")

        value = self.cdk_context.get(cdk_parameter_name)

        print(f"\t📦 Value for {cdk_parameter_name}: {value}")

        # Resolution order:
        # 1. CDK context (-c flag) — already checked above
        # 2. Environment variable (from deployment JSON or shell)
        # 3. Static value in config.json (acts as a default)
        # 4. default_value (last resort)
        if not value and environment_variable_name is not None:
            value = os.environ.get(environment_variable_name, None)

        if not value and static_value is not None:
            value = static_value

        if environment_variable_name is not None and value is not None:
            self._env_vars[environment_variable_name] = value

        if not value:
            # check for a default value
            value = parameter.get("default_value", None)
            if value is not None:
                print(f"\t\t🔀 Using default value for {cdk_parameter_name}: {value}")
            else:
                print(
                    f"\t\t⚠️  No value found for {cdk_parameter_name}, no default provided"
                )

        if value is None and not required:
            return None

        if value is None:
            raise ValueError(
                f"\n"
                f"  ✗ Missing required parameter: {placeholder}\n"
                f"    CDK Param   : {cdk_parameter_name}\n"
                f"    Env Var     : {environment_variable_name or '(none)'}\n"
                f"\n"
                f"  No value, environment variable, or default was found.\n"
                f"  Add this parameter to your deployment JSON or config.json.\n"
            )
        return value

    @property
    def environment_vars(self) -> Dict[str, str]:
        """
        Gets the environment variables
        """
        return self._env_vars

    def save_config_snapshot(self) -> None:
        """Re-save the current in-memory config to .dynamic/config.json.

        Call after all stack build() methods have run to capture
        post-mutation state (merged permissions, env vars, etc.).

        Raises:
            ValueError: If the dynamic config file path has not been
                        established (i.e., __resolved_config was not called).
        """
        if self._dynamic_config_path is None:
            raise ValueError(
                "Cannot save config snapshot: config file path has not been resolved. "
                "Ensure CdkConfig was initialized with a valid config path."
            )

        print(f"📀 Saving post-build config snapshot to {self._dynamic_config_path}")
        JsonLoadingUtility.save(self.config, self._dynamic_config_path)
