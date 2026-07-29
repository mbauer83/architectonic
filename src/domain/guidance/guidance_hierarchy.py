"""Guidance hierarchy contract (v2 layered guidance).

Guidance is attachable to any level a module declares and composed additively along a
concept's ancestry path when authoring support is requested. The level declaration is
authoritative here (never in a guidance document): a module declares an ordered set of
``GuidanceLevel``s and the ``GuidanceNode``s populating them, with each node naming its
parent one level up. For archimate-4 the levels are domain → entity type → specialization;
a module with a different tree (shallower or deeper) declares exactly its own.

``GuidanceLevelId`` is deliberately a *runtime-validated* string, not a closed union —
closing it at compile time would defeat module extensibility. Validation (undeclared level,
duplicate node, missing parent, cycle, non-total ordering) happens at import/build time via
:meth:`GuidanceHierarchy.validation_errors`, never as a runtime surprise during serving.
"""

from __future__ import annotations

from dataclasses import dataclass

GuidanceLevelId = str


@dataclass(frozen=True)
class GuidanceLevel:
    """One declared level in a module's guidance tree, with a display label and total order.

    ``order`` 0 is the broadest (root) level; larger is narrower. Orders must be unique across
    a hierarchy — that uniqueness is what makes the levels a total order (the parent of a level
    is the level with the next-lower order). ``order`` is an internal detail computed from the
    ontology declaration's list position; it never appears in a guidance document.

    In a v2 guidance document a broader level's context is keyed by the level ``id`` itself
    (e.g. ``domain:``); ``label`` is display-only. The two leaf levels (entity type,
    specialization) have no document map — the parser adapts them from the unchanged v1
    ``entity_types``/``connection_types`` slots.
    """

    id: GuidanceLevelId
    label: str
    order: int


@dataclass(frozen=True)
class GuidanceNode:
    """One node at a level. ``parent_node_id`` is the node id at the parent (next-broader) level,
    or ``None`` for a node at the root level. Node ids are unique within their level, not globally.
    """

    level_id: GuidanceLevelId
    node_id: str
    parent_node_id: str | None = None


@dataclass(frozen=True)
class GuidanceHierarchy:
    """An ordered set of levels plus the nodes populating them — a module's declared guidance tree."""

    levels: tuple[GuidanceLevel, ...]
    nodes: tuple[GuidanceNode, ...]

    def level_ids(self) -> frozenset[GuidanceLevelId]:
        return frozenset(level.id for level in self.levels)

    def is_declared_level(self, level_id: GuidanceLevelId) -> bool:
        return level_id in self.level_ids()

    def ordered_levels(self) -> tuple[GuidanceLevel, ...]:
        return tuple(sorted(self.levels, key=lambda level: level.order))

    def parent_level_of(self, level_id: GuidanceLevelId) -> GuidanceLevel | None:
        """The declared level one step broader than ``level_id`` (largest order below it), or None
        for the root level / an undeclared level."""
        target = next((level for level in self.levels if level.id == level_id), None)
        if target is None:
            return None
        broader = [level for level in self.levels if level.order < target.order]
        return max(broader, key=lambda level: level.order) if broader else None

    def _node(self, level_id: GuidanceLevelId, node_id: str) -> GuidanceNode | None:
        return next(
            (n for n in self.nodes if n.level_id == level_id and n.node_id == node_id),
            None,
        )

    def ancestry(self, level_id: GuidanceLevelId, node_id: str) -> tuple[GuidanceNode, ...]:
        """Nodes from the root level down to ``(level_id, node_id)`` inclusive, in composition
        order (broadest first). Empty if the node is not declared. Bounded by the level count so a
        malformed (cyclic) tree can never loop — build-time validation rejects such trees anyway.
        """
        chain: list[GuidanceNode] = []
        current = self._node(level_id, node_id)
        seen: set[tuple[str, str]] = set()
        while current is not None and (current.level_id, current.node_id) not in seen:
            seen.add((current.level_id, current.node_id))
            chain.append(current)
            parent_level = self.parent_level_of(current.level_id)
            if parent_level is None or current.parent_node_id is None:
                break
            current = self._node(parent_level.id, current.parent_node_id)
            if len(chain) > len(self.levels):
                break
        return tuple(reversed(chain))

    def validation_errors(self) -> tuple[str, ...]:
        """All structural problems, deterministically ordered. Empty means the tree is sound."""
        errors: list[str] = []
        errors.extend(self._level_ordering_errors())
        errors.extend(self._node_errors())
        return tuple(errors)

    def _level_ordering_errors(self) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()
        for level in self.levels:
            if level.id in seen_ids:
                errors.append(f"duplicate level id {level.id!r}")
            seen_ids.add(level.id)
        orders = [level.order for level in self.levels]
        if len(set(orders)) != len(orders):
            errors.append("level orders are not a total order (duplicate order values)")
        return sorted(errors)

    def _node_errors(self) -> list[str]:
        errors: list[str] = []
        declared = self.level_ids()
        seen: set[tuple[str, str]] = set()
        for node in self.nodes:
            ref = f"{node.level_id}/{node.node_id}"
            if node.level_id not in declared:
                errors.append(f"node {ref} is on undeclared level {node.level_id!r}")
                continue
            if (node.level_id, node.node_id) in seen:
                errors.append(f"duplicate node {ref}")
            seen.add((node.level_id, node.node_id))
            errors.extend(self._parent_errors(node, ref))
        return sorted(errors)

    def _parent_errors(self, node: GuidanceNode, ref: str) -> list[str]:
        parent_level = self.parent_level_of(node.level_id)
        if parent_level is None:
            if node.parent_node_id is not None:
                return [f"root-level node {ref} must not declare a parent"]
            return []
        if node.parent_node_id is None:
            return [f"node {ref} is missing a parent at level {parent_level.id!r}"]
        if self._node(parent_level.id, node.parent_node_id) is None:
            return [f"node {ref} references missing parent {parent_level.id}/{node.parent_node_id}"]
        return []

    def to_serializable(self) -> dict[str, object]:
        """Deterministic plain-data view (levels by order, nodes sorted) for stable snapshots."""
        return {
            "levels": [
                {"id": level.id, "label": level.label, "order": level.order}
                for level in self.ordered_levels()
            ],
            "nodes": [
                {"level_id": n.level_id, "node_id": n.node_id, "parent_node_id": n.parent_node_id}
                for n in sorted(self.nodes, key=lambda n: (n.level_id, n.node_id))
            ],
        }
