"""Service dependency graph builder.

Builds a directed graph of Lambda → Queue → Lambda relationships from
parsed CDK Lambda configurations. Supports topological traversal,
upstream/downstream queries, DLQ mapping, and execution flow derivation.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cdk_factory.introspection.config_parser import LambdaConfig


@dataclass
class ServiceNode:
    """A Lambda function in the service graph."""

    name: str
    description: str = ""
    handler: str = ""
    timeout: int = 0
    memory_size: int = 128
    consumer_queue: Optional[str] = None
    producer_queues: List[str] = field(default_factory=list)
    dlq_name: Optional[str] = None


@dataclass
class QueueEdge:
    """A directed edge representing an SQS queue connection."""

    queue_name: str
    from_lambda: str
    to_lambda: str
    is_dlq: bool = False


class ServiceGraph:
    """Directed graph of Lambda-to-queue-to-Lambda relationships."""

    def __init__(self) -> None:
        self.nodes: Dict[str, ServiceNode] = {}
        self.edges: List[QueueEdge] = []
        self.dlq_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_downstream(self, lambda_name: str) -> List[str]:
        """Get Lambda names downstream of the given Lambda.

        Returns the names of all Lambdas that consume from queues
        produced by *lambda_name*.
        """
        return [
            edge.to_lambda
            for edge in self.edges
            if edge.from_lambda == lambda_name and not edge.is_dlq
        ]

    def get_upstream(self, lambda_name: str) -> List[str]:
        """Get Lambda names upstream of the given Lambda.

        Returns the names of all Lambdas that produce to queues
        consumed by *lambda_name*.
        """
        return [
            edge.from_lambda
            for edge in self.edges
            if edge.to_lambda == lambda_name and not edge.is_dlq
        ]

    def get_dlq_for_queue(self, queue_name: str) -> Optional[str]:
        """Get the DLQ name for a given queue, or None."""
        return self.dlq_map.get(queue_name)

    # ------------------------------------------------------------------
    # Topological ordering
    # ------------------------------------------------------------------

    def topological_order(self, start_from: Optional[str] = None) -> List[str]:
        """Return Lambdas in topological order.

        If *start_from* is given, only nodes reachable from that node
        are included.  Otherwise traversal starts from all root nodes
        (nodes with no non-DLQ incoming edges).

        Uses Kahn's algorithm (BFS-based) so the result is deterministic
        when node names are sorted at each step.
        """
        # Build adjacency and in-degree maps using only non-DLQ edges.
        adj: Dict[str, List[str]] = {name: [] for name in self.nodes}
        in_degree: Dict[str, int] = {name: 0 for name in self.nodes}

        for edge in self.edges:
            if edge.is_dlq:
                continue
            if edge.from_lambda in adj and edge.to_lambda in in_degree:
                adj[edge.from_lambda].append(edge.to_lambda)
                in_degree[edge.to_lambda] += 1

        if start_from is not None:
            # Restrict to the subgraph reachable from start_from.
            reachable = self._reachable_from(start_from, adj)
            adj = {
                n: [c for c in children if c in reachable]
                for n, children in adj.items()
                if n in reachable
            }
            in_degree = {n: 0 for n in reachable}
            for node, children in adj.items():
                for child in children:
                    in_degree[child] += 1
            roots = sorted([n for n, d in in_degree.items() if d == 0])
        else:
            roots = sorted([n for n, d in in_degree.items() if d == 0])

        order: List[str] = []
        queue: deque[str] = deque(roots)

        while queue:
            node = queue.popleft()
            order.append(node)
            for child in sorted(adj.get(node, [])):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        return order

    # ------------------------------------------------------------------
    # Execution flow derivation
    # ------------------------------------------------------------------

    def derive_execution_flows(self) -> Dict[str, List[str]]:
        """Derive named execution flow sequences from graph structure.

        Identifies root nodes (no non-DLQ incoming edges) and performs a
        depth-first traversal from each root to produce named flows.
        If only one root exists the flow is named ``"main"``.
        """
        # Identify roots (no non-DLQ incoming edges).
        has_incoming: set[str] = set()
        for edge in self.edges:
            if not edge.is_dlq:
                has_incoming.add(edge.to_lambda)

        roots = sorted(name for name in self.nodes if name not in has_incoming)

        if not roots:
            # Graph has cycles or is empty — fall back to all nodes.
            return {"main": self.topological_order()}

        flows: Dict[str, List[str]] = {}
        if len(roots) == 1:
            flows["main"] = self.topological_order(start_from=roots[0])
        else:
            for idx, root in enumerate(roots):
                flow_name = f"flow_{root}"
                flows[flow_name] = self.topological_order(start_from=root)

        return flows

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "nodes": {
                name: {
                    "name": node.name,
                    "description": node.description,
                    "handler": node.handler,
                    "timeout": node.timeout,
                    "memory_size": node.memory_size,
                    "consumer_queue": node.consumer_queue,
                    "producer_queues": node.producer_queues,
                    "dlq_name": node.dlq_name,
                }
                for name, node in self.nodes.items()
            },
            "edges": [
                {
                    "queue_name": edge.queue_name,
                    "from_lambda": edge.from_lambda,
                    "to_lambda": edge.to_lambda,
                    "is_dlq": edge.is_dlq,
                }
                for edge in self.edges
            ],
            "dlq_map": dict(self.dlq_map),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reachable_from(start: str, adj: Dict[str, List[str]]) -> set[str]:
        """Return all nodes reachable from *start* via BFS."""
        visited: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            for child in adj.get(node, []):
                if child not in visited:
                    queue.append(child)
        return visited


# ======================================================================
# Graph builder
# ======================================================================


def build_service_graph(lambda_configs: List[LambdaConfig]) -> ServiceGraph:
    """Build a ServiceGraph from parsed Lambda configurations.

    Algorithm:
    1. Create a ``ServiceNode`` for each ``LambdaConfig``.
    2. Build a queue-name → consumer-Lambda index from all consumer queue
       entries.
    3. For each producer queue entry in each Lambda, look up the consumer
       Lambda and create a ``QueueEdge``.
    4. For each consumer queue with ``has_dlq=True``, add a DLQ mapping
       (``queue_name`` → ``queue_name-dlq``).
    5. Cross-reference ``dlq_consumer`` entries to connect DLQ queues to
       the DLQ handler Lambda.
    """
    graph = ServiceGraph()

    # Step 1: Create nodes.
    for config in lambda_configs:
        # Primary consumer queue (first consumer queue, if any).
        consumer_queue: Optional[str] = None
        if config.consumer_queues:
            consumer_queue = config.consumer_queues[0].queue_name

        # DLQ name derived from primary consumer queue with has_dlq.
        dlq_name: Optional[str] = None
        for cq in config.consumer_queues:
            if cq.has_dlq:
                dlq_name = f"{cq.queue_name}-dlq"
                break

        node = ServiceNode(
            name=config.name,
            description=config.description,
            handler=config.handler,
            timeout=config.timeout,
            memory_size=config.memory_size,
            consumer_queue=consumer_queue,
            producer_queues=[pq.queue_name for pq in config.producer_queues],
            dlq_name=dlq_name,
        )
        graph.nodes[config.name] = node

    # Step 2: Build queue-name → consumer-Lambda index.
    queue_to_consumer: Dict[str, str] = {}
    for config in lambda_configs:
        for cq in config.consumer_queues:
            queue_to_consumer[cq.queue_name] = config.name

    # Step 3: Create edges from producer → consumer matches.
    for config in lambda_configs:
        for pq in config.producer_queues:
            consumer_lambda = queue_to_consumer.get(pq.queue_name)
            if consumer_lambda is not None:
                edge = QueueEdge(
                    queue_name=pq.queue_name,
                    from_lambda=config.name,
                    to_lambda=consumer_lambda,
                    is_dlq=False,
                )
                graph.edges.append(edge)

    # Step 4: DLQ mappings from consumer queues with has_dlq=True.
    for config in lambda_configs:
        for cq in config.consumer_queues:
            if cq.has_dlq:
                dlq_queue_name = f"{cq.queue_name}-dlq"
                graph.dlq_map[cq.queue_name] = dlq_queue_name

    # Step 5: Cross-reference dlq_consumer entries to create DLQ edges.
    # Build a dlq-queue-name → handler-Lambda index.
    dlq_to_handler: Dict[str, str] = {}
    for config in lambda_configs:
        for dq in config.dlq_consumer_queues:
            dlq_to_handler[dq.queue_name] = config.name

    # For each DLQ mapping, if a handler Lambda consumes that DLQ,
    # create a DLQ edge from the primary queue's consumer Lambda to
    # the DLQ handler Lambda.
    for primary_queue, dlq_queue in graph.dlq_map.items():
        handler_lambda = dlq_to_handler.get(dlq_queue)
        if handler_lambda is not None:
            # The "from" side is the Lambda that owns the primary queue
            # (the one whose messages end up in the DLQ).
            source_lambda = queue_to_consumer.get(primary_queue)
            if source_lambda is not None:
                edge = QueueEdge(
                    queue_name=dlq_queue,
                    from_lambda=source_lambda,
                    to_lambda=handler_lambda,
                    is_dlq=True,
                )
                graph.edges.append(edge)

    return graph
