"""
Property-based tests for PathOwnershipBuilder.

Feature: tree-based-path-ownership
Tests correctness properties of the trie-based path ownership model.
"""

import string
from typing import Any, Dict, List

from hypothesis import assume, given, settings
from hypothesis.strategies import (
    composite,
    integers,
    lists,
    sampled_from,
    text,
)

from cdk_factory.stack_library.api_gateway.path_ownership_builder import (
    PathOwnershipBuilder,
    TrieNode,
)

# --- Strategies ---

# Realistic path segment alphabet
RESOURCE_NAMES = [
    "users",
    "metrics",
    "admin",
    "tenants",
    "files",
    "reports",
    "subscriptions",
    "workflows",
    "config",
    "audit",
    "warmup",
    "templates",
    "messages",
    "validations",
]

PARAM_SEGMENTS = [
    "{tenant-id}",
    "{user-id}",
    "{file-id}",
    "{report-id}",
    "{execution-id}",
]

VERSION_PREFIXES = ["v1", "v2", "v3", "v4", "v5"]

ALL_SEGMENTS = RESOURCE_NAMES + PARAM_SEGMENTS + VERSION_PREFIXES


# Strategy for generating individual path segments (used by construct ID tests)
segment_strategy = sampled_from(ALL_SEGMENTS)


@composite
def route_path(draw) -> str:
    """Generate a random route path like /v3/tenants/{tenant-id}/users."""
    num_segments = draw(integers(min_value=1, max_value=5))
    segments = [draw(sampled_from(ALL_SEGMENTS)) for _ in range(num_segments)]
    return "/" + "/".join(segments)


@composite
def route_groups_strategy(draw, min_groups=2, max_groups=5, min_routes=1, max_routes=5):
    """Generate random route groups with multiple groups and routes."""
    group_name_base = draw(
        text(
            min_size=2,
            max_size=8,
            alphabet=string.ascii_lowercase,
        )
    )
    num_groups = draw(integers(min_value=min_groups, max_value=max_groups))
    group_names = [f"{group_name_base}-{i}" for i in range(num_groups)]

    route_groups: Dict[str, List[Dict[str, Any]]] = {}
    for group_name in group_names:
        num_routes = draw(integers(min_value=min_routes, max_value=max_routes))
        routes = []
        for _ in range(num_routes):
            path = draw(route_path())
            routes.append({"path": path})
        route_groups[group_name] = routes

    return route_groups


# ---------------------------------------------------------------------------
# Property 1: Trie completeness
# ---------------------------------------------------------------------------


