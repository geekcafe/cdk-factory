"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class StackConfig:
    """A Cloud Formation Stack built by the CDK"""

    def __init__(self, stack: dict, workload: dict) -> None:
        self.__stack: dict = stack
        self.__workload: dict = workload

    @property
    def workload(self) -> dict:
        """
        Returns the workload
        """
        return self.__workload

    @property
    def dictionary(self) -> dict:
        """
        Returns the dictionary of the stack
        """
        return self.__stack

    @property
    def name(self) -> str:
        """
        The actual stack name. Used for CDK construct ID and CloudFormation stack name.
        This is NOT a visual label — use `description` for that.
        """
        value = self.dictionary.get("name")
        if not value:
            raise ValueError("Stack name is not defined in the configuration")
        return value

    @property
    def description(self) -> str | None:
        """
        Human-readable label describing what the stack is for.
        """
        return self.dictionary.get("description")

    @property
    def module(self) -> str:
        """
        Returns the module name
        """
        value = self.dictionary.get("module")
        if not value:
            raise ValueError(
                "Stack module is required but it is not defined in the configuration"
            )
        return value

    @property
    def kwargs(self) -> dict:
        """
        Returns the kwargs
        """
        return self.__stack.get("kwargs", {})

    @property
    def enabled(self) -> bool:
        """
        Returns if the stack is enabled
        """
        value = self.dictionary.get("enabled")
        return str(value).lower() == "true" or value is True

    @property
    def dependencies(self) -> List[str]:
        """
        Canonical dependency list. Reads from 'depends_on' only.
        """
        value = self.dictionary.get("depends_on")
        if value is None:
            return []
        if isinstance(value, list):
            return value
        raise ValueError("depends_on must be a list of strings")

    @property
    def ssm_config(self) -> dict:
        """
        Top-level SSM configuration block.
        """
        return self.dictionary.get("ssm", {})

    def resolved_ssm_config(self, nested_key: str) -> dict:
        """
        Resolve the SSM configuration block for a stack that may carry its
        ``ssm`` block EITHER at the stack top level OR nested inside a module
        block (e.g. ``api_gateway.ssm``).

        Historically some stacks (notably ``api_gateway_stack``) nest the whole
        ``ssm`` block inside their module config (``{"api_gateway": {"ssm": {...}}}``)
        while the engine's generic reads looked at the stack top level
        (``{"ssm": {...}}``). That split meant one code path (the authorizer
        lookup, which read nested) worked while another (lambda-route
        auto-discovery, which read top level) saw an empty block and failed.

        This accessor is the single source of truth for that resolution: it
        MERGES the top-level and nested blocks per-key (nested wins), so a config
        written either way — or one that splits keys across both blocks — resolves
        to the same correct result and every read site agrees. See
        :func:`cdk_factory.utilities.ssm_path_utils.resolve_nested_ssm_config` for
        the exact merge rule (including the per-key merge of the ``imports``
        sub-dict).

        Args:
            nested_key: The module key to look under for a nested ``ssm`` block
                (e.g. ``"api_gateway"``).

        Returns:
            The resolved ``ssm`` configuration dict (may be empty).
        """
        # Delegate to the shared helper so every config type resolves the ssm
        # block by the SAME rule (see utilities.ssm_path_utils).
        from cdk_factory.utilities.ssm_path_utils import resolve_nested_ssm_config

        return resolve_nested_ssm_config(self.dictionary, nested_key)

    @property
    def ssm_namespace(self) -> str | None:
        """
        SSM namespace from top-level ssm block.
        """
        return self.ssm_config.get("namespace")

    @property
    def ssm_auto_export(self) -> bool:
        """
        Whether auto-export is enabled.
        """
        return str(self.ssm_config.get("auto_export", False)).lower() == "true"

    @property
    def additional_permissions(self) -> list:
        """
        Stack-level permissions to merge into every resource.
        """
        return self.dictionary.get("additional_permissions", [])

    @property
    def additional_environment_variables(self) -> list:
        """
        Stack-level environment variables to merge into every resource.
        """
        return self.dictionary.get("additional_environment_variables", [])

    def build_id(self) -> str:
        """
        Returns the stack name
        """
        return f"{self.name}"
