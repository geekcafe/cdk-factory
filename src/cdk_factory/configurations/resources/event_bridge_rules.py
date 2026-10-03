"""
EventBridge Rules Configuration

Parses a list of EventBridge-rule-to-SQS-target entries. Each entry routes a
matched event (by ``event_pattern``) on a given bus to an SQS queue whose ARN is
resolved at deploy time from SSM (``target_queue_ssm_path``). Consumed by the
``eventbridge_stack``.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Any, Dict, List


class EventBridgeRuleConfig:
    """Individual EventBridge rule -> SQS target configuration."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def name(self) -> str:
        """Rule name. Supports template variables."""
        return self._config.get("name", "")

    @property
    def event_bus_name(self) -> str:
        """Target event bus name. Defaults to ``default``."""
        return self._config.get("event_bus_name", "default")

    @property
    def event_pattern(self) -> Dict[str, Any]:
        """EventBridge event pattern (source / detail-type / detail filters)."""
        pattern = self._config.get("event_pattern", {})
        return pattern if isinstance(pattern, dict) else {}

    @property
    def target_queue_ssm_path(self) -> str:
        """SSM parameter path resolving to the target queue ARN (deploy-time)."""
        return self._config.get("target_queue_ssm_path", "")


class EventBridgeRulesConfig:
    """EventBridge rules stack configuration (parses ``event_bridge_rules``)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @property
    def rules(self) -> List[EventBridgeRuleConfig]:
        """List of EventBridge rule configurations."""
        entries = self._config.get("event_bridge_rules", [])
        if not isinstance(entries, list):
            return []
        return [EventBridgeRuleConfig(entry) for entry in entries]
