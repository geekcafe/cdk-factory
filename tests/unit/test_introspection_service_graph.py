"""Unit tests for cdk_factory.introspection.service_graph.

Tests cover graph construction, edge creation, DLQ mapping,
topological ordering, execution flow derivation, and serialization.
"""

import pytest

from cdk_factory.introspection.config_parser import LambdaConfig, QueueConfig
from cdk_factory.introspection.service_graph import (
    QueueEdge,
    ServiceGraph,
    ServiceNode,
    build_service_graph,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PREFIX = "acme-saas-development-dev"


def _make_lambda(
    name: str,
    description: str = "",
    handler: str = "",
    timeout: int = 60,
    consumer_queues: list | None = None,
    producer_queues: list | None = None,
    dlq_consumer_queues: list | None = None,
) -> LambdaConfig:
    """Create a LambdaConfig with sensible defaults."""
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


def _build_admission_workflow_orchestrator() -> list[LambdaConfig]:
    """Build a minimal admission → workflow_builder → orchestrator pipeline."""
    admission = _make_lambda(
        name="analysis-admission-handler",
        description="Admission handler",
        handler="admission.app.lambda_handler",
        timeout=180,
        consumer_queues=[
            _queue(f"{PREFIX}-analysis-admission", "consumer", has_dlq=True),
        ],
        producer_queues=[
            _queue(f"{PREFIX}-build-analysis-workflow-steps", "producer"),
        ],
    )
    workflow_builder = _make_lambda(
        name="analysis-workflow-step-builder",
        description="Workflow step builder",
        handler="workflow_builder.app.lambda_handler",
        timeout=600,
        consumer_queues=[
            _queue(f"{PREFIX}-build-analysis-workflow-steps", "consumer", has_dlq=True),
        ],
        producer_queues=[
            _queue(f"{PREFIX}-workflow-step-processor", "producer"),
        ],
    )
    orchestrator = _make_lambda(
        name="workflow-step-processor",
        description="Step processor",
        handler="step_processor.app.lambda_handler",
        timeout=600,
        consumer_queues=[
            _queue(f"{PREFIX}-workflow-step-processor", "consumer", has_dlq=True),
        ],
        producer_queues=[
            _queue(f"{PREFIX}-analysis-data-cleaning", "producer"),
            _queue(f"{PREFIX}-workflow-complete", "producer"),
        ],
    )
    return [admission, workflow_builder, orchestrator]


# ---------------------------------------------------------------------------
# Tests: build_service_graph — node creation
# ---------------------------------------------------------------------------


class TestBuildServiceGraphNodes:
    def test_creates_node_for_each_config(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        assert len(graph.nodes) == 3

    def test_node_names_match_config_names(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        assert set(graph.nodes.keys()) == {
            "analysis-admission-handler",
            "analysis-workflow-step-builder",
            "workflow-step-processor",
        }

    def test_node_fields_populated(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        node = graph.nodes["analysis-admission-handler"]
        assert node.description == "Admission handler"
        assert node.handler == "admission.app.lambda_handler"
        assert node.timeout == 180
        assert node.memory_size == 128

    def test_consumer_queue_set(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        node = graph.nodes["analysis-admission-handler"]
        assert node.consumer_queue == f"{PREFIX}-analysis-admission"

    def test_producer_queues_set(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        node = graph.nodes["workflow-step-processor"]
        assert f"{PREFIX}-analysis-data-cleaning" in node.producer_queues
        assert f"{PREFIX}-workflow-complete" in node.producer_queues

    def test_dlq_name_set_when_has_dlq(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        node = graph.nodes["analysis-admission-handler"]
        assert node.dlq_name == f"{PREFIX}-analysis-admission-dlq"

    def test_no_consumer_queue_when_none(self):
        config = _make_lambda(name="isolated-lambda")
        graph = build_service_graph([config])
        assert graph.nodes["isolated-lambda"].consumer_queue is None

    def test_no_dlq_name_when_no_dlq(self):
        config = _make_lambda(
            name="no-dlq-lambda",
            consumer_queues=[_queue("some-queue", "consumer", has_dlq=False)],
        )
        graph = build_service_graph([config])
        assert graph.nodes["no-dlq-lambda"].dlq_name is None


# ---------------------------------------------------------------------------
# Tests: build_service_graph — edge creation
# ---------------------------------------------------------------------------


class TestBuildServiceGraphEdges:
    def test_creates_edges_for_matched_producer_consumer(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        non_dlq_edges = [e for e in graph.edges if not e.is_dlq]
        # admission → workflow_builder, workflow_builder → orchestrator
        assert len(non_dlq_edges) == 2

    def test_edge_from_admission_to_workflow_builder(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        edge = next(
            (
                e
                for e in graph.edges
                if e.from_lambda == "analysis-admission-handler" and not e.is_dlq
            ),
            None,
        )
        assert edge is not None
        assert edge.to_lambda == "analysis-workflow-step-builder"
        assert edge.queue_name == f"{PREFIX}-build-analysis-workflow-steps"
        assert edge.is_dlq is False

    def test_no_edge_for_unmatched_producer(self):
        # orchestrator produces to analysis-data-cleaning and workflow-complete
        # but no Lambda consumes those queues in this set
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        unmatched_edges = [
            e for e in graph.edges if e.queue_name == f"{PREFIX}-analysis-data-cleaning"
        ]
        assert len(unmatched_edges) == 0

    def test_self_loop_edge(self):
        """A Lambda that produces to its own consumer queue creates a self-loop."""
        config = _make_lambda(
            name="self-loop",
            consumer_queues=[_queue("loop-queue", "consumer")],
            producer_queues=[_queue("loop-queue", "producer")],
        )
        graph = build_service_graph([config])
        assert len(graph.edges) == 1
        assert graph.edges[0].from_lambda == "self-loop"
        assert graph.edges[0].to_lambda == "self-loop"


# ---------------------------------------------------------------------------
# Tests: DLQ mapping
# ---------------------------------------------------------------------------


class TestDlqMapping:
    def test_dlq_map_created_for_has_dlq_queues(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        assert f"{PREFIX}-analysis-admission" in graph.dlq_map
        assert (
            graph.dlq_map[f"{PREFIX}-analysis-admission"]
            == f"{PREFIX}-analysis-admission-dlq"
        )

    def test_dlq_map_not_created_for_no_dlq(self):
        config = _make_lambda(
            name="no-dlq",
            consumer_queues=[_queue("plain-queue", "consumer", has_dlq=False)],
        )
        graph = build_service_graph([config])
        assert len(graph.dlq_map) == 0

    def test_dlq_edge_created_when_dlq_consumer_exists(self):
        admission = _make_lambda(
            name="admission",
            consumer_queues=[_queue("admission-queue", "consumer", has_dlq=True)],
        )
        dlq_handler = _make_lambda(
            name="dlq-handler",
            dlq_consumer_queues=[_queue("admission-queue-dlq", "dlq_consumer")],
        )
        graph = build_service_graph([admission, dlq_handler])
        dlq_edges = [e for e in graph.edges if e.is_dlq]
        assert len(dlq_edges) == 1
        assert dlq_edges[0].queue_name == "admission-queue-dlq"
        assert dlq_edges[0].from_lambda == "admission"
        assert dlq_edges[0].to_lambda == "dlq-handler"

    def test_get_dlq_for_queue(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        assert (
            graph.get_dlq_for_queue(f"{PREFIX}-analysis-admission")
            == f"{PREFIX}-analysis-admission-dlq"
        )
        assert graph.get_dlq_for_queue("nonexistent-queue") is None


# ---------------------------------------------------------------------------
# Tests: get_downstream / get_upstream
# ---------------------------------------------------------------------------


class TestDownstreamUpstream:
    def test_get_downstream(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        downstream = graph.get_downstream("analysis-admission-handler")
        assert downstream == ["analysis-workflow-step-builder"]

    def test_get_upstream(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        upstream = graph.get_upstream("analysis-workflow-step-builder")
        assert upstream == ["analysis-admission-handler"]

    def test_get_downstream_excludes_dlq_edges(self):
        admission = _make_lambda(
            name="admission",
            consumer_queues=[_queue("admission-queue", "consumer", has_dlq=True)],
        )
        dlq_handler = _make_lambda(
            name="dlq-handler",
            dlq_consumer_queues=[_queue("admission-queue-dlq", "dlq_consumer")],
        )
        graph = build_service_graph([admission, dlq_handler])
        # DLQ edge should not appear in downstream
        assert graph.get_downstream("admission") == []

    def test_get_upstream_excludes_dlq_edges(self):
        admission = _make_lambda(
            name="admission",
            consumer_queues=[_queue("admission-queue", "consumer", has_dlq=True)],
        )
        dlq_handler = _make_lambda(
            name="dlq-handler",
            dlq_consumer_queues=[_queue("admission-queue-dlq", "dlq_consumer")],
        )
        graph = build_service_graph([admission, dlq_handler])
        assert graph.get_upstream("dlq-handler") == []

    def test_get_downstream_empty_for_leaf(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        # orchestrator has no matched consumers
        assert graph.get_downstream("workflow-step-processor") == []

    def test_get_upstream_empty_for_root(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        assert graph.get_upstream("analysis-admission-handler") == []


# ---------------------------------------------------------------------------
# Tests: topological_order
# ---------------------------------------------------------------------------


class TestTopologicalOrder:
    def test_linear_chain_order(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        order = graph.topological_order()
        assert order == [
            "analysis-admission-handler",
            "analysis-workflow-step-builder",
            "workflow-step-processor",
        ]

    def test_start_from_middle(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        order = graph.topological_order(start_from="analysis-workflow-step-builder")
        assert "analysis-admission-handler" not in order
        assert order[0] == "analysis-workflow-step-builder"
        assert "workflow-step-processor" in order

    def test_start_from_leaf(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        order = graph.topological_order(start_from="workflow-step-processor")
        assert order == ["workflow-step-processor"]

    def test_isolated_node(self):
        config = _make_lambda(name="isolated")
        graph = build_service_graph([config])
        order = graph.topological_order()
        assert order == ["isolated"]

    def test_empty_graph(self):
        graph = build_service_graph([])
        assert graph.topological_order() == []

    def test_topological_order_respects_edges(self):
        """For every edge (u, v), u appears before v."""
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        order = graph.topological_order()
        for edge in graph.edges:
            if edge.is_dlq:
                continue
            if edge.from_lambda in order and edge.to_lambda in order:
                assert order.index(edge.from_lambda) < order.index(edge.to_lambda)


# ---------------------------------------------------------------------------
# Tests: derive_execution_flows
# ---------------------------------------------------------------------------


class TestDeriveExecutionFlows:
    def test_single_root_produces_main_flow(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        flows = graph.derive_execution_flows()
        assert "main" in flows
        assert flows["main"] == [
            "analysis-admission-handler",
            "analysis-workflow-step-builder",
            "workflow-step-processor",
        ]

    def test_multiple_roots_produce_named_flows(self):
        lambda_a = _make_lambda(
            name="root-a",
            producer_queues=[_queue("q1", "producer")],
        )
        lambda_b = _make_lambda(
            name="root-b",
            producer_queues=[_queue("q2", "producer")],
        )
        consumer_1 = _make_lambda(
            name="consumer-1",
            consumer_queues=[_queue("q1", "consumer")],
        )
        consumer_2 = _make_lambda(
            name="consumer-2",
            consumer_queues=[_queue("q2", "consumer")],
        )
        graph = build_service_graph([lambda_a, lambda_b, consumer_1, consumer_2])
        flows = graph.derive_execution_flows()
        assert len(flows) >= 2
        # Each root should have its own flow
        assert any("root-a" in flow for flow in flows.values())
        assert any("root-b" in flow for flow in flows.values())

    def test_empty_graph_flows(self):
        graph = build_service_graph([])
        flows = graph.derive_execution_flows()
        assert "main" in flows
        assert flows["main"] == []


# ---------------------------------------------------------------------------
# Tests: to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_structure(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        d = graph.to_dict()
        assert "nodes" in d
        assert "edges" in d
        assert "dlq_map" in d

    def test_to_dict_nodes(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        d = graph.to_dict()
        assert "analysis-admission-handler" in d["nodes"]
        node = d["nodes"]["analysis-admission-handler"]
        assert node["name"] == "analysis-admission-handler"
        assert node["timeout"] == 180
        assert node["consumer_queue"] == f"{PREFIX}-analysis-admission"
        assert node["dlq_name"] == f"{PREFIX}-analysis-admission-dlq"

    def test_to_dict_edges(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        d = graph.to_dict()
        non_dlq_edges = [e for e in d["edges"] if not e["is_dlq"]]
        assert len(non_dlq_edges) == 2

    def test_to_dict_dlq_map(self):
        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        d = graph.to_dict()
        assert f"{PREFIX}-analysis-admission" in d["dlq_map"]

    def test_to_dict_is_json_serializable(self):
        import json

        configs = _build_admission_workflow_orchestrator()
        graph = build_service_graph(configs)
        # Should not raise
        json.dumps(graph.to_dict())
