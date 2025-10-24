"""
Unit tests for the Monitoring Stack - No Mocking, Real CDK Synthesis
Follows established testing patterns with pytest fixtures and real CDK synthesis.
"""

import pytest
import aws_cdk as cdk
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.stack_library.monitoring.monitoring_stack import MonitoringStack
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestMonitoringStack:
    """Test Monitoring stack with real CDK synthesis"""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing"""
        return App()

    @pytest.fixture
    def workload_config(self):
        """Create a basic workload config"""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                }
            }
        )

    @pytest.fixture
    def deployment_config(self, workload_config):
        """Create a deployment config"""
        return DeploymentConfig(
            workload=workload_config.dictionary,
            deployment={
                "name": "test-deployment",
                "environment": "test",
                "account": "123456789012",
                "region": "us-east-1",
            },
        )

    def test_minimal_monitoring_stack(self, app, deployment_config, workload_config):
        """Test Monitoring stack with minimal configuration"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "test-monitoring",
                    "sns_topics": [],
                    "alarms": [],
                    "dashboards": [],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestMinimalMonitoring",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Minimal stack should not create resources if none configured
        # Just verify it doesn't error
        assert stack.monitoring_config.name == "test-monitoring"

    def test_monitoring_with_sns_topic(self, app, deployment_config, workload_config):
        """Test Monitoring stack with SNS topic"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "sns-monitoring",
                    "sns_topics": [
                        {
                            "name": "critical-alerts",
                            "display_name": "Critical Alerts",
                            "subscriptions": [
                                {
                                    "protocol": "email",
                                    "endpoint": "alerts@example.com",
                                }
                            ],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestSNSTopic",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify SNS Topic exists
        template.has_resource("AWS::SNS::Topic", {})

        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "TopicName": "critical-alerts",
                "DisplayName": "Critical Alerts",
            },
        )

        # Verify SNS Subscription exists
        template.has_resource("AWS::SNS::Subscription", {})

        template.has_resource_properties(
            "AWS::SNS::Subscription",
            {
                "Protocol": "email",
                "Endpoint": "alerts@example.com",
            },
        )

        assert "critical-alerts" in stack.sns_topics

    def test_monitoring_with_metric_alarm(self, app, deployment_config, workload_config):
        """Test Monitoring stack with CloudWatch metric alarm"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "alarm-monitoring",
                    "sns_topics": [
                        {
                            "name": "alarm-topic",
                            "display_name": "Alarm Topic",
                        }
                    ],
                    "alarms": [
                        {
                            "name": "high-cpu-alarm",
                            "type": "metric",
                            "description": "CPU utilization is too high",
                            "metric": {
                                "namespace": "AWS/EC2",
                                "metric_name": "CPUUtilization",
                                "dimensions": {
                                    "InstanceId": "i-1234567890abcdef0",
                                },
                                "statistic": "Average",
                                "period": 300,
                            },
                            "comparison_operator": "GreaterThanThreshold",
                            "threshold": 80,
                            "evaluation_periods": 2,
                            "treat_missing_data": "notBreaching",
                            "actions": ["alarm-topic"],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestMetricAlarm",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify CloudWatch Alarm exists
        template.has_resource("AWS::CloudWatch::Alarm", {})

        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "high-cpu-alarm",
                "AlarmDescription": "CPU utilization is too high",
                "MetricName": "CPUUtilization",
                "Namespace": "AWS/EC2",
                "Statistic": "Average",
                "Period": 300,
                "ComparisonOperator": "GreaterThanThreshold",
                "Threshold": 80,
                "EvaluationPeriods": 2,
                "TreatMissingData": "notBreaching",
            },
        )

        # Verify alarm action is configured
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmActions": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Ref": Match.string_like_regexp(".*Topic.*")
                            }
                        )
                    ]
                ),
            },
        )

        assert "high-cpu-alarm" in stack.alarms

    def test_monitoring_with_multiple_alarms(self, app, deployment_config, workload_config):
        """Test Monitoring stack with multiple alarms"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "multi-alarm-monitoring",
                    "sns_topics": [
                        {
                            "name": "critical-topic",
                        },
                        {
                            "name": "warning-topic",
                        },
                    ],
                    "alarms": [
                        {
                            "name": "critical-alarm",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/ApplicationELB",
                                "metric_name": "HTTPCode_Target_5XX_Count",
                                "statistic": "Sum",
                            },
                            "threshold": 10,
                            "evaluation_periods": 2,
                            "actions": ["critical-topic"],
                        },
                        {
                            "name": "warning-alarm",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/ApplicationELB",
                                "metric_name": "HTTPCode_Target_4XX_Count",
                                "statistic": "Sum",
                            },
                            "threshold": 50,
                            "evaluation_periods": 3,
                            "actions": ["warning-topic"],
                        },
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestMultipleAlarms",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify 2 SNS topics
        template.resource_count_is("AWS::SNS::Topic", 2)

        # Verify 2 alarms
        template.resource_count_is("AWS::CloudWatch::Alarm", 2)

        assert len(stack.alarms) == 2
        assert "critical-alarm" in stack.alarms
        assert "warning-alarm" in stack.alarms

    def test_monitoring_with_dashboard(self, app, deployment_config, workload_config):
        """Test Monitoring stack with CloudWatch dashboard"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "dashboard-monitoring",
                    "dashboards": [
                        {
                            "name": "test-dashboard",
                            "widgets": [
                                {
                                    "type": "graph",
                                    "title": "CPU Utilization",
                                    "width": 12,
                                    "height": 6,
                                    "metrics": [
                                        {
                                            "namespace": "AWS/EC2",
                                            "metric_name": "CPUUtilization",
                                            "statistic": "Average",
                                            "period": 300,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestDashboard",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify CloudWatch Dashboard exists
        template.has_resource("AWS::CloudWatch::Dashboard", {})

        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "test-dashboard",
            },
        )

        assert "test-dashboard" in stack.dashboards

    def test_monitoring_with_composite_alarm(self, app, deployment_config, workload_config):
        """Test Monitoring stack with composite alarm"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "composite-monitoring",
                    "sns_topics": [
                        {
                            "name": "composite-topic",
                        }
                    ],
                    "alarms": [
                        {
                            "name": "alarm-1",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/EC2",
                                "metric_name": "CPUUtilization",
                                "statistic": "Average",
                            },
                            "threshold": 80,
                            "evaluation_periods": 1,
                        },
                        {
                            "name": "alarm-2",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/EC2",
                                "metric_name": "NetworkIn",
                                "statistic": "Average",
                            },
                            "threshold": 1000000,
                            "evaluation_periods": 1,
                        },
                    ],
                    "composite_alarms": [
                        {
                            "name": "composite-alarm",
                            "description": "Both alarms are in ALARM state",
                            "alarm_rule": "ALARM(alarm-1) AND ALARM(alarm-2)",
                            "actions": ["composite-topic"],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestCompositeAlarm",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify composite alarm exists
        template.has_resource("AWS::CloudWatch::CompositeAlarm", {})

        template.has_resource_properties(
            "AWS::CloudWatch::CompositeAlarm",
            {
                "AlarmName": "composite-alarm",
                "AlarmRule": "ALARM(alarm-1) AND ALARM(alarm-2)",
            },
        )

    def test_monitoring_with_log_metric_filter(self, app, deployment_config, workload_config):
        """Test Monitoring stack with log metric filter"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "log-filter-monitoring",
                    "log_metric_filters": [
                        {
                            "name": "error-filter",
                            "log_group_name": "/aws/lambda/test-function",
                            "filter_pattern": "[ERROR]",
                            "metric_namespace": "CustomMetrics",
                            "metric_name": "ErrorCount",
                            "metric_value": "1",
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestLogMetricFilter",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify metric filter exists
        template.has_resource("AWS::Logs::MetricFilter", {})

        template.has_resource_properties(
            "AWS::Logs::MetricFilter",
            {
                "FilterPattern": "[ERROR]",
                "MetricTransformations": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "MetricNamespace": "CustomMetrics",
                                "MetricName": "ErrorCount",
                                "MetricValue": "1",
                            }
                        )
                    ]
                ),
            },
        )

    def test_monitoring_with_ssm_exports(self, app, deployment_config, workload_config):
        """Test Monitoring stack with SSM parameter exports"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "ssm-export-monitoring",
                    "sns_topics": [
                        {
                            "name": "export-topic",
                        }
                    ],
                    "ssm_exports": {
                        "sns_topic_export-topic": "/test/monitoring/topic-arn",
                    },
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestSSMExports",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify SSM parameter exists
        template.has_resource("AWS::SSM::Parameter", {})

        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/test/monitoring/topic-arn",
                "Type": "String",
            },
        )

    def test_monitoring_alarm_with_datapoints_to_alarm(self, app, deployment_config, workload_config):
        """Test Monitoring alarm with datapoints_to_alarm configuration"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "datapoints-monitoring",
                    "alarms": [
                        {
                            "name": "datapoints-alarm",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/ECS",
                                "metric_name": "CPUUtilization",
                                "statistic": "Average",
                            },
                            "threshold": 75,
                            "evaluation_periods": 3,
                            "datapoints_to_alarm": 2,
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestDatapointsAlarm",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify alarm with datapoints_to_alarm
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "EvaluationPeriods": 3,
                "DatapointsToAlarm": 2,
            },
        )

    def test_monitoring_alarm_with_ok_actions(self, app, deployment_config, workload_config):
        """Test Monitoring alarm with OK actions"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "ok-actions-monitoring",
                    "sns_topics": [
                        {
                            "name": "ok-topic",
                        }
                    ],
                    "alarms": [
                        {
                            "name": "ok-actions-alarm",
                            "type": "metric",
                            "metric": {
                                "namespace": "AWS/RDS",
                                "metric_name": "CPUUtilization",
                                "statistic": "Average",
                            },
                            "threshold": 70,
                            "evaluation_periods": 2,
                            "actions": ["ok-topic"],
                            "ok_actions": ["ok-topic"],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestOKActions",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify alarm has both AlarmActions and OKActions
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmActions": Match.any_value(),
                "OKActions": Match.any_value(),
            },
        )

    def test_monitoring_with_multiple_sns_subscriptions(self, app, deployment_config, workload_config):
        """Test Monitoring with multiple SNS subscriptions"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "multi-subscription-monitoring",
                    "sns_topics": [
                        {
                            "name": "multi-sub-topic",
                            "subscriptions": [
                                {
                                    "protocol": "email",
                                    "endpoint": "team@example.com",
                                },
                                {
                                    "protocol": "email",
                                    "endpoint": "manager@example.com",
                                },
                            ],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestMultiSubscription",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify 2 subscriptions exist
        template.resource_count_is("AWS::SNS::Subscription", 2)

    def test_monitoring_dashboard_with_multiple_widgets(self, app, deployment_config, workload_config):
        """Test Monitoring dashboard with multiple widget types"""
        stack_config = StackConfig(
            {
                "monitoring": {
                    "name": "multi-widget-monitoring",
                    "dashboards": [
                        {
                            "name": "multi-widget-dashboard",
                            "widgets": [
                                {
                                    "type": "graph",
                                    "title": "Graph Widget",
                                    "metrics": [
                                        {
                                            "namespace": "AWS/Lambda",
                                            "metric_name": "Invocations",
                                            "statistic": "Sum",
                                        }
                                    ],
                                },
                                {
                                    "type": "number",
                                    "title": "Number Widget",
                                    "metrics": [
                                        {
                                            "namespace": "AWS/Lambda",
                                            "metric_name": "Errors",
                                            "statistic": "Sum",
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            },
            workload=workload_config.dictionary,
        )

        stack = MonitoringStack(
            app,
            "TestMultiWidget",
            stack_config=stack_config,
            deployment=deployment_config,
            env=cdk.Environment(account="123456789012", region="us-east-1"),
        )
        stack.build()
        template = Template.from_stack(stack)

        # Verify dashboard exists with widgets
        template.has_resource("AWS::CloudWatch::Dashboard", {})

        # Verify dashboard has the correct name
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "multi-widget-dashboard",
                "DashboardBody": Match.any_value(),  # Body is a complex Fn::Join structure
            },
        )
