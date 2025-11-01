"""
Monitoring Configuration
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, List, Any, Optional
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class MonitoringConfig(EnhancedBaseConfig):
    """
    Monitoring Configuration for CloudWatch Alarms and Dashboards
    """

    def __init__(self, config: dict = None, deployment=None) -> None:
        super().__init__(
            config or {},
            resource_type="monitoring",
            resource_name=config.get("name", "monitoring") if config else "monitoring",
        )
        self._config = config or {}
        self._deployment = deployment

    @property
    def name(self) -> str:
        """Monitoring stack name"""
        return self._config.get("name", "monitoring")

    @property
    def sns_topics(self) -> List[Dict[str, Any]]:
        """SNS topics for alarm notifications"""
        return self._config.get("sns_topics", [])

    @property
    def alarms(self) -> List[Dict[str, Any]]:
        """CloudWatch alarms configuration"""
        return self._config.get("alarms", [])

    @property
    def dashboards(self) -> List[Dict[str, Any]]:
        """CloudWatch dashboards configuration"""
        return self._config.get("dashboards", [])

    @property
    def composite_alarms(self) -> List[Dict[str, Any]]:
        """Composite alarms (combine multiple alarms)"""
        return self._config.get("composite_alarms", [])

    @property
    def log_metric_filters(self) -> List[Dict[str, Any]]:
        """CloudWatch Logs metric filters"""
        return self._config.get("log_metric_filters", [])

    @property
    def enable_anomaly_detection(self) -> bool:
        """Enable CloudWatch anomaly detection"""
        return self._config.get("enable_anomaly_detection", False)

    @property
    def tags(self) -> Dict[str, str]:
        """Resource tags"""
        return self._config.get("tags", {})

    @property
    def ssm(self) -> Dict[str, Any]:
        """SSM configuration"""
        return self._config.get("ssm", {})

    @property
    def ssm_exports(self) -> Dict[str, str]:
        """SSM parameter exports"""
        return self.ssm.get("exports", {})

    @property
    def ssm_imports(self) -> Dict[str, str]:
        """SSM parameter imports for resource ARNs"""
        return self.ssm.get("imports", {})
