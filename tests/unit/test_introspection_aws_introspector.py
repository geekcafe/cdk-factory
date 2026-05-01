"""Unit tests for cdk_factory.introspection.aws_introspector.

Tests cover log group resolution, queue URL resolution, queue attributes,
service map generation, caching, error handling, and credential validation.
All AWS calls are mocked via unittest.mock.
"""

import json
from unittest.mock import MagicMock, patch

import botocore.exceptions
import pytest

from cdk_factory.introspection.aws_introspector import (
    AwsCredentialError,
    AwsIntrospector,
    ResolvedLambda,
    _derive_service_key,
    select_best_log_group,
)
from cdk_factory.introspection.config_parser import LambdaConfig, QueueConfig
from cdk_factory.introspection.service_graph import ServiceGraph, build_service_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PREFIX = "aplos-nca-saas-development-dev"


def _make_lambda(
    name: str,
    description: str = "",
    handler: str = "",
    timeout: int = 60,
    consumer_queues: list | None = None,
    producer_queues: list | None = None,
    dlq_consumer_queues: list | None = None,
) -> LambdaConfig:
    return LambdaConfig(
        name=name,
        description=description,
        handler=handler,
        timeout=timeout,
        consumer_queues=consumer_queues or [],
        producer_queues=producer_queues or [],
        dlq_consumer_queues=dlq_consumer_queues or [],
    )


def _queue(
    name: str,
    queue_type: str = "consumer",
    has_dlq: bool = False,
) -> QueueConfig:
    return QueueConfig(queue_name=name, queue_type=queue_type, has_dlq=has_dlq)


def _build_simple_graph() -> ServiceGraph:
    """Build a simple admission → workflow_builder graph."""
    admission = _make_lambda(
        name="analysis-admission-handler",
        description="Admission handler",
        timeout=180,
        consumer_queues=[_queue(f"{PREFIX}-admission", "consumer", has_dlq=True)],
        producer_queues=[_queue(f"{PREFIX}-build-steps", "producer")],
    )
    builder = _make_lambda(
        name="analysis-workflow-step-builder",
        description="Workflow builder",
        timeout=600,
        consumer_queues=[_queue(f"{PREFIX}-build-steps", "consumer", has_dlq=True)],
    )
    return build_service_graph([admission, builder])


def _make_introspector_with_mocks():
    """Create an AwsIntrospector with all boto3 calls mocked.

    Returns (introspector, mock_session) where mock_session has
    .client() returning mocks for each service.
    """
    mock_session = MagicMock()
    mock_sts = MagicMock()
    mock_logs = MagicMock()
    mock_sqs = MagicMock()
    mock_ssm = MagicMock()

    def client_factory(service_name, **kwargs):
        return {
            "sts": mock_sts,
            "logs": mock_logs,
            "sqs": mock_sqs,
            "ssm": mock_ssm,
        }[service_name]

    mock_session.client.side_effect = client_factory

    with patch(
        "cdk_factory.introspection.aws_introspector.boto3.Session",
        return_value=mock_session,
    ):
        introspector = AwsIntrospector(profile_name="test-profile", region="us-east-1")

    return introspector, mock_logs, mock_sqs, mock_ssm, mock_sts


# ---------------------------------------------------------------------------
# Tests: select_best_log_group (pure function)
# ---------------------------------------------------------------------------


class TestSelectBestLogGroup:
    def test_selects_highest_stored_bytes(self):
        candidates = [
            {"logGroupName": "/aws/lambda/func-abc123", "storedBytes": 100},
            {"logGroupName": "/aws/lambda/func-def456", "storedBytes": 5000},
            {"logGroupName": "/aws/lambda/func-ghi789", "storedBytes": 200},
        ]
        name, stored = select_best_log_group(candidates)
        assert name == "/aws/lambda/func-def456"
        assert stored == 5000

    def test_single_candidate(self):
        candidates = [
            {"logGroupName": "/aws/lambda/my-func", "storedBytes": 42},
        ]
        name, stored = select_best_log_group(candidates)
        assert name == "/aws/lambda/my-func"
        assert stored == 42

    def test_empty_candidates(self):
        name, stored = select_best_log_group([])
        assert name is None
        assert stored == 0

    def test_missing_stored_bytes_defaults_to_zero(self):
        candidates = [
            {"logGroupName": "/aws/lambda/no-bytes"},
            {"logGroupName": "/aws/lambda/has-bytes", "storedBytes": 10},
        ]
        name, stored = select_best_log_group(candidates)
        assert name == "/aws/lambda/has-bytes"
        assert stored == 10

    def test_all_zero_stored_bytes(self):
        candidates = [
            {"logGroupName": "/aws/lambda/a", "storedBytes": 0},
            {"logGroupName": "/aws/lambda/b", "storedBytes": 0},
        ]
        name, stored = select_best_log_group(candidates)
        # Should return one of them (deterministic via max)
        assert name is not None
        assert stored == 0


