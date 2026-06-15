"""
Path Ownership Builder — Trie-based path ownership for API Gateway nested stacks.

Builds a trie of all routes across all nested stack groups, identifies every
path segment shared by multiple groups, and computes a Resource_ID_Handoff_Map
telling each nested stack exactly where to attach its unique segments.

No CDK imports — pure Python data structures only.

Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class TrieNode:
    """A single node in the path trie."""

    segment: str
    groups: Set[str] = field(default_factory=set)
    children: Dict[str, "TrieNode"] = field(default_factory=dict)
    parent: Optional["TrieNode"] = field(default=None, repr=False)

    @property
    def is_shared(self) -> bool:
        """True if 2+ groups pass through this node."""
        return len(self.groups) >= 2

    @property
    def is_exclusive(self) -> bool:
        """True if exactly 1 group passes through this node."""
        return len(self.groups) == 1

    @property
    def is_divergence_point(self) -> bool:
        """True if this is a shared node with at least one exclusive child."""
        if not self.is_shared:
            return False
        return any(child.is_exclusive for child in self.children.values())

    @property
    def full_path(self) -> List[str]:
        """Compute the full path from root to this node (excludes root's empty segment)."""
        segments: List[str] = []
        node: Optional[TrieNode] = self
        while node is not None and node.segment != "":
            segments.append(node.segment)
            node = node.parent
        segments.reverse()
        return segments


class PathOwnershipBuilder:
    """Builds a path trie and computes ownership for API Gateway resources."""

    # Synthetic group name injected into nodes to force them into the parent stack.
    _PREEMPTIVE_GROUP = "__preemptive__"

    def __init__(
        self,
        route_groups: Dict[str, List[Dict[str, Any]]],
        preemptive_shared_parameterized: bool = True,
    ):
        """
        Args:
            route_groups: Dict mapping group names to lists of route dicts.
                Each route dict must have a "path" key (e.g., "/v3/tenants/{tenant-id}/users").
            preemptive_shared_parameterized: When True (default), any path segment
                containing a parameterized part (e.g., ``{tenant-id}``) and all of its
                ancestors are automatically treated as shared — even if only one route
                group currently uses them. This prevents CloudFormation resource
                relocation conflicts when a new group is added later that shares the
                same parameterized prefix.

        Raises:
            ValueError: If route_groups is empty.
        """
        if not route_groups:
            raise ValueError("PathOwnershipBuilder requires at least one route group")
        self._route_groups = route_groups
        self._preemptive_shared_parameterized = preemptive_shared_parameterized
        self._root = TrieNode(segment="", groups=set(), children={}, parent=None)
        self._built = False

    def build(self) -> "PathOwnershipBuilder":
        """
        Construct the trie from all routes across all groups in a single pass.

        When ``preemptive_shared_parameterized`` is enabled, a post-processing pass
        marks parameterized nodes and their ancestors as shared by injecting a
        synthetic group. This ensures those API Gateway path resources are always
        created in the parent stack, preventing resource relocation conflicts when
        new route groups are added later that share the same parameterized prefix.

        Returns self for chaining.
        """
        for group_name, routes in self._route_groups.items():
            for route in routes:
                path = route.get("path", "")
                if not path:
                    logger.warning(
                        "Route missing 'path' key or has empty path in group '%s', skipping.",
                        group_name,
                    )
                    continue

                segments = [s for s in path.split("/") if s]
                current = self._root
                for segment in segments:
                    if segment not in current.children:
                        child = TrieNode(
                            segment=segment,
                            groups=set(),
                            children={},
                            parent=current,
                        )
                        current.children[segment] = child
                    current = current.children[segment]
                    current.groups.add(group_name)

        # Post-processing: preemptively mark parameterized paths as shared
        if self._preemptive_shared_parameterized:
            self._mark_parameterized_paths_as_shared(self._root)

        self._built = True
        return self

    def _mark_parameterized_paths_as_shared(self, node: TrieNode) -> None:
        """
        Walk the trie and inject a synthetic group into parameterized nodes
        and all their ancestors (up to root) to force them into the parent stack.

        A parameterized segment is one that contains '{' (e.g., ``{tenant-id}``).
        The immediate children of a parameterized segment are also marked shared
        because they represent the branching points where different groups will
        diverge (e.g., ``users``, ``assets`` after ``{tenant-id}``).

        This ensures that adding a new route group under the same parameterized
        prefix never causes a CloudFormation resource relocation conflict.
        """
        self._walk_and_mark(self._root)

    def _walk_and_mark(self, node: TrieNode) -> None:
        """Recursively walk the trie marking parameterized nodes and their children.

        Applies preemptive marking to parameterized nodes when the node is at a
        "multi-group junction" — i.e., its parent or an ancestor is already shared
        by multiple real groups. This prevents resource relocation when a future
        group branches from the same parameterized prefix.

        Does NOT apply preemptive marking when the parameterized node is deep within
        a single-group's exclusive subtree (where no other group could ever branch).
        In such cases, preemptive marking would actually *cause* relocation conflicts
        during incremental deployments (pulling resources from nested to parent stack).
        """
        for child in node.children.values():
            if self._is_parameterized(child.segment):
                # Attempt to mark this parameterized node and its ancestors.
                # _inject_preemptive_group_upward returns whether marking was applied.
                was_marked = self._inject_preemptive_group_upward(child)
                if was_marked:
                    # Mark immediate children of parameterized nodes as shared.
                    # These are the branching points where different groups diverge
                    # (e.g., "users", "assets", "admin" after {tenant-id}).
                    for grandchild in child.children.values():
                        grandchild.groups.add(self._PREEMPTIVE_GROUP)
            # Recurse into all children regardless
            self._walk_and_mark(child)

    def _inject_preemptive_group_upward(self, node: TrieNode) -> bool:
        """Inject the synthetic preemptive group into this node and ancestors.

        Propagates upward only while the path is at a "multi-group junction" —
        meaning the node's parent has children from multiple real groups (indicating
        that other groups share the prefix and a future group could realistically
        branch from the parameterized segment).

        Stops propagating when it reaches a node whose parent only routes traffic
        from a single real group — at that depth, no other group can reach this
        subtree, so preemptive marking would only cause resource relocation conflicts
        during incremental deployments (pulling nested-stack resources into parent).

        Returns:
            True if the node was marked (preemptive sharing applied),
            False if marking was skipped (single-group subtree, no relocation risk).
        """
        current: Optional[TrieNode] = node
        marked_any = False

        while current is not None and current.segment != "":
            # Check if this node's parent has children from multiple real groups.
            # If so, this level is at a multi-group junction — safe to mark.
            parent = current.parent
            if parent is None or parent.segment == "":
                # Reached the root level. Mark if the root has children from
                # multiple real groups (indicating this is a shared API prefix).
                if parent is not None:
                    root_real_groups = self._get_all_real_groups_in_children(parent)
                    if len(root_real_groups) > 1:
                        current.groups.add(self._PREEMPTIVE_GROUP)
                        marked_any = True
                break

            # Check if the parent level has multiple real groups across its children
            parent_child_groups = self._get_all_real_groups_in_children(parent)
            if len(parent_child_groups) > 1:
                # Multi-group junction — this node can be shared safely
                current.groups.add(self._PREEMPTIVE_GROUP)
                marked_any = True
                current = parent
            else:
                # Single-group subtree — stop propagating.
                # This node is exclusively owned by one group's nested stack.
                break

        return marked_any

    def _get_all_real_groups_in_children(self, node: TrieNode) -> Set[str]:
        """Get the union of all real groups across a node's children."""
        all_groups: Set[str] = set()
        for child in node.children.values():
            all_groups.update(child.groups - {self._PREEMPTIVE_GROUP})
        return all_groups

    @staticmethod
    def _is_parameterized(segment: str) -> bool:
        """Return True if the segment contains a path parameter (e.g., '{tenant-id}')."""
        return "{" in segment and "}" in segment

    def validate(self) -> None:
        """
        Validate the trie after construction.

        Raises:
            ValueError: If any shared node would be left unowned (self-consistency check),
                or if two groups would create the same segment under the same parent.
            RuntimeError: If build() has not been called.
        """
        if not self._built:
            raise RuntimeError("Must call build() before accessing trie results")

        shared_nodes = self.get_shared_nodes()
        for node in shared_nodes:
            path_str = "/" + "/".join(node.full_path)
            # Verify shared nodes are correctly identified (self-consistency)
            if not node.is_shared:
                raise ValueError(
                    f"Unowned shared node: '{path_str}' shared by groups "
                    f"{node.groups} but not assigned to parent stack"
                )

        # Check for cross-stack conflicts: if a shared node exists that
        # would cause two nested stacks to create the same resource
        self._check_cross_stack_conflicts(self._root)

    def _check_cross_stack_conflicts(self, node: TrieNode) -> None:
        """Recursively check for cross-stack conflicts in the trie."""
        for child in node.children.values():
            if child.is_shared:
                # Shared nodes are owned by the parent stack — no conflict
                pass
            elif len(child.groups) > 1:
                # This shouldn't happen if is_shared is correct, but guard anyway
                path_str = "/" + "/".join(child.full_path)
                parent_path = "/" + "/".join(node.full_path) if node.segment else "/"
                raise ValueError(
                    f"Cross-stack conflict: segment '{child.segment}' under "
                    f"'{parent_path}' claimed by groups: {sorted(child.groups)}"
                )
            self._check_cross_stack_conflicts(child)

    def get_shared_nodes(self) -> List[TrieNode]:
        """
        Return all shared nodes in depth-first order (parent before children).

        Raises:
            RuntimeError: If build() has not been called.
        """
        if not self._built:
            raise RuntimeError("Must call build() before accessing trie results")

        result: List[TrieNode] = []
        self._collect_shared_nodes(self._root, result)
        return result

    def _collect_shared_nodes(self, node: TrieNode, result: List[TrieNode]) -> None:
        """Depth-first traversal collecting shared nodes (parent before children)."""
        for child in node.children.values():
            if child.is_shared:
                result.append(child)
            self._collect_shared_nodes(child, result)

    def get_handoff_map(self, group_name: str) -> Dict[str, str]:
        """
        Compute the Resource_ID_Handoff_Map for a specific group.

        Returns:
            Dict mapping path prefixes (as "/" joined strings like "/v3/tenants/{tenant-id}")
            to those same path strings (placeholder keys that will be replaced with
            actual resource IDs during CDK synthesis).

            For routes with no shared prefix, the key is "/" (API root).

        Raises:
            RuntimeError: If build() has not been called.
        """
        if not self._built:
            raise RuntimeError("Must call build() before accessing trie results")

        handoff_paths: Set[str] = set()
        routes = self._route_groups.get(group_name, [])

        for route in routes:
            path = route.get("path", "")
            if not path:
                continue

            segments = [s for s in path.split("/") if s]
            handoff_path = self._find_handoff_path_for_route(segments, group_name)
            handoff_paths.add(handoff_path)

        # Return dict mapping path → path (placeholder keys)
        return {path: path for path in sorted(handoff_paths)}

    def _find_handoff_path_for_route(self, segments: List[str], group_name: str) -> str:
        """
        Find the handoff path for a specific route in a group.

        The handoff path is the deepest shared node that acts as a divergence
        point for this group's route, or a shared leaf if the entire route is shared.
        """
        current = self._root
        last_handoff: Optional[str] = None

        for i, segment in enumerate(segments):
            if segment not in current.children:
                break
            child = current.children[segment]

            if child.is_shared:
                # Check if this is a divergence point for this group
                if child.is_divergence_point:
                    last_handoff = "/" + "/".join(segments[: i + 1])
                # Check if this is a shared leaf node (entire path is shared)
                elif i == len(segments) - 1:
                    # The entire route path is shared — handoff at this leaf
                    last_handoff = "/" + "/".join(segments[: i + 1])
            else:
                # We've hit an exclusive node — stop traversing
                break

            current = child

        if last_handoff is None:
            # No shared segments for this route — handoff from API root
            return "/"

        return last_handoff

    def get_routes_with_handoff(self, group_name: str) -> List[Dict[str, Any]]:
        """
        Return routes for a group annotated with their handoff point.

        Each route dict gets an additional "_handoff_path" key indicating
        which handoff map entry provides its parent resource ID.

        Raises:
            RuntimeError: If build() has not been called.
        """
        if not self._built:
            raise RuntimeError("Must call build() before accessing trie results")

        routes = self._route_groups.get(group_name, [])
        annotated: List[Dict[str, Any]] = []

        for route in routes:
            path = route.get("path", "")
            route_copy = dict(route)

            if not path:
                route_copy["_handoff_path"] = "/"
            else:
                segments = [s for s in path.split("/") if s]
                handoff_path = self._find_handoff_path_for_route(segments, group_name)
                route_copy["_handoff_path"] = handoff_path

            annotated.append(route_copy)

        return annotated

    @staticmethod
    def compute_construct_id(path_segments: List[str]) -> str:
        """
        Generate a stable CDK construct ID from path segments.

        The ID is deterministic and depends only on path content.
        Uses the pattern: "SharedPath-{sanitized-segments}"
        where braces are removed from parameterized segments.

        Args:
            path_segments: List of path segments (e.g., ["v3", "tenants", "{tenant-id}"])

        Returns:
            Stable construct ID string.

        Examples:
            >>> PathOwnershipBuilder.compute_construct_id(["v3", "tenants", "{tenant-id}"])
            'SharedPath-v3-tenants-tenant-id'
            >>> PathOwnershipBuilder.compute_construct_id(["v3", "app"])
            'SharedPath-v3-app'
        """
        sanitized = [
            segment.replace("{", "").replace("}", "") for segment in path_segments
        ]
        return "SharedPath-" + "-".join(sanitized)