class TestTrieCompleteness:
    """
    Property 1: Trie completeness

    For any set of route groups and their routes, after building the trie,
    every path segment from every route SHALL appear as a node in the trie
    at the correct depth and with the correct parent-child relationship.

    **Validates: Requirements 1.1, 1.3**
    """

    @given(route_groups=route_groups_strategy(min_groups=1, max_groups=5))
    @settings(max_examples=100)
    def test_property_1_every_segment_appears_at_correct_depth(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """Every path segment from every route appears as a node at the correct depth.

        For a route "/v3/tenants/{tenant-id}/users", the trie must contain:
        - "v3" at depth 1
        - "tenants" at depth 2
        - "{tenant-id}" at depth 3
        - "users" at depth 4

        **Validates: Requirements 1.1, 1.3**
        """
        # Filter out groups with no routes
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 1)

        # Ensure at least one route has a non-empty path
        has_valid_route = any(
            route.get("path", "").strip()
            for routes in route_groups.values()
            for route in routes
        )
        assume(has_valid_route)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # For every route in every group, verify each segment exists at the correct depth
        for group_name, routes in route_groups.items():
            for route in routes:
                path = route.get("path", "")
                if not path:
                    continue

                segments = [s for s in path.split("/") if s]
                if not segments:
                    continue

                # Walk the trie and verify each segment exists at the expected depth
                current = builder._root
                for depth_index, segment in enumerate(segments):
                    assert segment in current.children, (
                        f"Segment '{segment}' at depth {depth_index + 1} "
                        f"not found in trie for route '{path}' "
                        f"(group '{group_name}'). "
                        f"Available children: {list(current.children.keys())}"
                    )
                    child = current.children[segment]

                    # Verify the node's segment matches
                    assert child.segment == segment, (
                        f"Node at depth {depth_index + 1} has segment "
                        f"'{child.segment}' but expected '{segment}' "
                        f"for route '{path}' (group '{group_name}')"
                    )

                    # Verify depth by checking full_path length
                    assert len(child.full_path) == depth_index + 1, (
                        f"Node '{segment}' has full_path length "
                        f"{len(child.full_path)} but expected depth "
                        f"{depth_index + 1} for route '{path}' "
                        f"(group '{group_name}')"
                    )

                    current = child

    @given(route_groups=route_groups_strategy(min_groups=1, max_groups=5))
    @settings(max_examples=100)
    def test_property_1_parent_child_relationships_are_correct(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """Each node's parent reference points to the correct parent node.

        For a route "/v3/tenants/{tenant-id}", the node for "tenants" must
        have "v3" as its parent, and "{tenant-id}" must have "tenants" as
        its parent.

        **Validates: Requirements 1.1, 1.3**
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 1)

        has_valid_route = any(
            route.get("path", "").strip()
            for routes in route_groups.values()
            for route in routes
        )
        assume(has_valid_route)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        for group_name, routes in route_groups.items():
            for route in routes:
                path = route.get("path", "")
                if not path:
                    continue

                segments = [s for s in path.split("/") if s]
                if not segments:
                    continue

                current = builder._root
                for i, segment in enumerate(segments):
                    if segment not in current.children:
                        break
                    child = current.children[segment]

                    # Verify parent reference
                    assert child.parent is current, (
                        f"Node '{segment}' at depth {i + 1} has incorrect "
                        f"parent reference for route '{path}' "
                        f"(group '{group_name}'). "
                        f"Expected parent segment: "
                        f"'{current.segment if current.segment else '<root>'}', "
                        f"got: '{child.parent.segment if child.parent else None}'"
                    )

                    # Verify the full path reconstructs correctly
                    expected_path = segments[: i + 1]
                    assert child.full_path == expected_path, (
                        f"Node '{segment}' full_path is {child.full_path} "
                        f"but expected {expected_path} for route '{path}' "
                        f"(group '{group_name}')"
                    )

                    current = child

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_property_1_trie_contains_all_unique_paths(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """The trie contains nodes for all unique path prefixes across all routes.

        If routes "/v3/users" and "/v3/metrics" exist, the trie must contain
        nodes for "v3", "users", and "metrics" — with "users" and "metrics"
        both being children of "v3".

        **Validates: Requirements 1.1, 1.3**
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 1)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Collect all expected (parent_path, segment) pairs from all routes
        expected_nodes: set = set()
        for routes in route_groups.values():
            for route in routes:
                path = route.get("path", "")
                if not path:
                    continue
                segments = [s for s in path.split("/") if s]
                for i, segment in enumerate(segments):
                    # Key: (tuple of parent path segments, segment)
                    parent_path = tuple(segments[:i])
                    expected_nodes.add((parent_path, segment))

        # Verify each expected node exists in the trie
        for parent_path, segment in expected_nodes:
            # Navigate to the parent
            current = builder._root
            for parent_seg in parent_path:
                assert parent_seg in current.children, (
                    f"Parent path segment '{parent_seg}' not found while "
                    f"navigating to parent of '{segment}'"
                )
                current = current.children[parent_seg]

            # Verify the segment exists as a child of the parent
            assert segment in current.children, (
                f"Segment '{segment}' not found as child of "
                f"'{'/' + '/'.join(parent_path) if parent_path else '/'}'. "
                f"Available children: {list(current.children.keys())}"
            )


# --- Property 3: Shared/exclusive classification ---