# ---------------------------------------------------------------------------
# Tests: _derive_service_key (pure function)
# ---------------------------------------------------------------------------


class TestDeriveServiceKey:
    def test_strips_analysis_prefix(self):
        assert _derive_service_key("analysis-admission-handler") == "admission_handler"

    def test_strips_workflow_prefix(self):
        assert _derive_service_key("workflow-step-processor") == "step_processor"

    def test_no_prefix_to_strip(self):
        assert _derive_service_key("custom-lambda") == "custom_lambda"

    def test_converts_hyphens_to_underscores(self):
        assert _derive_service_key("analysis-data-cleaning") == "data_cleaning"


# ---------------------------------------------------------------------------
# Tests: resolve_log_groups
# ---------------------------------------------------------------------------


class TestResolveLogGroups:
    def test_resolves_log_groups_for_all_lambdas(self):
        introspector, mock_logs, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()

        # Mock describe_log_groups to return one group per Lambda
        def describe_side_effect(**kwargs):
            prefix = kwargs["logGroupNamePrefix"]
            if "admission" in prefix:
                return {
                    "logGroups": [
                        {"logGroupName": f"{prefix}-abc123", "storedBytes": 500}
                    ]
                }
            elif "step-builder" in prefix:
                return {
                    "logGroups": [
                        {"logGroupName": f"{prefix}-def456", "storedBytes": 300}
                    ]
                }
            return {"logGroups": []}

        mock_logs.describe_log_groups.side_effect = describe_side_effect

        resolved = introspector.resolve_log_groups(graph)

        assert len(resolved) == 2
        assert resolved["analysis-admission-handler"].log_group is not None
        assert resolved["analysis-admission-handler"].unresolved is False
        assert resolved["analysis-workflow-step-builder"].log_group is not None

    def test_selects_highest_stored_bytes_when_multiple_match(self):
        introspector, mock_logs, _, _, _ = _make_introspector_with_mocks()

        # Single-node graph
        config = _make_lambda(name="my-func")
        graph = build_service_graph([config])

        mock_logs.describe_log_groups.return_value = {
            "logGroups": [
                {"logGroupName": "/aws/lambda/my-func-old", "storedBytes": 100},
                {"logGroupName": "/aws/lambda/my-func-active", "storedBytes": 9999},
                {"logGroupName": "/aws/lambda/my-func-stale", "storedBytes": 50},
            ]
        }

        resolved = introspector.resolve_log_groups(graph)
        assert resolved["my-func"].log_group == "/aws/lambda/my-func-active"
        assert resolved["my-func"].log_group_stored_bytes == 9999

    def test_marks_unresolved_when_no_log_group_found(self):
        introspector, mock_logs, _, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(name="missing-func")
        graph = build_service_graph([config])

        mock_logs.describe_log_groups.return_value = {"logGroups": []}

        resolved = introspector.resolve_log_groups(graph)
        assert resolved["missing-func"].unresolved is True
        assert resolved["missing-func"].log_group is None

    def test_caching_avoids_duplicate_api_calls(self):
        introspector, mock_logs, _, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(name="cached-func")
        graph = build_service_graph([config])

        mock_logs.describe_log_groups.return_value = {
            "logGroups": [
                {"logGroupName": "/aws/lambda/cached-func-xyz", "storedBytes": 200}
            ]
        }

        # First call
        resolved1 = introspector.resolve_log_groups(graph)
        # Second call — should use cache
        resolved2 = introspector.resolve_log_groups(graph)

        assert resolved1["cached-func"].log_group == resolved2["cached-func"].log_group
        # describe_log_groups should only be called once
        assert mock_logs.describe_log_groups.call_count == 1


# ---------------------------------------------------------------------------
# Tests: resolve_queue_urls
# ---------------------------------------------------------------------------


