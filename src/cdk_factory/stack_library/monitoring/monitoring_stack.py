"""
Monitoring Stack - CloudWatch Alarms and Dashboards
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import logging
from typing import Dict, List, Any, Optional

from aws_cdk import (
    Duration,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_ssm as ssm,
    aws_logs as logs,
    CfnOutput,
)
from constructs import Construct

from cdk_factory.interfaces.istack import IStack
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.monitoring import MonitoringConfig

logger = logging.getLogger(__name__)


@register_stack("monitoring_library_module")
class MonitoringStack(IStack):
    """
    Monitoring Stack with CloudWatch Alarms and Dashboards
    
    Supports:
    - SNS topics for notifications
    - CloudWatch alarms (metric, composite, anomaly detection)
    - CloudWatch dashboards
    - Log metric filters
    - Email/Slack/PagerDuty subscriptions
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        stack_config: StackConfig,
        deployment,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.stack_config = stack_config
        self.deployment = deployment
        
        # Monitoring config
        monitoring_dict = stack_config.dictionary.get("monitoring", {})
        self.monitoring_config = MonitoringConfig(monitoring_dict, deployment)
        
        # Resources
        self.sns_topics: Dict[str, sns.Topic] = {}
        self.alarms: Dict[str, cloudwatch.Alarm] = {}
        self.dashboards: Dict[str, cloudwatch.Dashboard] = {}

    def build(
        self,
        vpc=None,
        target_groups=None,
        security_groups=None,
        shared=None,
    ):
        """Build monitoring resources"""
        
        logger.info(f"Building monitoring stack: {self.monitoring_config.name}")
        
        # Create SNS topics first
        self._create_sns_topics()
        
        # Create log metric filters
        self._create_log_metric_filters()
        
        # Create alarms
        self._create_alarms()
        
        # Create composite alarms
        self._create_composite_alarms()
        
        # Create dashboards
        self._create_dashboards()
        
        # Export SSM parameters
        self._export_ssm_parameters()
        
        # Create outputs
        self._create_outputs()
        
        return self

    def _create_sns_topics(self) -> None:
        """Create SNS topics for alarm notifications"""
        topics_config = self.monitoring_config.sns_topics
        
        for topic_config in topics_config:
            topic_name = topic_config.get("name")
            if not topic_name:
                logger.warning("SNS topic name is required, skipping")
                continue
            
            # Create topic
            topic = sns.Topic(
                self,
                f"Topic-{topic_name}",
                topic_name=topic_name,
                display_name=topic_config.get("display_name", topic_name),
            )
            
            # Add subscriptions
            subscriptions_config = topic_config.get("subscriptions", [])
            for sub_config in subscriptions_config:
                protocol = sub_config.get("protocol", "email")
                endpoint = sub_config.get("endpoint")
                
                if not endpoint:
                    logger.warning(f"Subscription endpoint required for {topic_name}, skipping")
                    continue
                
                if protocol == "email":
                    topic.add_subscription(subscriptions.EmailSubscription(endpoint))
                elif protocol == "sms":
                    topic.add_subscription(subscriptions.SmsSubscription(endpoint))
                elif protocol == "https":
                    topic.add_subscription(subscriptions.UrlSubscription(endpoint))
                elif protocol == "lambda":
                    # Lambda ARN as endpoint
                    logger.warning(f"Lambda subscriptions not yet implemented for {topic_name}")
                else:
                    logger.warning(f"Unsupported protocol {protocol} for {topic_name}")
            
            self.sns_topics[topic_name] = topic
            logger.info(f"Created SNS topic: {topic_name}")

    def _create_log_metric_filters(self) -> None:
        """Create CloudWatch Logs metric filters"""
        filters_config = self.monitoring_config.log_metric_filters
        
        for filter_config in filters_config:
            filter_name = filter_config.get("name")
            log_group_name = filter_config.get("log_group_name")
            filter_pattern = filter_config.get("filter_pattern")
            metric_namespace = filter_config.get("metric_namespace", "CustomMetrics")
            metric_name = filter_config.get("metric_name")
            
            if not all([filter_name, log_group_name, filter_pattern, metric_name]):
                logger.warning(f"Missing required fields for metric filter {filter_name}, skipping")
                continue
            
            # Import log group
            log_group = logs.LogGroup.from_log_group_name(
                self,
                f"LogGroup-{filter_name}",
                log_group_name=log_group_name
            )
            
            # Create metric filter
            logs.MetricFilter(
                self,
                f"MetricFilter-{filter_name}",
                log_group=log_group,
                filter_pattern=logs.FilterPattern.literal(filter_pattern),
                metric_namespace=metric_namespace,
                metric_name=metric_name,
                metric_value=filter_config.get("metric_value", "1"),
                default_value=filter_config.get("default_value", 0),
            )
            
            logger.info(f"Created metric filter: {filter_name}")

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms"""
        alarms_config = self.monitoring_config.alarms
        
        for alarm_config in alarms_config:
            alarm_name = alarm_config.get("name")
            if not alarm_name:
                logger.warning("Alarm name is required, skipping")
                continue
            
            # Determine alarm type
            alarm_type = alarm_config.get("type", "metric")
            
            if alarm_type == "metric":
                alarm = self._create_metric_alarm(alarm_config)
            elif alarm_type == "anomaly":
                alarm = self._create_anomaly_alarm(alarm_config)
            else:
                logger.warning(f"Unsupported alarm type: {alarm_type}")
                continue
            
            if alarm:
                self.alarms[alarm_name] = alarm
                logger.info(f"Created alarm: {alarm_name}")

    def _create_metric_alarm(self, config: Dict[str, Any]) -> Optional[cloudwatch.Alarm]:
        """Create a metric-based alarm"""
        alarm_name = config.get("name")
        
        # Get metric configuration
        metric_config = config.get("metric", {})
        
        # Check if using SSM import for resource
        namespace = metric_config.get("namespace")
        metric_name = metric_config.get("metric_name")
        dimensions = metric_config.get("dimensions", {})
        
        # Resolve SSM parameters in dimensions
        resolved_dimensions = {}
        for dim_name, dim_value in dimensions.items():
            if isinstance(dim_value, str) and dim_value.startswith("{{ssm:") and dim_value.endswith("}}"):
                ssm_param = dim_value[6:-2]
                dim_value = ssm.StringParameter.value_from_lookup(self, ssm_param)
            resolved_dimensions[dim_name] = dim_value
        
        # Create metric
        metric = cloudwatch.Metric(
            namespace=namespace,
            metric_name=metric_name,
            dimensions_map=resolved_dimensions if resolved_dimensions else None,
            statistic=metric_config.get("statistic", "Average"),
            period=Duration.seconds(metric_config.get("period", 300)),
        )
        
        # Comparison operator
        comparison_op_map = {
            "GreaterThanThreshold": cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            "GreaterThanOrEqualToThreshold": cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            "LessThanThreshold": cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            "LessThanOrEqualToThreshold": cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
        }
        comparison_op = comparison_op_map.get(
            config.get("comparison_operator", "GreaterThanThreshold"),
            cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        # Treat missing data
        treat_missing_data_map = {
            "breaching": cloudwatch.TreatMissingData.BREACHING,
            "notBreaching": cloudwatch.TreatMissingData.NOT_BREACHING,
            "ignore": cloudwatch.TreatMissingData.IGNORE,
            "missing": cloudwatch.TreatMissingData.MISSING,
        }
        treat_missing_data = treat_missing_data_map.get(
            config.get("treat_missing_data", "notBreaching"),
            cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Create alarm
        alarm = cloudwatch.Alarm(
            self,
            f"Alarm-{alarm_name}",
            alarm_name=alarm_name,
            alarm_description=config.get("description", ""),
            metric=metric,
            threshold=config.get("threshold", 0),
            evaluation_periods=config.get("evaluation_periods", 1),
            datapoints_to_alarm=config.get("datapoints_to_alarm"),
            comparison_operator=comparison_op,
            treat_missing_data=treat_missing_data,
            actions_enabled=config.get("actions_enabled", True),
        )
        
        # Add alarm actions (SNS topics)
        actions = config.get("actions", [])
        for action in actions:
            if action in self.sns_topics:
                alarm.add_alarm_action(cw_actions.SnsAction(self.sns_topics[action]))
        
        # Add OK actions
        ok_actions = config.get("ok_actions", [])
        for action in ok_actions:
            if action in self.sns_topics:
                alarm.add_ok_action(cw_actions.SnsAction(self.sns_topics[action]))
        
        # Add insufficient data actions
        insufficient_data_actions = config.get("insufficient_data_actions", [])
        for action in insufficient_data_actions:
            if action in self.sns_topics:
                alarm.add_insufficient_data_action(cw_actions.SnsAction(self.sns_topics[action]))
        
        return alarm

    def _create_anomaly_alarm(self, config: Dict[str, Any]) -> Optional[cloudwatch.Alarm]:
        """Create an anomaly detection alarm"""
        # Anomaly detection alarms use a different approach
        # For now, log and skip - can be implemented later
        logger.info(f"Anomaly detection alarm {config.get('name')} - implementation pending")
        return None

    def _create_composite_alarms(self) -> None:
        """Create composite alarms (combine multiple alarms)"""
        composite_config = self.monitoring_config.composite_alarms
        
        for comp_config in composite_config:
            comp_name = comp_config.get("name")
            if not comp_name:
                logger.warning("Composite alarm name is required, skipping")
                continue
            
            # Build alarm rule
            alarm_rule = comp_config.get("alarm_rule")
            if not alarm_rule:
                logger.warning(f"Alarm rule required for {comp_name}, skipping")
                continue
            
            # Replace alarm names with ARNs in the rule
            # This is a simplified version - full implementation would parse the rule
            # For now, just pass through
            
            composite_alarm = cloudwatch.CompositeAlarm(
                self,
                f"CompositeAlarm-{comp_name}",
                composite_alarm_name=comp_name,
                alarm_description=comp_config.get("description", ""),
                alarm_rule=cloudwatch.AlarmRule.from_string(alarm_rule),
                actions_enabled=comp_config.get("actions_enabled", True),
            )
            
            # Add actions
            actions = comp_config.get("actions", [])
            for action in actions:
                if action in self.sns_topics:
                    composite_alarm.add_alarm_action(cw_actions.SnsAction(self.sns_topics[action]))
            
            logger.info(f"Created composite alarm: {comp_name}")

    def _create_dashboards(self) -> None:
        """Create CloudWatch dashboards"""
        dashboards_config = self.monitoring_config.dashboards
        
        for dashboard_config in dashboards_config:
            dashboard_name = dashboard_config.get("name")
            if not dashboard_name:
                logger.warning("Dashboard name is required, skipping")
                continue
            
            # Create dashboard
            dashboard = cloudwatch.Dashboard(
                self,
                f"Dashboard-{dashboard_name}",
                dashboard_name=dashboard_name,
            )
            
            # Add widgets
            widgets_config = dashboard_config.get("widgets", [])
            for widget_config in widgets_config:
                widget = self._create_widget(widget_config)
                if widget:
                    # Add to dashboard (position will be auto-calculated)
                    dashboard.add_widgets(widget)
            
            self.dashboards[dashboard_name] = dashboard
            logger.info(f"Created dashboard: {dashboard_name}")

    def _create_widget(self, config: Dict[str, Any]) -> Optional[cloudwatch.IWidget]:
        """Create a dashboard widget"""
        widget_type = config.get("type", "graph")
        
        if widget_type == "graph":
            return self._create_graph_widget(config)
        elif widget_type == "number":
            return self._create_single_value_widget(config)
        elif widget_type == "log":
            return self._create_log_widget(config)
        elif widget_type == "alarm":
            return self._create_alarm_widget(config)
        else:
            logger.warning(f"Unsupported widget type: {widget_type}")
            return None

    def _create_graph_widget(self, config: Dict[str, Any]) -> cloudwatch.GraphWidget:
        """Create a graph widget"""
        metrics_config = config.get("metrics", [])
        metrics = []
        
        for metric_config in metrics_config:
            metric = cloudwatch.Metric(
                namespace=metric_config.get("namespace"),
                metric_name=metric_config.get("metric_name"),
                dimensions_map=metric_config.get("dimensions", {}),
                statistic=metric_config.get("statistic", "Average"),
                period=Duration.seconds(metric_config.get("period", 300)),
                label=metric_config.get("label"),
            )
            metrics.append(metric)
        
        return cloudwatch.GraphWidget(
            title=config.get("title", ""),
            left=metrics,
            width=config.get("width", 12),
            height=config.get("height", 6),
            legend_position=cloudwatch.LegendPosition.BOTTOM,
        )

    def _create_single_value_widget(self, config: Dict[str, Any]) -> cloudwatch.SingleValueWidget:
        """Create a single value widget"""
        metrics_config = config.get("metrics", [])
        metrics = []
        
        for metric_config in metrics_config:
            metric = cloudwatch.Metric(
                namespace=metric_config.get("namespace"),
                metric_name=metric_config.get("metric_name"),
                dimensions_map=metric_config.get("dimensions", {}),
                statistic=metric_config.get("statistic", "Average"),
                period=Duration.seconds(metric_config.get("period", 300)),
            )
            metrics.append(metric)
        
        return cloudwatch.SingleValueWidget(
            title=config.get("title", ""),
            metrics=metrics,
            width=config.get("width", 6),
            height=config.get("height", 3),
        )

    def _create_log_widget(self, config: Dict[str, Any]) -> cloudwatch.LogQueryWidget:
        """Create a log query widget"""
        log_group_names = config.get("log_group_names", [])
        query_string = config.get("query_string", "")
        
        return cloudwatch.LogQueryWidget(
            title=config.get("title", ""),
            log_group_names=log_group_names,
            query_string=query_string,
            width=config.get("width", 24),
            height=config.get("height", 6),
        )

    def _create_alarm_widget(self, config: Dict[str, Any]) -> cloudwatch.AlarmWidget:
        """Create an alarm status widget"""
        alarm_names = config.get("alarm_names", [])
        alarms = [self.alarms[name] for name in alarm_names if name in self.alarms]
        
        if not alarms:
            logger.warning(f"No alarms found for alarm widget")
            return None
        
        return cloudwatch.AlarmWidget(
            title=config.get("title", "Alarms"),
            alarms=alarms,
            width=config.get("width", 12),
            height=config.get("height", 6),
        )

    def _export_ssm_parameters(self) -> None:
        """Export monitoring resources to SSM Parameter Store"""
        ssm_exports = self.monitoring_config.ssm_exports
        
        if not ssm_exports:
            return
        
        # Export SNS topic ARNs
        for topic_name, topic in self.sns_topics.items():
            param_name = ssm_exports.get(f"sns_topic_{topic_name}")
            if param_name:
                ssm.StringParameter(
                    self,
                    f"SnsTopicParam-{topic_name}",
                    parameter_name=param_name,
                    string_value=topic.topic_arn,
                    description=f"SNS Topic ARN for {topic_name}",
                )

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        # Output SNS topic ARNs
        for topic_name, topic in self.sns_topics.items():
            CfnOutput(
                self,
                f"SnsTopicArn-{topic_name}",
                value=topic.topic_arn,
                description=f"SNS Topic ARN: {topic_name}",
            )
        
        # Output dashboard URLs
        for dashboard_name, dashboard in self.dashboards.items():
            CfnOutput(
                self,
                f"DashboardUrl-{dashboard_name}",
                value=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={dashboard_name}",
                description=f"Dashboard URL: {dashboard_name}",
            )
