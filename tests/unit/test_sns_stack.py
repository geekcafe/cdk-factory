"""
Unit tests for SNS Stack using real configuration objects.
Tests sns_stack.py functionality without mocks, via real CDK synthesis.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.sns.sns_stack import SNSStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestSNSStackReal:
    """Test cases for SNS Stack functionality using real config objects."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for SNS stack testing",
            "devops": {"ci_cd": {"enabled": True}},
        }
        deployment_dict = {
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        config_dict = {
            "name": "test-workload",
            "description": "Test workload for SNS stack testing",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return WorkloadConfig(config=config_dict)

    @pytest.fixture
    def stack_config_with_topic(self):
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for SNS stack testing",
        }
        stack_dict = {
            "name": "test-sns-stack",
            "enabled": True,
            "sns": {
                "topics": [
                    {
                        "name": "contact-notifications",
                        "display_name": "Contact Notifications",
                        "subscriptions": [
                            {"protocol": "email", "endpoint": "leads@example.com"}
                        ],
                    }
                ]
            },
        }
        return StackConfig(stack=stack_dict, workload=workload_dict)

    def test_sns_stack_initialization(self, app):
        """Stack initializes with empty state."""
        stack = SNSStack(
            scope=app,
            id="test-sns-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        assert stack is not None
        assert stack.topics == {}
        assert stack.stack_config is None
        assert stack.deployment is None
        assert stack.workload is None

    def test_sns_stack_build_creates_topic_and_subscription(
        self,
        app,
        deployment_config,
        workload_config,
        stack_config_with_topic,
    ):
        """Building the stack creates a topic, an email subscription, and an SSM param."""
        stack = SNSStack(
            scope=app,
            id="test-sns-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config_with_topic,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)

        # Topic name comes from the config value (naming/prefixing is the
        # responsibility of the config, mirroring the lambda/sqs modules).
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "TopicName": "contact-notifications",
                "DisplayName": "Contact Notifications",
            },
        )

        # Email subscription wired to the topic
        template.has_resource_properties(
            "AWS::SNS::Subscription",
            {
                "Protocol": "email",
                "Endpoint": "leads@example.com",
            },
        )

        # Topic ARN exported to SSM
        template.resource_count_is("AWS::SSM::Parameter", 1)

        assert len(stack.topics) == 1

    def test_sns_stack_resolves_name_placeholders(
        self, app, deployment_config, workload_config
    ):
        """`{{workload-name}}`/`{{deployment-name}}` placeholders resolve in the topic name."""
        stack_dict = {
            "name": "test-sns-stack",
            "enabled": True,
            "sns": {
                "topics": [
                    {"name": "{{workload-name}}-{{deployment-name}}-contact"}
                ]
            },
        }
        stack_config = StackConfig(
            stack=stack_dict, workload={"name": "test-workload"}
        )

        stack = SNSStack(
            scope=app,
            id="test-sns-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {"TopicName": "test-workload-test-deployment-contact"},
        )

    def test_sns_stack_no_topics_is_noop(
        self, app, deployment_config, workload_config
    ):
        """A config with no topics builds without creating SNS resources."""
        stack_dict = {"name": "test-sns-stack", "enabled": True, "sns": {"topics": []}}
        stack_config = StackConfig(
            stack=stack_dict, workload={"name": "test-workload"}
        )

        stack = SNSStack(
            scope=app,
            id="test-sns-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        template = Template.from_stack(stack)
        template.resource_count_is("AWS::SNS::Topic", 0)
        assert stack.topics == {}

    def test_sns_stack_unsupported_protocol_raises(
        self, app, deployment_config, workload_config
    ):
        """An unsupported subscription protocol raises a clear error."""
        stack_dict = {
            "name": "test-sns-stack",
            "enabled": True,
            "sns": {
                "topics": [
                    {
                        "name": "contact-notifications",
                        "subscriptions": [
                            {"protocol": "carrier-pigeon", "endpoint": "x"}
                        ],
                    }
                ]
            },
        }
        stack_config = StackConfig(
            stack=stack_dict, workload={"name": "test-workload"}
        )

        stack = SNSStack(
            scope=app,
            id="test-sns-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        with pytest.raises(ValueError, match="Unsupported SNS subscription protocol"):
            stack.build(
                stack_config=stack_config,
                deployment=deployment_config,
                workload=workload_config,
            )
