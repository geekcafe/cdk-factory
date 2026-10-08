"""
AppSync Events Configuration

Parses the ``appsync_events`` stack block into a small config wrapper with typed
``@property`` accessors, mirroring ``configurations/resources/sns.py`` and
``configurations/resources/event_bridge_rules.py``.

Describes a single AppSync Events API (``CfnApi`` + ``EventConfig``) with a
Cognito-User-Pools provider, an AWS_LAMBDA authorizer provider, and (optionally)
an API_KEY publish provider, plus one ``CfnChannelNamespace`` per configured
namespace. Consumed by the ``appsync_events_stack``.

Channel-namespace names are generic config values — the stack carries no
app-specific channel names (constraint C4). Cross-stack ids (user-pool id,
authorizer ARN) are SSM paths resolved as deploy-time CloudFormation tokens, not
literals.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Any, Dict, List, Optional


class AppSyncEventsChannelNamespaceConfig:
    """A single channel namespace entry.

    Accepts either a plain name string or an object of the form::

        {
            "name": "notifications",
            "publish_auth_modes": [{"auth_type": "API_KEY"}],
            "subscribe_auth_modes": [{"auth_type": "AWS_LAMBDA"}]
        }

    The optional ``publish_auth_modes`` / ``subscribe_auth_modes`` lists override
    the API-level defaults for this namespace. Each entry is an auth-mode dict
    (``{"auth_type": "<AWS_LAMBDA|API_KEY|AMAZON_COGNITO_USER_POOLS|...>"}``).
    """

    def __init__(self, config: Any) -> None:
        if isinstance(config, str):
            self._config: Dict[str, Any] = {"name": config}
        elif isinstance(config, dict):
            self._config = config
        else:
            self._config = {}

    @property
    def name(self) -> str:
        """Channel namespace name (the first channel-path segment family)."""
        return str(self._config.get("name", ""))

    @property
    def publish_auth_modes(self) -> Optional[List[Dict[str, Any]]]:
        """Per-namespace publish auth-mode overrides, or ``None`` to inherit."""
        modes = self._config.get("publish_auth_modes")
        if isinstance(modes, list):
            return modes
        return None

    @property
    def subscribe_auth_modes(self) -> Optional[List[Dict[str, Any]]]:
        """Per-namespace subscribe auth-mode overrides, or ``None`` to inherit."""
        modes = self._config.get("subscribe_auth_modes")
        if isinstance(modes, list):
            return modes
        return None


class AppSyncEventsConfig:
    """AppSync Events stack configuration (parses the ``appsync_events`` block)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}
        self._channel_namespaces: List[AppSyncEventsChannelNamespaceConfig] = []
        self._load_channel_namespaces()

    def _load_channel_namespaces(self) -> None:
        entries = self._config.get("channel_namespaces", [])
        if isinstance(entries, list):
            for entry in entries:
                self._channel_namespaces.append(
                    AppSyncEventsChannelNamespaceConfig(entry)
                )

    @property
    def name(self) -> str:
        """Logical API name; also the deterministic-construct-id seed."""
        return str(self._config.get("name", ""))

    @property
    def user_pool_id_ssm_path(self) -> str:
        """SSM path to the Cognito user-pool id (resolved as a deploy-time token)."""
        return str(self._config.get("user_pool_id_ssm_path", ""))

    @property
    def authorizer_lambda_arn_ssm_path(self) -> str:
        """SSM path to the authorizer Lambda ARN (resolved as a deploy-time token)."""
        return str(self._config.get("authorizer_lambda_arn_ssm_path", ""))

    @property
    def authorizer_result_ttl_seconds(self) -> int:
        """Authorizer result cache TTL in seconds (default 300)."""
        return int(self._config.get("authorizer_result_ttl_seconds", 300))

    @property
    def region(self) -> Optional[str]:
        """Optional explicit region; defaults to the deployment / stack region."""
        region = self._config.get("region")
        return str(region) if region else None

    @property
    def channel_namespaces(self) -> List[AppSyncEventsChannelNamespaceConfig]:
        """Configured channel namespaces (one ``CfnChannelNamespace`` per entry)."""
        return self._channel_namespaces

    @property
    def api_key_publish(self) -> bool:
        """Whether to register the API_KEY publish provider (default True)."""
        value = self._config.get("api_key_publish", True)
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM export passthrough (e.g. ``{"namespace": "<prefix>"}``)."""
        ssm = self._config.get("ssm", {})
        return ssm if isinstance(ssm, dict) else {}