class TestResolveQueueUrls:
    def test_resolves_queue_urls(self):
        introspector, _, mock_sqs, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()

        def get_queue_url_side_effect(**kwargs):
            name = kwargs["QueueName"]
            return {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/123456789/{name}"}

        mock_sqs.get_queue_url.side_effect = get_queue_url_side_effect

        urls = introspector.resolve_queue_urls(graph)
        # Should have resolved URLs for edges + DLQ queues
        assert len(urls) > 0
        for queue_name, url in urls.items():
            assert queue_name in url

    def test_handles_nonexistent_queue(self):
        introspector, _, mock_sqs, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(
            name="func",
            consumer_queues=[_queue("nonexistent-queue", "consumer")],
            producer_queues=[_queue("nonexistent-queue", "producer")],
        )
        graph = build_service_graph([config])

        error_response = {
            "Error": {
                "Code": "AWS.SimpleQueueService.NonExistentQueue",
                "Message": "Queue not found",
            }
        }
        mock_sqs.get_queue_url.side_effect = botocore.exceptions.ClientError(
            error_response, "GetQueueUrl"
        )

        urls = introspector.resolve_queue_urls(graph)
        # Should return empty dict, not raise
        assert urls == {}

    def test_handles_access_denied(self):
        introspector, _, mock_sqs, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(
            name="func",
            consumer_queues=[_queue("denied-queue", "consumer")],
            producer_queues=[_queue("denied-queue", "producer")],
        )
        graph = build_service_graph([config])

        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        mock_sqs.get_queue_url.side_effect = botocore.exceptions.ClientError(
            error_response, "GetQueueUrl"
        )

        urls = introspector.resolve_queue_urls(graph)
        assert urls == {}


# ---------------------------------------------------------------------------
# Tests: get_queue_attributes
# ---------------------------------------------------------------------------


class TestGetQueueAttributes:
    def test_returns_attributes(self):
        introspector, _, mock_sqs, _, _ = _make_introspector_with_mocks()

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "5",
                "ApproximateNumberOfMessagesNotVisible": "2",
            }
        }

        attrs = introspector.get_queue_attributes("https://sqs.example.com/my-queue")
        assert attrs["ApproximateNumberOfMessages"] == "5"
        assert attrs["ApproximateNumberOfMessagesNotVisible"] == "2"

    def test_returns_empty_on_access_denied(self):
        introspector, _, mock_sqs, _, _ = _make_introspector_with_mocks()

        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        mock_sqs.get_queue_attributes.side_effect = botocore.exceptions.ClientError(
            error_response, "GetQueueAttributes"
        )

        attrs = introspector.get_queue_attributes("https://sqs.example.com/my-queue")
        assert attrs == {}


# ---------------------------------------------------------------------------
# Tests: generate_service_map
# ---------------------------------------------------------------------------