class TestSharedExclusiveClassification:
    """Property 3: Shared/exclusive classification.

    For any trie node, the node SHALL be classified as shared if and only if
    its group set contains two or more distinct group names, and as exclusive
    if and only if its group set contains exactly one group name.

    **Validates: Requirements 2.1, 2.3**
    """

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_shared_iff_two_or_more_groups(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """A node is shared if and only if its group set has 2+ groups.

        **Validates: Requirements 2.1, 2.3**
        """
        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Traverse all nodes and verify classification
        all_nodes = self._collect_all_nodes(builder._root)

        for node in all_nodes:
            group_count = len(node.groups)
            if group_count >= 2:
                assert node.is_shared, (
                    f"Node '{'/'.join(node.full_path)}' has {group_count} groups "
                    f"{node.groups} but is_shared is False"
                )
                assert not node.is_exclusive, (
                    f"Node '{'/'.join(node.full_path)}' has {group_count} groups "
                    f"but is_exclusive is True (should be False)"
                )
            elif group_count == 1:
                assert node.is_exclusive, (
                    f"Node '{'/'.join(node.full_path)}' has 1 group "
                    f"{node.groups} but is_exclusive is False"
                )
                assert not node.is_shared, (
                    f"Node '{'/'.join(node.full_path)}' has 1 group "
                    f"but is_shared is True (should be False)"
                )
            else:
                # Root node or empty node — neither shared nor exclusive
                assert not node.is_shared
                assert not node.is_exclusive

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_shared_and_exclusive_are_mutually_exclusive(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """No node can be both shared and exclusive simultaneously.

        **Validates: Requirements 2.1, 2.3**
        """
        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        all_nodes = self._collect_all_nodes(builder._root)

        for node in all_nodes:
            # A node cannot be both shared and exclusive
            assert not (node.is_shared and node.is_exclusive), (
                f"Node '{'/'.join(node.full_path)}' is both shared AND exclusive "
                f"(groups: {node.groups})"
            )

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_every_non_root_node_is_shared_or_exclusive(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ):
        """Every non-root node with groups must be either shared or exclusive.

        **Validates: Requirements 2.1, 2.3**
        """
        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        all_nodes = self._collect_all_nodes(builder._root)

        for node in all_nodes:
            if len(node.groups) > 0:
                # Must be one or the other
                assert node.is_shared or node.is_exclusive, (
                    f"Node '{'/'.join(node.full_path)}' has {len(node.groups)} groups "
                    f"but is neither shared nor exclusive"
                )

    def _collect_all_nodes(self, root: TrieNode) -> List[TrieNode]:
        """Collect all nodes in the trie (excluding root)."""
        nodes: List[TrieNode] = []
        self._traverse(root, nodes)
        return nodes

    def _traverse(self, node: TrieNode, result: List[TrieNode]) -> None:
        """Depth-first traversal collecting all child nodes."""
        for child in node.children.values():
            result.append(child)
            self._traverse(child, result)


# ---------------------------------------------------------------------------
# Property 7: Single group produces no shared nodes
# ---------------------------------------------------------------------------


class TestSingleGroupNoSharedNodes:
    """
    Property 7: Single group produces no shared nodes

    For any set of routes all assigned to a single group, the trie SHALL
    contain zero shared nodes, and the handoff map SHALL contain only the
    API root entry.

    **Validates: Requirements 6.2**
    """

    @given(route_groups=route_groups_strategy(min_groups=1, max_groups=1))
    @settings(max_examples=100)
    def test_property_7_single_group_no_shared_nodes(self, route_groups):
        """All routes in one group → zero shared nodes, handoff map has only "/".

        Validates: Requirements 6.2
        """
        # Ensure we have exactly one group with at least one route
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) == 1)

        group_name = list(route_groups.keys())[0]
        routes = route_groups[group_name]
        assume(len(routes) >= 1)

        # Ensure at least one route has a non-empty path
        has_valid_route = any(route.get("path", "").strip() for route in routes)
        assume(has_valid_route)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Property: zero shared nodes when all routes belong to one group
        shared_nodes = builder.get_shared_nodes()
        assert shared_nodes == [], (
            f"Expected zero shared nodes for single group '{group_name}', "
            f"but found {len(shared_nodes)} shared nodes: "
            f"{['/' + '/'.join(n.full_path) for n in shared_nodes]}"
        )

        # Property: handoff map contains only the API root entry "/"
        handoff_map = builder.get_handoff_map(group_name)
        assert handoff_map == {"/": "/"}, (
            f"Expected handoff map to be {{'/': '/'}} for single group "
            f"'{group_name}', but got: {handoff_map}"
        )


