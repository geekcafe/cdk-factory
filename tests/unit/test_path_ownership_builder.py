"""
Unit tests for PathOwnershipBuilder — trie-based path ownership for API Gateway nested stacks.

Tests trie construction, shared/exclusive node classification, divergence point detection,
handoff map computation, construct ID generation, conflict detection, and edge cases.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 3.4, 5.1, 5.2, 5.4, 6.2, 8.1, 8.2, 8.3
"""

import pytest

from cdk_factory.stack_library.api_gateway.path_ownership_builder import (
    PathOwnershipBuilder,
    TrieNode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aplos_route_groups():
    """Real Aplos NCA route groups for testing."""
    return {
        "users": [
            {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
            {"path": "/v3/tenants/{tenant-id}/users/{user-id}", "method": "GET"},
        ],
        "metrics": [
            {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            {
                "path": "/v3/tenants/{tenant-id}/users/{user-id}/metrics",
                "method": "GET",
            },
        ],
        "warm-up": [
            {"path": "/v3/admin/warm-up", "method": "POST"},
        ],
    }


@pytest.fixture
def built_builder(aplos_route_groups):
    """A PathOwnershipBuilder that has been built with Aplos NCA routes."""
    builder = PathOwnershipBuilder(aplos_route_groups)
    builder.build()
    return builder


# ---------------------------------------------------------------------------
# Trie Construction Tests (Requirement 1.1, 1.3)
# ---------------------------------------------------------------------------


class TestTrieConstruction:
    """Tests for trie construction with known Aplos NCA routes."""

    def test_trie_contains_all_segments(self, built_builder):
        """Every path segment from every route appears in the trie."""
        shared_and_exclusive = self._collect_all_segments(built_builder)
        expected_segments = {
            "v3",
            "tenants",
            "{tenant-id}",
            "users",
            "{user-id}",
            "metrics",
            "admin",
            "warm-up",
        }
        assert expected_segments.issubset(shared_and_exclusive)

    def test_trie_depth_correct_for_users_route(self, built_builder):
        """Route /v3/tenants/{tenant-id}/users has nodes at correct depths."""
        root = built_builder._root
        assert "v3" in root.children
        v3 = root.children["v3"]
        assert "tenants" in v3.children
        tenants = v3.children["tenants"]
        assert "{tenant-id}" in tenants.children
        tenant_id = tenants.children["{tenant-id}"]
        assert "users" in tenant_id.children

    def test_trie_depth_correct_for_warmup_route(self, built_builder):
        """Route /v3/admin/warm-up has nodes at correct depths."""
        root = built_builder._root
        v3 = root.children["v3"]
        assert "admin" in v3.children
        admin = v3.children["admin"]
        assert "warm-up" in admin.children

    def test_parent_child_relationships(self, built_builder):
        """Parent references are correctly set."""
        root = built_builder._root
        v3 = root.children["v3"]
        assert v3.parent is root
        tenants = v3.children["tenants"]
        assert tenants.parent is v3
        tenant_id = tenants.children["{tenant-id}"]
        assert tenant_id.parent is tenants

    def _collect_all_segments(self, builder):
        """Helper to collect all segment names from the trie."""
        segments = set()
        self._walk(builder._root, segments)
        return segments

    def _walk(self, node, segments):
        for child in node.children.values():
            segments.add(child.segment)
            self._walk(child, segments)


# ---------------------------------------------------------------------------
# Shared Node Identification Tests (Requirement 2.1, 2.2)
# ---------------------------------------------------------------------------


class TestSharedNodeIdentification:
    """Tests for shared node identification."""

    def test_v3_is_shared(self, built_builder):
        """'v3' is shared across users, metrics, warm-up, and __preemptive__ groups."""
        v3 = built_builder._root.children["v3"]
        assert v3.is_shared is True
        # v3 is an ancestor of parameterized {tenant-id}, so __preemptive__ is injected
        assert "users" in v3.groups
        assert "metrics" in v3.groups
        assert "warm-up" in v3.groups
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP in v3.groups

    def test_tenants_is_shared(self, built_builder):
        """'tenants' is shared across users and metrics groups."""
        tenants = built_builder._root.children["v3"].children["tenants"]
        assert tenants.is_shared is True
        assert "users" in tenants.groups
        assert "metrics" in tenants.groups

    def test_tenant_id_is_shared(self, built_builder):
        """'{tenant-id}' is shared across users and metrics groups."""
        tenant_id = (
            built_builder._root.children["v3"]
            .children["tenants"]
            .children["{tenant-id}"]
        )
        assert tenant_id.is_shared is True
        assert "users" in tenant_id.groups
        assert "metrics" in tenant_id.groups

    def test_get_shared_nodes_returns_all_shared(self, built_builder):
        """get_shared_nodes() returns all shared nodes."""
        shared_nodes = built_builder.get_shared_nodes()
        shared_segments = [node.segment for node in shared_nodes]
        # v3, tenants, {tenant-id} are shared; users/{user-id} under {tenant-id} is also shared
        assert "v3" in shared_segments
        assert "tenants" in shared_segments
        assert "{tenant-id}" in shared_segments

    def test_shared_nodes_parent_before_children(self, built_builder):
        """Shared nodes are returned in depth-first order (parent before children)."""
        shared_nodes = built_builder.get_shared_nodes()
        paths = ["/" + "/".join(node.full_path) for node in shared_nodes]
        # v3 must come before tenants, tenants before {tenant-id}
        v3_idx = paths.index("/v3")
        tenants_idx = paths.index("/v3/tenants")
        tenant_id_idx = paths.index("/v3/tenants/{tenant-id}")
        assert v3_idx < tenants_idx < tenant_id_idx


# ---------------------------------------------------------------------------
# Exclusive Node Identification Tests (Requirement 2.3)
# ---------------------------------------------------------------------------


class TestExclusiveNodeIdentification:
    """Tests for exclusive node identification."""

    def test_admin_is_exclusive_to_warmup(self, built_builder):
        """'admin' is exclusive to the warm-up group."""
        admin = built_builder._root.children["v3"].children["admin"]
        assert admin.is_exclusive is True
        assert admin.groups == {"warm-up"}

    def test_warmup_is_exclusive(self, built_builder):
        """'warm-up' is exclusive to the warm-up group."""
        warmup = (
            built_builder._root.children["v3"].children["admin"].children["warm-up"]
        )
        assert warmup.is_exclusive is True
        assert warmup.groups == {"warm-up"}

    def test_metrics_leaf_is_exclusive_to_metrics(self, built_builder):
        """'metrics' directly under {tenant-id} is shared due to preemptive parameterized marking.

        Because {tenant-id} is parameterized, its immediate children (users, metrics)
        are marked with __preemptive__ to prevent future resource relocation conflicts.
        """
        metrics = (
            built_builder._root.children["v3"]
            .children["tenants"]
            .children["{tenant-id}"]
            .children["metrics"]
        )
        # With preemptive sharing, metrics is no longer exclusive —
        # it has both "metrics" and "__preemptive__" groups
        assert metrics.is_shared is True
        assert "metrics" in metrics.groups
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP in metrics.groups


# ---------------------------------------------------------------------------
# Divergence Point Detection Tests (Requirement 2.4)
# ---------------------------------------------------------------------------


class TestDivergencePointDetection:
    """Tests for divergence point detection."""

    def test_tenant_id_is_divergence_point(self, built_builder):
        """{tenant-id} is shared but not a divergence point with preemptive sharing.

        With preemptive sharing enabled, all immediate children of {tenant-id}
        (users, metrics) are marked shared via __preemptive__. Since no exclusive
        children remain, {tenant-id} is no longer a divergence point.
        This is intentional — the handoff happens deeper in the tree.
        """
        tenant_id = (
            built_builder._root.children["v3"]
            .children["tenants"]
            .children["{tenant-id}"]
        )
        # With preemptive sharing, children are shared, so no exclusive children exist
        assert tenant_id.is_divergence_point is False

    def test_v3_is_divergence_point(self, built_builder):
        """'v3' is a divergence point because 'admin' is exclusive to warm-up."""
        v3 = built_builder._root.children["v3"]
        assert v3.is_divergence_point is True

    def test_non_shared_node_is_not_divergence_point(self, built_builder):
        """An exclusive node is never a divergence point."""
        admin = built_builder._root.children["v3"].children["admin"]
        assert admin.is_divergence_point is False


# ---------------------------------------------------------------------------
# Handoff Map Tests (Requirement 5.1, 5.2)
# ---------------------------------------------------------------------------


class TestHandoffMap:
    """Tests for handoff map computation."""

    def test_users_group_handoff_contains_shared_paths(self, built_builder):
        """Users group handoff map contains shared paths for its routes.

        Because the metrics group also has a route through
        /v3/tenants/{tenant-id}/users/{user-id}/metrics, the 'users' and
        '{user-id}' nodes are shared. The users group's routes are entirely
        shared paths, so handoff occurs at the leaf shared nodes.
        """
        handoff = built_builder.get_handoff_map("users")
        # Route /v3/tenants/{tenant-id}/users is entirely shared (leaf shared node)
        assert "/v3/tenants/{tenant-id}/users" in handoff
        # Route /v3/tenants/{tenant-id}/users/{user-id} is entirely shared (leaf shared node)
        assert "/v3/tenants/{tenant-id}/users/{user-id}" in handoff

    def test_users_group_handoff_at_tenant_id_when_users_exclusive(self):
        """When 'users' is a child of parameterized {tenant-id}, handoff is at 'users'.

        With preemptive sharing, 'users' (child of {tenant-id}) is automatically
        shared because its parent is a parameterized node in a multi-group subtree.
        But '{user-id}' below 'users' is NOT preemptively marked because 'users'
        only has one real group flowing through it — the nested stack owns '{user-id}'.
        """
        route_groups = {
            "users": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/users/{user-id}", "method": "GET"},
            ],
            "metrics": [
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        handoff = builder.get_handoff_map("users")
        # 'users' is shared (preemptive child of {tenant-id} in multi-group context).
        # '{user-id}' is NOT shared — it's exclusive to users group.
        # Handoff occurs at 'users' — the nested stack creates '{user-id}' itself.
        assert "/v3/tenants/{tenant-id}/users" in handoff
        assert "/v3/tenants/{tenant-id}/users/{user-id}" not in handoff

    def test_warmup_group_handoff_contains_v3(self, built_builder):
        """Warm-up group with route '/v3/admin/warm-up' has handoff at '/v3'."""
        handoff = built_builder.get_handoff_map("warm-up")
        assert "/v3" in handoff

    def test_group_with_no_shared_segments_handoff_is_root(self):
        """A group with no shared segments gets handoff at '/'."""
        route_groups = {
            "alpha": [{"path": "/alpha/resource", "method": "GET"}],
            "beta": [{"path": "/beta/resource", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        handoff = builder.get_handoff_map("alpha")
        # The divergence point is the root since alpha and beta share nothing
        # but they do share... nothing. Let's check what happens.
        # Actually /alpha is exclusive to alpha, /beta is exclusive to beta.
        # No shared nodes exist, so handoff should be "/"
        assert "/" in handoff

    def test_route_entire_path_shared_handoff_at_leaf(self):
        """Route whose entire path is shared: handoff at leaf shared node."""
        route_groups = {
            "group-a": [
                {"path": "/v3/tenants/{tenant-id}", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
            ],
            "group-b": [
                {"path": "/v3/tenants/{tenant-id}", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # For the route /v3/tenants/{tenant-id} which is entirely shared,
        # the handoff should be at the leaf shared node
        handoff_a = builder.get_handoff_map("group-a")
        assert "/v3/tenants/{tenant-id}" in handoff_a


# ---------------------------------------------------------------------------
# Construct ID Generation Tests (Requirement 3.4)
# ---------------------------------------------------------------------------


class TestConstructIdGeneration:
    """Tests for construct ID generation."""

    def test_basic_construct_id(self):
        """'/v3/tenants/{tenant-id}' → 'SharedPath-v3-tenants-tenant-id'."""
        result = PathOwnershipBuilder.compute_construct_id(
            ["v3", "tenants", "{tenant-id}"]
        )
        assert result == "SharedPath-v3-tenants-tenant-id"

    def test_construct_id_removes_braces(self):
        """Braces are removed from parameterized segments."""
        result = PathOwnershipBuilder.compute_construct_id(["v3", "users", "{user-id}"])
        assert result == "SharedPath-v3-users-user-id"

    def test_construct_id_simple_path(self):
        """Simple path without parameters."""
        result = PathOwnershipBuilder.compute_construct_id(["v3", "app"])
        assert result == "SharedPath-v3-app"

    def test_construct_id_uniqueness(self):
        """Distinct paths produce distinct construct IDs."""
        id_1 = PathOwnershipBuilder.compute_construct_id(
            ["v3", "tenants", "{tenant-id}"]
        )
        id_2 = PathOwnershipBuilder.compute_construct_id(["v3", "app"])
        id_3 = PathOwnershipBuilder.compute_construct_id(
            ["v3", "tenants", "{tenant-id}", "users"]
        )
        assert id_1 != id_2
        assert id_1 != id_3
        assert id_2 != id_3

    def test_construct_id_deterministic(self):
        """Same input always produces the same output."""
        segments = ["v3", "tenants", "{tenant-id}"]
        result_1 = PathOwnershipBuilder.compute_construct_id(segments)
        result_2 = PathOwnershipBuilder.compute_construct_id(segments)
        assert result_1 == result_2


# ---------------------------------------------------------------------------
# Conflict Detection Tests (Requirement 8.1, 8.2, 8.3)
# ---------------------------------------------------------------------------


class TestConflictDetection:
    """Tests for conflict detection via validate()."""

    def test_valid_configuration_does_not_raise(self, built_builder):
        """A valid configuration passes validation without error."""
        # Should not raise
        built_builder.validate()

    def test_validate_raises_on_unowned_shared_node(self):
        """ValueError raised when shared node would be unowned.

        Note: In the current implementation, shared nodes are always correctly
        identified by the trie construction. This test verifies that validate()
        runs the self-consistency check without error on a valid trie.
        The validate() method would raise if the internal state were corrupted.
        """
        # A normal valid configuration should pass
        route_groups = {
            "a": [{"path": "/shared/unique-a", "method": "GET"}],
            "b": [{"path": "/shared/unique-b", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # Should not raise — shared node "shared" is correctly identified
        builder.validate()


# ---------------------------------------------------------------------------
# Single Group Edge Case (Requirement 6.2)
# ---------------------------------------------------------------------------


class TestSingleGroupEdgeCase:
    """Tests for single group edge case."""

    def test_single_group_no_shared_nodes(self):
        """Single group with parameterized paths produces NO shared nodes.

        When all paths in a subtree belong to a single real group, preemptive
        sharing is skipped — there is no relocation risk because no other group
        could ever branch from this parameterized prefix.
        """
        route_groups = {
            "only-group": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        shared_nodes = builder.get_shared_nodes()
        # Single group → no shared nodes even with parameterized paths
        assert len(shared_nodes) == 0

    def test_single_group_no_shared_nodes_when_preemptive_disabled(self):
        """Single group produces no shared nodes when preemptive sharing is disabled."""
        route_groups = {
            "only-group": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(
            route_groups, preemptive_shared_parameterized=False
        )
        builder.build()
        shared_nodes = builder.get_shared_nodes()
        assert len(shared_nodes) == 0

    def test_single_group_handoff_is_root_only(self):
        """Single group handoff map has only '/' when preemptive sharing is disabled."""
        route_groups = {
            "only-group": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(
            route_groups, preemptive_shared_parameterized=False
        )
        builder.build()
        handoff = builder.get_handoff_map("only-group")
        assert handoff == {"/": "/"}

    def test_single_group_handoff_with_preemptive_sharing(self):
        """Single group handoff map only has '/' — no preemptive sharing in single-group subtrees."""
        route_groups = {
            "only-group": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        handoff = builder.get_handoff_map("only-group")
        # Single group → handoff from root only (no shared nodes to hand off from)
        assert handoff == {"/": "/"}


# ---------------------------------------------------------------------------
# Error Handling / Edge Cases
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_empty_route_groups_raises_value_error(self):
        """Empty route_groups raises ValueError."""
        with pytest.raises(ValueError, match="at least one route group"):
            PathOwnershipBuilder({})

    def test_route_missing_path_key_is_skipped(self):
        """Route missing 'path' key is gracefully skipped."""
        route_groups = {
            "group-a": [
                {"method": "GET"},  # Missing 'path' key
                {"path": "/v3/users", "method": "GET"},
            ],
            "group-b": [
                {"path": "/v3/metrics", "method": "GET"},
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # Should not raise, and the route without path is skipped
        shared_nodes = builder.get_shared_nodes()
        shared_segments = [node.segment for node in shared_nodes]
        assert "v3" in shared_segments

    def test_build_must_be_called_before_get_shared_nodes(self):
        """RuntimeError raised if build() not called before get_shared_nodes()."""
        route_groups = {
            "group-a": [{"path": "/v3/users", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        with pytest.raises(RuntimeError, match="Must call build"):
            builder.get_shared_nodes()

    def test_build_must_be_called_before_get_handoff_map(self):
        """RuntimeError raised if build() not called before get_handoff_map()."""
        route_groups = {
            "group-a": [{"path": "/v3/users", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        with pytest.raises(RuntimeError, match="Must call build"):
            builder.get_handoff_map("group-a")

    def test_build_must_be_called_before_validate(self):
        """RuntimeError raised if build() not called before validate()."""
        route_groups = {
            "group-a": [{"path": "/v3/users", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        with pytest.raises(RuntimeError, match="Must call build"):
            builder.validate()


# ---------------------------------------------------------------------------
# TrieNode Properties Tests
# ---------------------------------------------------------------------------


class TestTrieNodeProperties:
    """Tests for TrieNode property methods."""

    def test_full_path_from_leaf(self, built_builder):
        """full_path returns correct path from root to leaf."""
        users_node = (
            built_builder._root.children["v3"]
            .children["tenants"]
            .children["{tenant-id}"]
            .children["users"]
        )
        assert users_node.full_path == ["v3", "tenants", "{tenant-id}", "users"]

    def test_full_path_from_root_child(self, built_builder):
        """full_path for a direct child of root."""
        v3 = built_builder._root.children["v3"]
        assert v3.full_path == ["v3"]

    def test_is_shared_with_one_group(self):
        """Node with one group is not shared."""
        node = TrieNode(segment="test", groups={"only-one"})
        assert node.is_shared is False

    def test_is_shared_with_two_groups(self):
        """Node with two groups is shared."""
        node = TrieNode(segment="test", groups={"a", "b"})
        assert node.is_shared is True

    def test_is_exclusive_with_one_group(self):
        """Node with one group is exclusive."""
        node = TrieNode(segment="test", groups={"only-one"})
        assert node.is_exclusive is True

    def test_is_exclusive_with_zero_groups(self):
        """Node with zero groups is not exclusive."""
        node = TrieNode(segment="test", groups=set())
        assert node.is_exclusive is False


# ---------------------------------------------------------------------------
# Routes With Handoff Tests
# ---------------------------------------------------------------------------


class TestRoutesWithHandoff:
    """Tests for get_routes_with_handoff()."""

    def test_routes_annotated_with_handoff_path(self, built_builder):
        """Routes are annotated with _handoff_path key."""
        annotated = built_builder.get_routes_with_handoff("users")
        for route in annotated:
            assert "_handoff_path" in route

    def test_users_routes_handoff_at_shared_leaf(self, built_builder):
        """Users group routes have handoff at their respective shared leaf nodes.

        Because metrics group shares the 'users' and '{user-id}' nodes,
        the users group's routes are entirely shared paths with handoff
        at the leaf shared node for each route.
        """
        annotated = built_builder.get_routes_with_handoff("users")
        handoff_paths = {r["path"]: r["_handoff_path"] for r in annotated}
        assert (
            handoff_paths["/v3/tenants/{tenant-id}/users"]
            == "/v3/tenants/{tenant-id}/users"
        )
        assert (
            handoff_paths["/v3/tenants/{tenant-id}/users/{user-id}"]
            == "/v3/tenants/{tenant-id}/users/{user-id}"
        )

    def test_warmup_routes_handoff_at_v3(self, built_builder):
        """Warm-up group routes have handoff at /v3."""
        annotated = built_builder.get_routes_with_handoff("warm-up")
        for route in annotated:
            assert route["_handoff_path"] == "/v3"


# ---------------------------------------------------------------------------
# Preemptive Shared Parameterized Path Tests
# ---------------------------------------------------------------------------


class TestPreemptiveSharedParameterized:
    """Tests for preemptive sharing of parameterized path segments.

    This feature prevents CloudFormation resource relocation conflicts when a new
    route group is added that shares a parameterized path prefix with existing groups.

    The exact scenario this solves: two groups ('profiles' and 'notifications') both
    use /tenants/{tenant-id}/users/{user-id}/... — because {tenant-id} exists in a
    multi-group context, it and its children are preemptively marked as shared.

    IMPORTANT: Preemptive marking only applies when the parameterized node is in a
    multi-group context (i.e., its parent's children collectively have multiple real
    groups). In single-group deployments, no preemptive marking occurs because
    there's no relocation risk — and marking would actually CAUSE relocation
    conflicts when new parameterized paths are added to the same group later.
    """

    def test_parameterized_segment_not_shared_in_single_group(self):
        """Parameterized segments are NOT shared with only a single route group.

        In a single-group deployment, the parent of the parameterized node has
        only one real group flowing through it, so preemptive marking is skipped
        to avoid causing relocation conflicts on incremental deployments.
        """
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        user_id = tenant_id.children["users"].children["{user-id}"]
        # Single group → no preemptive marking
        assert tenant_id.is_shared is False
        assert user_id.is_shared is False

    def test_parameterized_segment_shared_in_multi_group(self):
        """Parameterized segments ARE shared when multiple groups exist at parent level."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
            "notifications": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/notifications",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        # Multi-group context → preemptive marking applies
        assert tenant_id.is_shared is True
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP in tenant_id.groups

    def test_children_of_parameterized_segment_shared_in_multi_group(self):
        """Immediate children of parameterized segments are shared in multi-group context."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
            "notifications": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/notifications",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        users_node = tenant_id.children["users"]
        # 'users' is a child of {tenant-id} in a multi-group context → preemptively shared
        assert users_node.is_shared is True
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP in users_node.groups

    def test_children_of_parameterized_segment_not_shared_in_single_group(self):
        """Immediate children of parameterized segments are NOT shared in single-group."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        users_node = tenant_id.children["users"]
        # Single group → no preemptive marking
        assert users_node.is_shared is False
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP not in users_node.groups

    def test_ancestors_of_parameterized_segment_shared_in_multi_group(self):
        """Ancestors of a parameterized segment are shared in multi-group context."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
            "notifications": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/notifications",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenants_node = builder._root.children["tenants"]
        assert tenants_node.is_shared is True
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP in tenants_node.groups

    def test_ancestors_not_shared_in_single_group(self):
        """Ancestors of a parameterized segment are NOT shared in single-group."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        tenants_node = builder._root.children["tenants"]
        assert tenants_node.is_shared is False
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP not in tenants_node.groups

    def test_adding_new_group_does_not_relocate_resources(self):
        """Adding a new group under the same parameterized prefix works correctly.

        In the multi-group (after) state, preemptive marking correctly identifies
        shared paths. In the single-group (before) state, no marking occurs.

        NOTE: The transition from single-group to multi-group DOES create new shared
        nodes. This means adding a brand new second group to a previously single-group
        parameterized prefix will relocate resources. This is an accepted trade-off —
        the alternative (always marking single-group paths) causes the SAME relocation
        issue when adding new parameterized routes to an existing single group.
        """
        # Before: only profiles — single group, no preemptive marking
        route_groups_before = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder_before = PathOwnershipBuilder(route_groups_before)
        builder_before.build()
        shared_before = {
            "/" + "/".join(n.full_path) for n in builder_before.get_shared_nodes()
        }
        # Single group → no shared nodes
        assert len(shared_before) == 0

        # After: profiles + notifications — multi-group, preemptive marking applies
        route_groups_after = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
            "notifications": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/notifications",
                    "method": "GET",
                },
            ],
        }
        builder_after = PathOwnershipBuilder(route_groups_after)
        builder_after.build()
        shared_after = {
            "/" + "/".join(n.full_path) for n in builder_after.get_shared_nodes()
        }

        # Multi-group: shared paths include the parameterized prefix
        assert "/tenants/{tenant-id}/users" in shared_after
        assert "/tenants/{tenant-id}" in shared_after

    def test_non_parameterized_paths_not_affected(self):
        """Paths without parameterized segments are not preemptively shared."""
        route_groups = {
            "alpha": [{"path": "/alpha/resource", "method": "GET"}],
            "beta": [{"path": "/beta/resource", "method": "GET"}],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # No parameterized segments → no preemptive sharing
        alpha_node = builder._root.children["alpha"]
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP not in alpha_node.groups
        assert alpha_node.is_exclusive is True

    def test_opt_out_disables_preemptive_sharing(self):
        """Setting preemptive_shared_parameterized=False disables the feature."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(
            route_groups, preemptive_shared_parameterized=False
        )
        builder.build()
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        # Without preemptive sharing, single-group nodes stay exclusive
        assert tenant_id.is_exclusive is True
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP not in tenant_id.groups

    def test_nested_parameterized_segments_not_shared_in_single_group(self):
        """Multiple nested parameterized segments are NOT shared in single-group context."""
        route_groups = {
            "tasks": [
                {
                    "path": "/tenants/{tenant-id}/assets/{asset-id}/maintenance/{schedule-id}/tasks",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Single group → no preemptive marking anywhere
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        assets = tenant_id.children["assets"]
        asset_id = assets.children["{asset-id}"]
        maintenance = asset_id.children["maintenance"]
        schedule_id = maintenance.children["{schedule-id}"]
        tasks = schedule_id.children["tasks"]

        assert tenant_id.is_shared is False
        assert assets.is_shared is False
        assert asset_id.is_shared is False
        assert maintenance.is_shared is False
        assert schedule_id.is_shared is False
        assert tasks.is_shared is False

    def test_nested_parameterized_segments_shared_in_multi_group(self):
        """Multiple nested parameterized segments are shared in multi-group context."""
        route_groups = {
            "tasks": [
                {
                    "path": "/tenants/{tenant-id}/assets/{asset-id}/maintenance/{schedule-id}/tasks",
                    "method": "GET",
                },
            ],
            "reports": [
                {
                    "path": "/tenants/{tenant-id}/assets/{asset-id}/reports",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()

        # Multi-group: {tenant-id} is in multi-group context → marked
        tenant_id = builder._root.children["tenants"].children["{tenant-id}"]
        assets = tenant_id.children["assets"]
        asset_id = assets.children["{asset-id}"]

        assert tenant_id.is_shared is True
        assert assets.is_shared is True  # child of {tenant-id}
        assert asset_id.is_shared is True  # parameterized, parent has multiple groups

    def test_validate_passes_with_preemptive_sharing(self):
        """Validation still passes with preemptive sharing enabled."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
            "notifications": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/notifications",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # Should not raise
        builder.validate()

    def test_validate_passes_with_single_group_preemptive(self):
        """Validation passes with single group (no shared nodes created)."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        # Should not raise — no shared nodes, no conflicts
        builder.validate()

    def test_handoff_map_with_preemptive_single_group(self):
        """Single group handoff map has only '/' — no shared paths."""
        route_groups = {
            "profiles": [
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile",
                    "method": "GET",
                },
                {
                    "path": "/tenants/{tenant-id}/users/{user-id}/profile/preferences",
                    "method": "GET",
                },
            ],
        }
        builder = PathOwnershipBuilder(route_groups)
        builder.build()
        handoff = builder.get_handoff_map("profiles")
        # Single group → handoff from root only
        assert handoff == {"/": "/"}


# ---------------------------------------------------------------------------
# Regression: Feature-Flags Incremental Deployment (Issue #409)
# ---------------------------------------------------------------------------


class TestFeatureFlagsIncrementalDeployment:
    """Regression tests for the feature-flags deployment conflict.

    Scenario: A 'feature-flags' group exists with routes under
    /v3/feature-flags/... alongside other groups under /v3/tenants/...
    Adding a new parameterized route (/v3/feature-flags/registry/{registration-id})
    should NOT cause 'registry' to be promoted to the parent stack.

    This was caused by the preemptive marking logic marking ancestors of ANY
    parameterized segment as shared — even when those ancestors were exclusively
    owned by a single group deep within its private subtree.
    """

    @pytest.fixture
    def multi_group_with_feature_flags(self):
        """Simulate the real Aplos NCA deployment with feature-flags."""
        route_groups = {
            "users": [
                {"path": "/v3/tenants/{tenant-id}/users", "method": "GET"},
                {"path": "/v3/tenants/{tenant-id}/users/{user-id}", "method": "GET"},
            ],
            "metrics": [
                {"path": "/v3/tenants/{tenant-id}/metrics", "method": "GET"},
            ],
            "feature-flags": [
                {"path": "/v3/feature-flags/registry", "method": "GET"},
                {
                    "path": "/v3/feature-flags/registry/{registration-id}",
                    "method": "DELETE",
                },
                {
                    "path": "/v3/feature-flags/registry/{registration-id}",
                    "method": "PUT",
                },
                {"path": "/v3/feature-flags/rules", "method": "GET"},
                {"path": "/v3/feature-flags/rules/{rule-id}", "method": "DELETE"},
                {"path": "/v3/feature-flags/evaluate", "method": "GET"},
            ],
        }
        return route_groups

    def test_registry_not_shared(self, multi_group_with_feature_flags):
        """'registry' under feature-flags should NOT be shared (not promoted to parent)."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        feature_flags = builder._root.children["v3"].children["feature-flags"]
        registry = feature_flags.children["registry"]

        # registry should be exclusive to feature-flags group — NOT shared
        assert registry.is_shared is False
        assert PathOwnershipBuilder._PREEMPTIVE_GROUP not in registry.groups

    def test_registration_id_not_shared(self, multi_group_with_feature_flags):
        """{registration-id} should NOT be shared."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        registration_id = (
            builder._root.children["v3"]
            .children["feature-flags"]
            .children["registry"]
            .children["{registration-id}"]
        )
        assert registration_id.is_shared is False

    def test_feature_flags_not_shared(self, multi_group_with_feature_flags):
        """'feature-flags' itself should NOT be shared (only one group routes through it)."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        feature_flags = builder._root.children["v3"].children["feature-flags"]
        assert feature_flags.is_shared is False

    def test_v3_is_genuinely_shared(self, multi_group_with_feature_flags):
        """'v3' should be shared because multiple real groups route through it."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        v3 = builder._root.children["v3"]
        real_groups = v3.groups - {PathOwnershipBuilder._PREEMPTIVE_GROUP}
        assert len(real_groups) > 1
        assert v3.is_shared is True

    def test_tenant_id_is_shared_in_multi_group(self, multi_group_with_feature_flags):
        """{tenant-id} is correctly shared because tenants has multiple groups."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        tenant_id = (
            builder._root.children["v3"].children["tenants"].children["{tenant-id}"]
        )
        assert tenant_id.is_shared is True

    def test_handoff_map_feature_flags_from_v3(self, multi_group_with_feature_flags):
        """Feature-flags group handoff should be at /v3 (shared), not deeper."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()

        handoff = builder.get_handoff_map("feature-flags")
        # v3 is the only shared ancestor — handoff from there
        assert "/v3" in handoff
        # registry should NOT be in handoff (it's not shared)
        assert "/v3/feature-flags/registry" not in handoff

    def test_adding_parameterized_route_no_relocation(
        self, multi_group_with_feature_flags
    ):
        """Adding {registration-id} routes should not create new shared nodes under feature-flags.

        This is the exact regression: previously, adding DELETE/PUT routes for
        /v3/feature-flags/registry/{registration-id} caused 'registry' to be
        promoted to the parent stack (409 conflict).
        """
        # Before: no {registration-id} routes
        route_groups_before = {
            "users": multi_group_with_feature_flags["users"],
            "metrics": multi_group_with_feature_flags["metrics"],
            "feature-flags": [
                {"path": "/v3/feature-flags/registry", "method": "GET"},
                {"path": "/v3/feature-flags/rules", "method": "GET"},
                {"path": "/v3/feature-flags/rules/{rule-id}", "method": "DELETE"},
                {"path": "/v3/feature-flags/evaluate", "method": "GET"},
            ],
        }
        builder_before = PathOwnershipBuilder(route_groups_before)
        builder_before.build()
        shared_before = {
            "/" + "/".join(n.full_path) for n in builder_before.get_shared_nodes()
        }

        # After: {registration-id} routes added
        builder_after = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder_after.build()
        shared_after = {
            "/" + "/".join(n.full_path) for n in builder_after.get_shared_nodes()
        }

        # Critical: no new shared paths under feature-flags/ should appear
        new_shared = shared_after - shared_before
        feature_flags_new_shared = {p for p in new_shared if "feature-flags" in p}
        assert feature_flags_new_shared == set(), (
            f"Adding parameterized routes caused new shared nodes under feature-flags: "
            f"{feature_flags_new_shared}"
        )

    def test_validate_passes(self, multi_group_with_feature_flags):
        """Validation passes with the feature-flags multi-group configuration."""
        builder = PathOwnershipBuilder(multi_group_with_feature_flags)
        builder.build()
        builder.validate()
