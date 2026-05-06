"""Unit tests for cdk_factory.introspection.config_parser.

Tests cover parsing real CDK config files, template variable resolution,
queue classification, SQS URL extraction, and error handling.
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict

import pytest

from cdk_factory.introspection.config_parser import (
    LambdaConfig,
    QueueConfig,
    parse_lambda_configs,
    resolve_template_variables,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENV_VARS = {
    "WORKLOAD_NAME": "acme-saas",
    "DEPLOYMENT_NAMESPACE": "development-dev",
}


def _write_config(base_dir: str, subpath: str, data: Dict[str, Any]) -> str:
    """Write a JSON config file under the standard resource directory layout."""
    resource_dir = os.path.join(base_dir, "stacks", "lambdas", "resources", subpath)
    os.makedirs(resource_dir, exist_ok=True)
    file_path = os.path.join(resource_dir, f"{data.get('name', 'unnamed')}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return file_path


def _make_admission_config() -> Dict[str, Any]:
    """Return a config dict modeled after analysis-admission-handler.json."""
    return {
        "name": "analysis-admission-handler",
        "timeout": 180,
        "description": "Admission handler for analysis workflow.",
        "image_config": {
            "command": [
                "aplos_nca_orchestration.handlers.analysis.admission.app.lambda_handler"
            ]
        },
        "environment_variables": [
            {
                "name": "SQS_URL_ADMISSION_QUEUE",
                "value": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-analysis-admission",
                "transform": True,
            },
            {
                "name": "SQS_URL_BUILD_ANALYSIS_WORKFLOW_STEPS",
                "value": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-build-analysis-workflow-steps",
                "transform": True,
            },
            {
                "name": "THROTTLING_ENABLED",
                "value": "false",
            },
        ],
        "sqs": {
            "queues": [
                {
                    "type": "consumer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-analysis-admission",
                    "description": "admission queue",
                    "visibility_timeout_seconds": 180,
                    "delay_seconds": 0,
                    "add_dead_letter_queue": True,
                },
                {
                    "type": "producer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-build-analysis-workflow-steps",
                    "description": "routes to workflow step builder",
                },
            ]
        },
    }


def _make_step_processor_config() -> Dict[str, Any]:
    """Return a config dict modeled after workflow-step-processor.json."""
    return {
        "name": "workflow-step-processor",
        "description": "Workflow Step Processor.",
        "image_config": {
            "command": [
                "aplos_nca_orchestration.handlers.execution_workflow.step_processor.app.lambda_handler"
            ]
        },
        "environment_variables": [
            {
                "name": "SQS_URL_WORKFLOW_STEP_PROCESSOR",
                "value": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-step-processor",
                "transform": True,
            },
            {
                "name": "SQS_URL_CUSTOM_CALCULATIONS",
                "value": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-custom-calculations",
                "transform": True,
            },
            {
                "name": "ANALYSIS_BUCKET",
                "value": "{{S3_WORKLOAD_BUCKET_NAME}}",
            },
        ],
        "sqs": {
            "queues": [
                {
                    "type": "consumer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-step-processor",
                    "description": "consumer queue",
                    "visibility_timeout_seconds": 30,
                    "delay_seconds": 5,
                    "add_dead_letter_queue": True,
                },
                {
                    "type": "producer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-step-processor",
                    "description": "sends back to itself",
                },
                {
                    "type": "producer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-complete",
                    "description": "complete step",
                },
                {
                    "type": "producer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-analysis-data-cleaning",
                    "description": "data cleaning",
                },
            ]
        },
    }


def _make_dlq_handler_config() -> Dict[str, Any]:
    """Return a config dict modeled after workflow-dlq-handler.json."""
    return {
        "name": "workflow-dlq-handler",
        "timeout": 30,
        "description": "DLQ handler for failed workflows.",
        "image_config": {
            "command": [
                "aplos_nca_orchestration.handlers.execution_workflow.dlq_monitor.app.lambda_handler"
            ]
        },
        "environment_variables": [
            {
                "name": "SQS_URL_WORKFLOW_STEP_PROCESSOR",
                "value": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-step-processor",
                "transform": True,
            },
        ],
        "sqs": {
            "queues": [
                {
                    "type": "dlq_consumer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-analysis-data-cleaning-dlq",
                    "description": "DLQ for data-cleaning",
                },
                {
                    "type": "dlq_consumer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-analysis-admission-dlq",
                    "description": "DLQ for admission",
                },
                {
                    "type": "producer",
                    "queue_name": "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-workflow-step-processor",
                    "description": "Sends failure completion messages",
                },
            ]
        },
    }


# ---------------------------------------------------------------------------
# Tests: resolve_template_variables
# ---------------------------------------------------------------------------


class TestResolveTemplateVariables:
    def test_replaces_known_placeholders(self):
        result = resolve_template_variables(
            "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-queue",
            ENV_VARS,
        )
        assert result == "acme-saas-development-dev-queue"

    def test_leaves_unknown_placeholders(self):
        result = resolve_template_variables(
            "{{WORKLOAD_NAME}}-{{UNKNOWN}}-queue",
            ENV_VARS,
        )
        assert result == "acme-saas-{{UNKNOWN}}-queue"

    def test_empty_env_vars(self):
        result = resolve_template_variables("{{WORKLOAD_NAME}}-test", {})
        assert result == "{{WORKLOAD_NAME}}-test"

    def test_no_placeholders(self):
        result = resolve_template_variables("plain-string", ENV_VARS)
        assert result == "plain-string"

    def test_empty_string(self):
        result = resolve_template_variables("", ENV_VARS)
        assert result == ""

    def test_multiple_same_placeholder(self):
        result = resolve_template_variables(
            "{{WORKLOAD_NAME}}-{{WORKLOAD_NAME}}", ENV_VARS
        )
        assert result == "acme-saas-acme-saas"


# ---------------------------------------------------------------------------
# Tests: parse_lambda_configs — admission handler
# ---------------------------------------------------------------------------


class TestParseAdmissionHandler:
    @pytest.fixture()
    def parsed_configs(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow/sqs-handler", _make_admission_config())
        return parse_lambda_configs(config_dir, env_vars=ENV_VARS)

    def test_parses_one_config(self, parsed_configs):
        assert len(parsed_configs) == 1

    def test_name(self, parsed_configs):
        assert parsed_configs[0].name == "analysis-admission-handler"

    def test_description(self, parsed_configs):
        assert "Admission handler" in parsed_configs[0].description

    def test_handler(self, parsed_configs):
        assert parsed_configs[0].handler == (
            "aplos_nca_orchestration.handlers.analysis.admission.app.lambda_handler"
        )

    def test_timeout(self, parsed_configs):
        assert parsed_configs[0].timeout == 180

    def test_memory_size_default(self, parsed_configs):
        assert parsed_configs[0].memory_size == 128

    def test_consumer_queues(self, parsed_configs):
        consumers = parsed_configs[0].consumer_queues
        assert len(consumers) == 1
        assert consumers[0].queue_name == "acme-saas-development-dev-analysis-admission"
        assert consumers[0].queue_type == "consumer"
        assert consumers[0].has_dlq is True
        assert consumers[0].visibility_timeout == 180

    def test_producer_queues(self, parsed_configs):
        producers = parsed_configs[0].producer_queues
        assert len(producers) == 1
        assert producers[0].queue_name == (
            "acme-saas-development-dev-build-analysis-workflow-steps"
        )

    def test_sqs_url_references(self, parsed_configs):
        refs = parsed_configs[0].sqs_url_references
        assert "SQS_URL_ADMISSION_QUEUE" in refs
        assert refs["SQS_URL_ADMISSION_QUEUE"] == (
            "acme-saas-development-dev-analysis-admission"
        )
        assert "SQS_URL_BUILD_ANALYSIS_WORKFLOW_STEPS" in refs
        # Non-SQS env vars should NOT be in sqs_url_references
        assert "THROTTLING_ENABLED" not in refs

    def test_environment_variables_include_all(self, parsed_configs):
        env = parsed_configs[0].environment_variables
        assert "THROTTLING_ENABLED" in env
        assert env["THROTTLING_ENABLED"] == "false"
        assert "SQS_URL_ADMISSION_QUEUE" in env


# ---------------------------------------------------------------------------
# Tests: parse_lambda_configs — step processor (complex config)
# ---------------------------------------------------------------------------


class TestParseStepProcessor:
    @pytest.fixture()
    def parsed_configs(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow/sqs-handler", _make_step_processor_config())
        return parse_lambda_configs(config_dir, env_vars=ENV_VARS)

    def test_multiple_producer_queues(self, parsed_configs):
        producers = parsed_configs[0].producer_queues
        assert len(producers) == 3
        queue_names = [q.queue_name for q in producers]
        assert "acme-saas-development-dev-workflow-step-processor" in queue_names
        assert "acme-saas-development-dev-workflow-complete" in queue_names
        assert "acme-saas-development-dev-analysis-data-cleaning" in queue_names

    def test_consumer_queue_with_dlq(self, parsed_configs):
        consumers = parsed_configs[0].consumer_queues
        assert len(consumers) == 1
        assert consumers[0].has_dlq is True
        assert consumers[0].delay_seconds == 5

    def test_sqs_url_references_only_sqs_prefix(self, parsed_configs):
        refs = parsed_configs[0].sqs_url_references
        assert "SQS_URL_WORKFLOW_STEP_PROCESSOR" in refs
        assert "SQS_URL_CUSTOM_CALCULATIONS" in refs
        # ANALYSIS_BUCKET should NOT be in sqs_url_references
        assert "ANALYSIS_BUCKET" not in refs


# ---------------------------------------------------------------------------
# Tests: parse_lambda_configs — DLQ handler
# ---------------------------------------------------------------------------


class TestParseDlqHandler:
    @pytest.fixture()
    def parsed_configs(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow/sqs-handler", _make_dlq_handler_config())
        return parse_lambda_configs(config_dir, env_vars=ENV_VARS)

    def test_dlq_consumer_queues(self, parsed_configs):
        dlq_consumers = parsed_configs[0].dlq_consumer_queues
        assert len(dlq_consumers) == 2
        names = [q.queue_name for q in dlq_consumers]
        assert "acme-saas-development-dev-analysis-data-cleaning-dlq" in names
        assert "acme-saas-development-dev-analysis-admission-dlq" in names

    def test_dlq_consumer_type(self, parsed_configs):
        for q in parsed_configs[0].dlq_consumer_queues:
            assert q.queue_type == "dlq_consumer"

    def test_producer_queue_present(self, parsed_configs):
        producers = parsed_configs[0].producer_queues
        assert len(producers) == 1
        assert "workflow-step-processor" in producers[0].queue_name


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_invalid_json_logs_warning_and_continues(self, tmp_path, caplog):
        config_dir = str(tmp_path)
        # Write a valid config
        _write_config(config_dir, "workflow", _make_admission_config())

        # Write an invalid JSON file
        resource_dir = os.path.join(
            config_dir, "stacks", "lambdas", "resources", "workflow"
        )
        bad_file = os.path.join(resource_dir, "bad-config.json")
        with open(bad_file, "w") as f:
            f.write("{invalid json content")

        with caplog.at_level(logging.WARNING):
            configs = parse_lambda_configs(config_dir, env_vars=ENV_VARS)

        # Valid config should still be parsed
        assert len(configs) == 1
        assert configs[0].name == "analysis-admission-handler"
        # Warning should be logged for the bad file
        assert any("bad-config.json" in record.message for record in caplog.records)

    def test_missing_name_field_logs_warning_and_skips(self, tmp_path, caplog):
        config_dir = str(tmp_path)
        resource_dir = os.path.join(
            config_dir, "stacks", "lambdas", "resources", "workflow"
        )
        os.makedirs(resource_dir, exist_ok=True)

        # Write a config without a name field
        no_name = {"description": "No name field", "timeout": 60}
        file_path = os.path.join(resource_dir, "no-name.json")
        with open(file_path, "w") as f:
            json.dump(no_name, f)

        with caplog.at_level(logging.WARNING):
            configs = parse_lambda_configs(config_dir, env_vars=ENV_VARS)

        assert len(configs) == 0
        assert any(
            "Missing required 'name' field" in record.message
            for record in caplog.records
        )

    def test_missing_config_dir_raises(self, tmp_path):
        with pytest.raises(
            FileNotFoundError, match="Config resource directory not found"
        ):
            parse_lambda_configs(str(tmp_path / "nonexistent"))

    def test_no_sqs_section_parses_without_queues(self, tmp_path):
        config_dir = str(tmp_path)
        data = {
            "name": "simple-lambda",
            "description": "Lambda without SQS",
            "timeout": 60,
        }
        _write_config(config_dir, "workflow", data)
        configs = parse_lambda_configs(config_dir, env_vars=ENV_VARS)
        assert len(configs) == 1
        assert configs[0].consumer_queues == []
        assert configs[0].producer_queues == []
        assert configs[0].dlq_consumer_queues == []


# ---------------------------------------------------------------------------
# Tests: resource_subdirs filtering
# ---------------------------------------------------------------------------


class TestResourceSubdirs:
    def test_filters_to_specified_subdirs(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow/sqs-handler", _make_admission_config())
        _write_config(
            config_dir,
            "other",
            {"name": "other-lambda", "description": "other"},
        )

        # Only scan workflow subdirectory
        configs = parse_lambda_configs(
            config_dir, env_vars=ENV_VARS, resource_subdirs=["workflow"]
        )
        assert len(configs) == 1
        assert configs[0].name == "analysis-admission-handler"

    def test_default_scans_all_subdirs(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow/sqs-handler", _make_admission_config())
        _write_config(
            config_dir,
            "other",
            {"name": "other-lambda", "description": "other"},
        )

        configs = parse_lambda_configs(config_dir, env_vars=ENV_VARS)
        assert len(configs) == 2
        names = {c.name for c in configs}
        assert names == {"analysis-admission-handler", "other-lambda"}


# ---------------------------------------------------------------------------
# Tests: source_file tracking
# ---------------------------------------------------------------------------


class TestSourceFile:
    def test_source_file_is_set(self, tmp_path):
        config_dir = str(tmp_path)
        _write_config(config_dir, "workflow", _make_admission_config())
        configs = parse_lambda_configs(config_dir, env_vars=ENV_VARS)
        assert configs[0].source_file.endswith(".json")
        assert "analysis-admission-handler" in configs[0].source_file
