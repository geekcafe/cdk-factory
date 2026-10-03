"""
Unit tests for the event_bridge_rules config model and its JSON schema.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from cdk_factory.configurations.resources.event_bridge_rules import (
    EventBridgeRulesConfig,
)
from cdk_factory.configurations.schema_registry import SchemaRegistry


SAMPLE_ENTRY = {
    "event_bridge_rules": [
        {
            "name": "myapp-dev-chatops-slack-rule",
            "event_bus_name": "default",
            "event_pattern": {
                "source": ["geekcafe.chatops"],
                "detail-type": ["ChatOpsMessage"],
                "detail": {"platform": ["slack"]},
            },
            "target_queue_ssm_path": "/chatops/dev/sqs/myapp-dev-chatops-slack/arn",
        }
    ]
}


def test_parses_four_fields():
    config = EventBridgeRulesConfig(SAMPLE_ENTRY)
    rules = config.rules
    assert len(rules) == 1
    rule = rules[0]
    assert rule.name == "myapp-dev-chatops-slack-rule"
    assert rule.event_bus_name == "default"
    assert rule.event_pattern == {
        "source": ["geekcafe.chatops"],
        "detail-type": ["ChatOpsMessage"],
        "detail": {"platform": ["slack"]},
    }
    assert (
        rule.target_queue_ssm_path
        == "/chatops/dev/sqs/myapp-dev-chatops-slack/arn"
    )


def test_event_bus_name_defaults_to_default():
    config = EventBridgeRulesConfig(
        {
            "event_bridge_rules": [
                {
                    "name": "r",
                    "event_pattern": {"source": ["x"]},
                    "target_queue_ssm_path": "/p",
                }
            ]
        }
    )
    assert config.rules[0].event_bus_name == "default"


def test_empty_config_yields_no_rules():
    assert EventBridgeRulesConfig({}).rules == []
    assert EventBridgeRulesConfig({"event_bridge_rules": None}).rules == []


def _schema() -> dict:
    schema = SchemaRegistry.get_schema("event_bridge_rules")
    assert schema is not None, "event_bridge_rules schema should be registered"
    return schema


def test_schema_accepts_valid_entry():
    jsonschema.validate(instance=SAMPLE_ENTRY, schema=_schema())


def test_schema_rejects_missing_target_queue_ssm_path():
    bad = {
        "event_bridge_rules": [
            {
                "name": "r",
                "event_pattern": {"source": ["x"]},
            }
        ]
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=_schema())


def test_schema_registered_by_resource_key():
    key_schema = SchemaRegistry.get_module_schema(SAMPLE_ENTRY)
    assert key_schema is not None
    key, schema = key_schema
    assert key == "event_bridge_rules"
