"""
Parameter Store Configuration
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, List, Optional


class ParameterConfig:
    """Individual SSM Parameter Configuration"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config

    @property
    def name(self) -> str:
        """Parameter name/path"""
        return self._config.get("name", "")

    @property
    def value(self) -> str:
        """Parameter value"""
        return self._config.get("value", "")

    @property
    def type(self) -> str:
        """Parameter type: String, StringList, or SecureString"""
        return self._config.get("type", "String")

    @property
    def description(self) -> Optional[str]:
        """Parameter description"""
        return self._config.get("description")

    @property
    def tier(self) -> str:
        """Parameter tier: Standard or Advanced"""
        return self._config.get("tier", "Standard")

    @property
    def allowed_pattern(self) -> Optional[str]:
        """Regular expression to validate parameter value"""
        return self._config.get("allowed_pattern")

    @property
    def data_type(self) -> str:
        """Data type: text, aws:ec2:image, aws:ssm:integration"""
        return self._config.get("data_type", "text")

    @property
    def tags(self) -> Dict[str, str]:
        """Tags for the parameter"""
        return self._config.get("tags", {})


class ParameterStoreConfig:
    """Parameter Store Stack Configuration"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config

    @property
    def parameters(self) -> List[ParameterConfig]:
        """List of parameters to create"""
        params = self._config.get("parameters", [])
        return [ParameterConfig(p) for p in params]

    @property
    def prefix(self) -> Optional[str]:
        """
        Optional prefix to prepend to all parameter names.
        Typically /{environment}/{workload}/ format.
        """
        return self._config.get("prefix")

    @property
    def auto_format_names(self) -> bool:
        """
        If true, automatically format parameter names with prefix.
        If false, use parameter names exactly as specified.
        """
        return self._config.get("auto_format_names", True)

    @property
    def global_tags(self) -> Dict[str, str]:
        """Tags to apply to all parameters"""
        return self._config.get("global_tags", {})