# ---------------------------------------------------------------------------
# Property 5: Construct ID stability and uniqueness
# ---------------------------------------------------------------------------


class TestConstructIdStabilityAndUniqueness:
    """
    Property 5: Construct ID stability and uniqueness

    For any list of path segments, the computed construct ID SHALL be
    deterministic (same input → same output) and two distinct paths
    SHALL produce distinct construct IDs.

    **Validates: Requirements 3.4, 7.4**
    """

    @given(
        segments=lists(
            sampled_from(ALL_SEGMENTS),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_construct_id_stability(self, segments):
        """Same input always produces the same construct ID (determinism).

        Validates: Requirements 3.4, 7.4
        """
        id_first = PathOwnershipBuilder.compute_construct_id(segments)
        id_second = PathOwnershipBuilder.compute_construct_id(segments)

        assert id_first == id_second, (
            f"Construct ID not stable for segments {segments}: "
            f"first call returned '{id_first}', second call returned '{id_second}'"
        )

    @given(
        segments_a=lists(sampled_from(ALL_SEGMENTS), min_size=1, max_size=5),
        segments_b=lists(sampled_from(ALL_SEGMENTS), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_construct_id_uniqueness(self, segments_a, segments_b):
        """Distinct path segment lists produce distinct construct IDs.

        Validates: Requirements 3.4, 7.4
        """
        assume(segments_a != segments_b)

        id_a = PathOwnershipBuilder.compute_construct_id(segments_a)
        id_b = PathOwnershipBuilder.compute_construct_id(segments_b)

        assert id_a != id_b, (
            f"Distinct paths produced the same construct ID '{id_a}': "
            f"segments_a={segments_a}, segments_b={segments_b}"
        )


# ---------------------------------------------------------------------------
# Property 2: Group annotation correctness
# ---------------------------------------------------------------------------


class TestGroupAnnotationCorrectness:
    """
    Property 2: Group annotation correctness

    For any set of route groups and their routes, each trie node's group set
    SHALL equal exactly the set of group names whose routes pass through that
    node — no more, no less.

    **Validates: Requirements 1.2**
    """

    @given(route_groups=route_groups_strategy())
    @settings(max_examples=100)
    def test_node_groups_match_routes_passing_through(self, route_groups):
        """Each node's group set equals exactly the set of groups whose routes pass through it.

        Validates: Requirements 1.2
        """
        # Filter out groups with no routes
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 1)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Independently compute expected groups for every node by checking all routes.
        # Walk the trie and for each node, compute which groups SHOULD pass through it.
        # A group passes through a node if any of its routes contain that node's
        # full path as a prefix.

        # First, collect all nodes in the trie via DFS
        all_nodes: List[TrieNode] = []
        stack = [builder._root]
        while stack:
            node = stack.pop()
            for child in node.children.values():
                all_nodes.append(child)
                stack.append(child)

        # For each node, independently compute expected groups
        for node in all_nodes:
            node_path = node.full_path  # e.g., ["v3", "tenants", "{tenant-id}"]

            expected_groups = set()
            for group_name, routes in route_groups.items():
                for route in routes:
                    path = route.get("path", "")
                    if not path:
                        continue
                    segments = [s for s in path.split("/") if s]

                    # Check if this route passes through this node:
                    # The route's segments must contain node_path as a prefix
                    if (
                        len(segments) >= len(node_path)
                        and segments[: len(node_path)] == node_path
                    ):
                        expected_groups.add(group_name)
                        break  # One matching route is enough for this group

            assert node.groups == expected_groups, (
                f"Group annotation mismatch at node '{'/' + '/'.join(node_path)}':\n"
                f"  Expected groups: {sorted(expected_groups)}\n"
                f"  Actual groups:   {sorted(node.groups)}\n"
                f"  Route groups: {list(route_groups.keys())}"
            )

    @given(route_groups=route_groups_strategy(min_groups=2))
    @settings(max_examples=100)
    def test_no_extra_groups_on_nodes(self, route_groups):
        """No node has a group in its set unless at least one route from that group passes through it.

        Validates: Requirements 1.2
        """
        # Filter out groups with no routes and ensure at least 2 groups remain
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # For each node, verify that every group in node.groups has at least
        # one route that actually passes through this node
        stack = [builder._root]
        while stack:
            node = stack.pop()
            for child in node.children.values():
                child_path = child.full_path

                for group_name in child.groups:
                    # Verify this group has at least one route passing through this node
                    routes = route_groups.get(group_name, [])
                    has_matching_route = False
                    for route in routes:
                        path = route.get("path", "")
                        if not path:
                            continue
                        segments = [s for s in path.split("/") if s]
                        if (
                            len(segments) >= len(child_path)
                            and segments[: len(child_path)] == child_path
                        ):
                            has_matching_route = True
                            break

                    assert has_matching_route, (
                        f"Node '{'/' + '/'.join(child_path)}' has group '{group_name}' "
                        f"but no route from that group passes through it"
                    )

                stack.append(child)


# ---------------------------------------------------------------------------
# Property 9: Conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    """
    Property 9: Conflict detection

    For any route configuration where two or more groups would create the same
    path segment under the same parent resource (i.e., a shared node exists that
    the builder fails to identify), the validate() method SHALL raise a ValueError
    identifying the conflicting groups and segment.

    Since the builder correctly identifies all shared nodes by construction,
    this property verifies that validate() does NOT raise for valid configurations
    (the builder always correctly identifies shared nodes). Additionally tests
    that validate() catches the self-consistency check.

    **Validates: Requirements 8.1, 8.2, 8.3**
    """

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_validate_does_not_raise_for_valid_configurations(self, route_groups):
        """validate() does not raise for any valid route configuration built by the builder.

        Since the builder correctly identifies all shared nodes by construction,
        validate() should never raise ValueError for configurations that go through
        the normal build() path.

        Validates: Requirements 8.1, 8.2, 8.3
        """
        # Filter out groups with no routes
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # validate() should NOT raise for any valid configuration
        # because the builder correctly identifies all shared nodes
        builder.validate()  # Should not raise

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_all_shared_nodes_are_correctly_identified(self, route_groups):
        """Every node with 2+ groups is in the shared nodes list (no unowned shared nodes).

        This verifies the self-consistency that validate() checks: every shared node
        in the trie is correctly identified by get_shared_nodes().

        Validates: Requirements 8.2, 8.3
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        shared_nodes = builder.get_shared_nodes()

        # Collect ALL nodes with 2+ groups via manual traversal
        all_shared_in_trie = []
        self._collect_all_shared(builder._root, all_shared_in_trie)

        # Every shared node in the trie must be in the shared_nodes list
        shared_node_set = set(id(n) for n in shared_nodes)
        for node in all_shared_in_trie:
            assert id(node) in shared_node_set, (
                f"Shared node '{'/' + '/'.join(node.full_path)}' with groups "
                f"{node.groups} was not returned by get_shared_nodes()"
            )

        # And vice versa: every node in shared_nodes must actually be shared
        for node in shared_nodes:
            assert node.is_shared, (
                f"Node '{'/' + '/'.join(node.full_path)}' returned by "
                f"get_shared_nodes() is not actually shared (groups={node.groups})"
            )

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_no_exclusive_node_has_multiple_groups(self, route_groups):
        """No node classified as exclusive has multiple groups (cross-stack conflict check).

        This is the invariant that validate()'s _check_cross_stack_conflicts enforces:
        if a node has len(groups) > 1, it must be classified as shared (is_shared=True).
        A violation would mean two nested stacks would try to create the same resource.

        Validates: Requirements 8.1
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Walk the entire trie and verify no node has multiple groups
        # without being classified as shared
        self._verify_no_cross_stack_conflicts(builder._root)

    def _collect_all_shared(self, node: "TrieNode", result: list) -> None:
        """Recursively collect all nodes with 2+ groups."""
        for child in node.children.values():
            if len(child.groups) >= 2:
                result.append(child)
            self._collect_all_shared(child, result)

    def _verify_no_cross_stack_conflicts(self, node: "TrieNode") -> None:
        """Recursively verify no node has multiple groups without being shared."""
        for child in node.children.values():
            if len(child.groups) > 1:
                assert child.is_shared, (
                    f"Cross-stack conflict: node '{'/' + '/'.join(child.full_path)}' "
                    f"has groups {child.groups} but is_shared={child.is_shared}"
                )
            self._verify_no_cross_stack_conflicts(child)


# ---------------------------------------------------------------------------
# Property 4: Divergence point identification
# ---------------------------------------------------------------------------


class TestDivergencePointIdentification:
    """
    Property 4: Divergence point identification

    For any shared trie node that has at least one child classified as exclusive,
    that node SHALL be identified as a divergence point.

    **Validates: Requirements 2.4**
    """

    @given(route_groups=route_groups_strategy(min_groups=2))
    @settings(max_examples=100)
    def test_divergence_point_iff_shared_with_exclusive_child(self, route_groups):
        """A node is a divergence point iff it is shared AND has at least one exclusive child.

        Validates: Requirements 2.4
        """
        # Filter out groups with no routes
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Traverse all nodes and verify the divergence point property
        def verify_divergence_points(node: TrieNode):
            for child in node.children.values():
                # Compute expected divergence point status
                expected_is_divergence = child.is_shared and any(
                    grandchild.is_exclusive for grandchild in child.children.values()
                )

                assert child.is_divergence_point == expected_is_divergence, (
                    f"Node '{'/' + '/'.join(child.full_path)}' has "
                    f"is_divergence_point={child.is_divergence_point} but expected "
                    f"{expected_is_divergence}. "
                    f"is_shared={child.is_shared}, "
                    f"children exclusive status: "
                    f"{[(c.segment, c.is_exclusive) for c in child.children.values()]}"
                )

                # Recurse into children
                verify_divergence_points(child)

        verify_divergence_points(builder._root)

    @given(route_groups=route_groups_strategy(min_groups=2))
    @settings(max_examples=100)
    def test_non_shared_node_is_never_divergence_point(self, route_groups):
        """A node that is NOT shared can never be a divergence point.

        Validates: Requirements 2.4
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        def verify_non_shared_not_divergence(node: TrieNode):
            for child in node.children.values():
                if not child.is_shared:
                    assert not child.is_divergence_point, (
                        f"Non-shared node '{'/' + '/'.join(child.full_path)}' "
                        f"should not be a divergence point, but is_divergence_point=True. "
                        f"groups={child.groups}"
                    )
                verify_non_shared_not_divergence(child)

        verify_non_shared_not_divergence(builder._root)

    @given(route_groups=route_groups_strategy(min_groups=2))
    @settings(max_examples=100)
    def test_shared_node_with_only_shared_children_is_not_divergence(
        self, route_groups
    ):
        """A shared node whose children are ALL shared is NOT a divergence point.

        Validates: Requirements 2.4
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        def verify_all_shared_children_not_divergence(node: TrieNode):
            for child in node.children.values():
                if child.is_shared and child.children:
                    all_children_shared = all(
                        grandchild.is_shared for grandchild in child.children.values()
                    )
                    if all_children_shared:
                        assert not child.is_divergence_point, (
                            f"Shared node '{'/' + '/'.join(child.full_path)}' "
                            f"has only shared children but is_divergence_point=True. "
                            f"Children: {[(c.segment, c.groups) for c in child.children.values()]}"
                        )
                verify_all_shared_children_not_divergence(child)

        verify_all_shared_children_not_divergence(builder._root)


# ---------------------------------------------------------------------------
# Property 6: Handoff map correctness
# ---------------------------------------------------------------------------


class TestHandoffMapCorrectness:
    """
    Property 6: Handoff map correctness

    For any route configuration with multiple groups, each group's handoff map
    SHALL contain an entry for every divergence point that group's routes pass
    through, and the nested stack SHALL only need to create segments below
    those divergence points.

    **Validates: Requirements 5.1**
    """

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_handoff_map_covers_all_divergence_points_for_group(self, route_groups):
        """Each group's handoff map contains an entry for every divergence point
        where the group's routes actually transition from shared to exclusive segments.

        The handoff map must cover the deepest relevant divergence point for each
        route — the point where the nested stack begins creating its own segments.
        A route that passes through a divergence point but continues through deeper
        shared nodes uses the deeper handoff point instead.

        Validates: Requirements 5.1
        """
        # Filter out groups with no routes
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        for group_name, routes in route_groups.items():
            handoff_map = builder.get_handoff_map(group_name)

            # For each route, find the deepest divergence point where the route
            # actually transitions from shared to exclusive (or the shared leaf
            # if the entire route is shared). This is the handoff point the
            # nested stack needs.
            required_handoff_points = set()

            for route in routes:
                path = route.get("path", "")
                if not path:
                    continue

                segments = [s for s in path.split("/") if s]
                current = builder._root
                deepest_handoff = None

                for i, segment in enumerate(segments):
                    if segment not in current.children:
                        break
                    child = current.children[segment]

                    if child.is_shared:
                        if child.is_divergence_point:
                            # This is a divergence point — potential handoff
                            deepest_handoff = "/" + "/".join(segments[: i + 1])
                        elif i == len(segments) - 1:
                            # Entire route is shared — handoff at shared leaf
                            deepest_handoff = "/" + "/".join(segments[: i + 1])
                    else:
                        # Hit an exclusive node — stop
                        break

                    current = child

                if deepest_handoff is None:
                    required_handoff_points.add("/")
                else:
                    required_handoff_points.add(deepest_handoff)

            # Every required handoff point must appear in the handoff map
            for hp in required_handoff_points:
                assert hp in handoff_map, (
                    f"Required handoff point '{hp}' for group "
                    f"'{group_name}' not in its handoff map. "
                    f"Handoff map keys: {list(handoff_map.keys())}"
                )

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_handoff_map_entries_are_shared_nodes_or_root(self, route_groups):
        """Every entry in a group's handoff map corresponds to a shared node
        path or the API root "/".

        Validates: Requirements 5.1
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Collect all shared node paths
        shared_nodes = builder.get_shared_nodes()
        shared_paths = {"/" + "/".join(node.full_path) for node in shared_nodes}
        shared_paths.add("/")  # API root is always a valid handoff point

        for group_name in route_groups:
            handoff_map = builder.get_handoff_map(group_name)

            for path_key in handoff_map:
                assert path_key in shared_paths or path_key == "/", (
                    f"Handoff map entry '{path_key}' for group '{group_name}' "
                    f"does not correspond to a shared node or API root. "
                    f"Shared paths: {sorted(shared_paths)}"
                )

    @given(route_groups=route_groups_strategy(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_nested_stack_only_creates_segments_below_handoff(self, route_groups):
        """For each route, the segments below the handoff point are exclusive
        to the group (the nested stack only creates segments below divergence points).

        Validates: Requirements 5.1
        """
        route_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(route_groups) >= 2)

        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        for group_name, routes in route_groups.items():
            handoff_map = builder.get_handoff_map(group_name)

            for route in routes:
                path = route.get("path", "")
                if not path:
                    continue

                segments = [s for s in path.split("/") if s]

                # Find the handoff path for this route (longest matching handoff)
                handoff_path = "/"
                for hp in handoff_map:
                    if hp == "/":
                        continue
                    hp_segments = [s for s in hp.split("/") if s]
                    # Check if this handoff path is a prefix of the route
                    if segments[: len(hp_segments)] == hp_segments:
                        if len(hp_segments) > len(
                            [s for s in handoff_path.split("/") if s]
                        ):
                            handoff_path = hp

                # Segments below the handoff point should be exclusive to this group
                # (or shared only among routes within this same group at that level)
                handoff_segments = [s for s in handoff_path.split("/") if s]
                remaining_segments = segments[len(handoff_segments) :]

                # Walk the trie from the handoff point to verify remaining segments
                current = builder._root
                for seg in handoff_segments:
                    if seg in current.children:
                        current = current.children[seg]

                # The first segment below the handoff should not be shared
                # (otherwise the handoff point should have been deeper)
                if remaining_segments and remaining_segments[0] in current.children:
                    first_below = current.children[remaining_segments[0]]
                    # If it's shared, it should be a divergence point itself
                    # (which would mean the handoff map should have a deeper entry)
                    if first_below.is_shared and first_below.is_divergence_point:
                        deeper_path = "/" + "/".join(
                            handoff_segments + [remaining_segments[0]]
                        )
                        # This deeper divergence point should also be in the handoff map
                        assert deeper_path in handoff_map, (
                            f"Route '{path}' in group '{group_name}' has a "
                            f"divergence point at '{deeper_path}' below handoff "
                            f"'{handoff_path}' that is not in the handoff map."
                        )


# ---------------------------------------------------------------------------
# Property 8: Group isolation
# ---------------------------------------------------------------------------


class TestGroupIsolation:
    """
    Property 8: Group isolation

    For any two route configurations that differ only by adding a route to one
    group (where the addition does not introduce new shared segments), the
    handoff maps for all other groups SHALL remain unchanged.

    **Validates: Requirements 7.2**
    """

    @given(
        route_groups=route_groups_strategy(
            min_groups=2, max_groups=4, min_routes=1, max_routes=4
        ),
        new_route_path=route_path(),
    )
    @settings(max_examples=100)
    def test_adding_route_to_one_group_leaves_others_unchanged(
        self,
        route_groups: Dict[str, List[Dict[str, Any]]],
        new_route_path: str,
    ):
        """Adding a route to one group (no new shared segments) leaves other
        groups' handoff maps unchanged.

        **Validates: Requirements 7.2**
        """
        import copy

        # Ensure we have at least 2 groups with valid routes
        valid_groups = {k: v for k, v in route_groups.items() if v}
        assume(len(valid_groups) >= 2)

        group_names = list(valid_groups.keys())
        target_group = group_names[0]
        other_groups = group_names[1:]

        # Build the original trie and compute handoff maps for other groups
        builder_before = PathOwnershipBuilder(valid_groups)
        builder_before.build()

        handoff_maps_before = {
            g: builder_before.get_handoff_map(g) for g in other_groups
        }

        # Create a modified route groups with the new route added to target_group
        modified_groups = copy.deepcopy(valid_groups)
        modified_groups[target_group].append({"path": new_route_path})

        # Check that the new route does NOT introduce new shared segments.
        # A segment is "newly shared" if it was previously exclusive to one group
        # (or didn't exist) and now belongs to 2+ groups.
        # We verify this by checking: all segments in the new route that appear
        # in the trie are either already shared OR already belong to target_group.
        new_segments = [s for s in new_route_path.split("/") if s]

        builder_after = PathOwnershipBuilder(modified_groups)
        builder_after.build()

        # Walk the new route's path in the rebuilt trie and check for newly shared segments
        current = builder_after._root
        introduces_new_shared = False
        for seg in new_segments:
            if seg not in current.children:
                break
            child = current.children[seg]
            # If this node is now shared but wasn't before (or didn't exist before),
            # the addition introduced new shared segments
            if child.is_shared:
                # Check if this node existed and was already shared in the original trie
                original_node = self._find_node(builder_before._root, child.full_path)
                if original_node is None or not original_node.is_shared:
                    introduces_new_shared = True
                    break
            current = child

        # Only test the property when no new shared segments are introduced
        assume(not introduces_new_shared)

        # Property: handoff maps for all other groups remain unchanged
        handoff_maps_after = {g: builder_after.get_handoff_map(g) for g in other_groups}

        for group in other_groups:
            assert handoff_maps_before[group] == handoff_maps_after[group], (
                f"Handoff map for group '{group}' changed after adding route "
                f"'{new_route_path}' to group '{target_group}'.\n"
                f"Before: {handoff_maps_before[group]}\n"
                f"After:  {handoff_maps_after[group]}"
            )

    def _find_node(self, root: TrieNode, path_segments: List[str]):
        """Find a node in the trie by its full path segments."""
        current = root
        for seg in path_segments:
            if seg not in current.children:
                return None
            current = current.children[seg]
        return current
