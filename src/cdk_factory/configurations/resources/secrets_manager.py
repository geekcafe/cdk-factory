"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List


class SecretConfig:
    """
    Configuration for a single Secrets Manager secret.

    Parses an entry like::

        {
            "name": "chatops/ingress/shared-secret",
            "description": "Ingress shared secret",
            "placeholder": "REPLACE_ME",
            "removal_policy": "RETAIN"
        }

    Only ``name`` is required. ``placeholder`` defaults to ``REPLACE_ME`` and
    ``removal_policy`` defaults to ``RETAIN`` (so a credential survives stack
    deletion). Template tokens such as ``{{WORKLOAD_NAME}}`` / ``{{ENVIRONMENT}}``
    in ``name`` / ``description`` are left intact here — the stack resolves them
    at synth time via the deployment context (never a live AWS lookup).
    """

    DEFAULT_PLACEHOLDER = "REPLACE_ME"
    DEFAULT_REMOVAL_POLICY = "RETAIN"

    def __init__(self, config: dict) -> None:
        self.__config: dict = config or {}

    @property
    def name(self) -> str:
        """Secret name (path). Required."""
        value = self.__config.get("name")
        if not value:
            raise ValueError(
                "Secret config is missing required 'name' field"
            )
        return value

    @property
    def description(self) -> str | None:
        """Human-readable description of the secret's purpose."""
        return self.__config.get("description")

    @property
    def placeholder(self) -> str:
        """Initial placeholder value written at create time.

        NEVER change this string in config after the first deploy — see the
        no-clobber contract documented on ``SecretsManagerStack``.
        """
        value = self.__config.get("placeholder")
        if value is None or str(value) == "":
            return self.DEFAULT_PLACEHOLDER
        return str(value)

    @property
    def removal_policy(self) -> str:
        """Removal policy name: ``RETAIN`` (default) or ``DESTROY``."""
        value = self.__config.get("removal_policy")
        if not value:
            return self.DEFAULT_REMOVAL_POLICY
        return str(value).upper()


class SecretsManager:
    """
    Secrets Manager stack configuration.

    Parses a stack config like::

        {
            "name": "...-secrets",
            "module": "secrets_manager_stack",
            "secrets": [
                {"name": "chatops/ingress/shared-secret", "placeholder": "REPLACE_ME"},
                {"name": "chatops/slack/geekcafe/bot-token", "placeholder": "REPLACE_ME"}
            ]
        }
    """

    def __init__(self, config: dict) -> None:
        self.__config: dict = config or {}
        self.__secrets: List[SecretConfig] = []
        self.__load_secrets()

    def __load_secrets(self) -> None:
        if self.__config and isinstance(self.__config, dict):
            entries = self.__config.get("secrets")
            if entries:
                for entry in entries:
                    self.__secrets.append(SecretConfig(entry))

    @property
    def secrets(self) -> List[SecretConfig]:
        """Configured secrets."""
        return self.__secrets