class TestGenerateServiceMap:
    def test_service_map_has_required_top_level_keys(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {
            name: ResolvedLambda(
                name=name,
                log_group=f"/aws/lambda/{name}-hash",
                log_group_stored_bytes=100,
            )
            for name in graph.nodes
        }

        service_map = introspector.generate_service_map(graph, resolved)

        assert "description" in service_map
        assert "version" in service_map
        assert "generated_at" in service_map
        assert "source" in service_map
        assert "services" in service_map
        assert "execution_flows" in service_map

    def test_service_map_contains_all_lambdas(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {name: ResolvedLambda(name=name) for name in graph.nodes}

        service_map = introspector.generate_service_map(graph, resolved)
        assert len(service_map["services"]) == len(graph.nodes)

    def test_service_entry_has_required_fields(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {
            name: ResolvedLambda(
                name=name,
                log_group=f"/aws/lambda/{name}-hash",
                log_group_stored_bytes=100,
            )
            for name in graph.nodes
        }

        service_map = introspector.generate_service_map(graph, resolved)

        for service_key, entry in service_map["services"].items():
            assert "description" in entry
            assert "timeout_seconds" in entry
            assert "lambda_name_template" in entry
            assert "cdk_function_name" in entry
            assert "log_groups" in entry
            assert "next_services" in entry

    def test_service_map_includes_log_groups(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(name="my-func", description="Test func", timeout=120)
        graph = build_service_graph([config])
        resolved = {
            "my-func": ResolvedLambda(
                name="my-func",
                log_group="/aws/lambda/my-func-abc123",
                log_group_stored_bytes=500,
            )
        }

        service_map = introspector.generate_service_map(graph, resolved)
        service = list(service_map["services"].values())[0]
        assert service["log_groups"]["resolved"] == "/aws/lambda/my-func-abc123"

    def test_service_map_includes_execution_flows(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {name: ResolvedLambda(name=name) for name in graph.nodes}

        service_map = introspector.generate_service_map(graph, resolved)
        assert len(service_map["execution_flows"]) >= 1

        # Each flow should have typical_flow
        for flow_name, flow_data in service_map["execution_flows"].items():
            assert "typical_flow" in flow_data
            assert "description" in flow_data
            assert len(flow_data["typical_flow"]) > 0

    def test_service_map_next_services_populated(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {name: ResolvedLambda(name=name) for name in graph.nodes}

        service_map = introspector.generate_service_map(graph, resolved)

        # admission_handler should have workflow_step_builder as next
        admission_key = _derive_service_key("analysis-admission-handler")
        builder_key = _derive_service_key("analysis-workflow-step-builder")

        admission_entry = service_map["services"][admission_key]
        assert builder_key in admission_entry["next_services"]

    def test_service_map_is_json_serializable(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {name: ResolvedLambda(name=name) for name in graph.nodes}

        service_map = introspector.generate_service_map(graph, resolved)
        # Should not raise
        json.dumps(service_map)

    def test_service_map_queue_fields(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()
        graph = _build_simple_graph()
        resolved = {name: ResolvedLambda(name=name) for name in graph.nodes}

        service_map = introspector.generate_service_map(graph, resolved)

        # admission has a consumer queue and a producer queue
        admission_key = _derive_service_key("analysis-admission-handler")
        admission_entry = service_map["services"][admission_key]
        assert "consumes_from_queue" in admission_entry
        assert "emits_to_queue" in admission_entry

    def test_unresolved_lambda_has_empty_log_groups(self):
        introspector, _, _, _, _ = _make_introspector_with_mocks()

        config = _make_lambda(name="unresolved-func")
        graph = build_service_graph([config])
        resolved = {
            "unresolved-func": ResolvedLambda(name="unresolved-func", unresolved=True)
        }

        service_map = introspector.generate_service_map(graph, resolved)
        service = list(service_map["services"].values())[0]
        assert service["log_groups"] == {}


# ---------------------------------------------------------------------------
# Tests: credential validation
# ---------------------------------------------------------------------------


class TestCredentialValidation:
    def test_expired_sso_token_raises_clear_error(self):
        mock_session = MagicMock()
        mock_sts = MagicMock()

        error_response = {"Error": {"Code": "ExpiredToken", "Message": "Token expired"}}
        mock_sts.get_caller_identity.side_effect = botocore.exceptions.ClientError(
            error_response, "GetCallerIdentity"
        )

        def client_factory(service_name, **kwargs):
            if service_name == "sts":
                return mock_sts
            return MagicMock()

        mock_session.client.side_effect = client_factory

        with patch(
            "cdk_factory.introspection.aws_introspector.boto3.Session",
            return_value=mock_session,
        ):
            with pytest.raises(AwsCredentialError, match="aws sso login"):
                AwsIntrospector(profile_name="my-profile")

    def test_no_credentials_raises_clear_error(self):
        mock_session = MagicMock()
        mock_sts = MagicMock()

        mock_sts.get_caller_identity.side_effect = (
            botocore.exceptions.NoCredentialsError()
        )

        def client_factory(service_name, **kwargs):
            if service_name == "sts":
                return mock_sts
            return MagicMock()

        mock_session.client.side_effect = client_factory

        with patch(
            "cdk_factory.introspection.aws_introspector.boto3.Session",
            return_value=mock_session,
        ):
            with pytest.raises(AwsCredentialError, match="No AWS credentials found"):
                AwsIntrospector()

    def test_profile_not_found_raises_clear_error(self):
        with patch(
            "cdk_factory.introspection.aws_introspector.boto3.Session",
            side_effect=botocore.exceptions.ProfileNotFound(profile="bad-profile"),
        ):
            with pytest.raises(AwsCredentialError, match="bad-profile"):
                AwsIntrospector(profile_name="bad-profile")
