"""Validate and filter one meta-ontology's guidance document against the module it targets.

A guidance document's nesting mirrors the module's declared guidance hierarchy: the alias is the
root node, its non-reserved keys are nodes of the next declared level, and so on until the level
above the leaf levels, whose concepts arrive as ``entity_types``/``connection_types`` slots. This
module is where that correspondence is *checked* — the runtime overlay parser
(:mod:`src.domain.guidance.guidance`) deliberately reads the same document without the hierarchy, because
it runs while the module is still being built.

What the nesting buys over flat, level-keyed maps: an entity type filed under the wrong node is a
detectable error rather than silently-served guidance, because the document states the type's
domain and the module can disagree.

Everything here is pure: the caller fetches the document and reports the outcome.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.guidance.guidance import (
    CONNECTION_TYPES_KEY,
    CONTEXT_KEY,
    ENTITY_TYPES_KEY,
    RESERVED_KEYS,
    SPECIALIZATIONS_KEY,
    ConceptKind,
)
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel
from src.domain.guidance.guidance_hierarchy_source import ENTITY_TYPE_LEVEL, SPECIALIZATION_LEVEL
from src.domain.ontology_representation.ontology_protocol import OntologyModule

# The levels whose concepts are named by type slots rather than by document nodes, so the node
# nesting stops at their parent level.
_SLOT_LEVELS = frozenset({ENTITY_TYPE_LEVEL, SPECIALIZATION_LEVEL})


@dataclass
class FilteredNode:
    """One node's filtered content plus the keys that matched and failed validation.

    An accumulator: it fills while its subtree is walked, and the caller reads the totals once at
    the end.
    """

    content: dict[str, object] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)

    def absorb(self, other: FilteredNode, *, key: str) -> None:
        if other.content:
            self.content[key] = other.content
        self.matched.extend(other.matched)
        self.unmatched.extend(other.unmatched)


@dataclass(frozen=True)
class _NodePosition:
    """Where in the document a node sits: its declared level (None above the root), its node id,
    and the key path that reaches it (empty at the root, which is the alias itself)."""

    level: GuidanceLevel | None
    node_id: str
    prefix: tuple[str, ...]

    def key(self, *parts: str) -> str:
        return ".".join((*self.prefix, *parts))

    def child(self, level: GuidanceLevel, node_id: str) -> _NodePosition:
        return _NodePosition(level=level, node_id=node_id, prefix=(*self.prefix, node_id))


def filter_document(
    module: OntologyModule, hierarchy: GuidanceHierarchy, document: Mapping[str, object], *, alias: str
) -> FilteredNode:
    """Filter one alias's document, keeping only content whose placement the module confirms.

    Reported keys are the document paths beneath the alias (``motivation.entity_types.goal``,
    ``connection_types.archimate-composition``, ``motivation.context``), so an unmatched key names
    exactly the line to fix. ``alias`` is the document's root node id — the same id the module's
    hierarchy gives its root — so a child node is checked against a real declared parent.
    """
    root_level = hierarchy.ordered_levels()[0] if hierarchy.levels else None
    root = _NodePosition(level=root_level, node_id=alias, prefix=())
    return _DocumentFilter(module, hierarchy).node(document, root)


class _DocumentFilter:
    """Walks one document against one module's hierarchy. Holds the pair every check needs, so a
    node's own position is all that travels down the recursion."""

    def __init__(self, module: OntologyModule, hierarchy: GuidanceHierarchy) -> None:
        self._module = module
        self._hierarchy = hierarchy

    def node(self, node_data: Mapping[str, object], at: _NodePosition) -> FilteredNode:
        out = FilteredNode()
        self._context(node_data, at, out)
        self._entity_types(node_data, at, out)
        self._connection_types(node_data, at, out)
        self._child_nodes(node_data, at, out)
        return out

    def _context(self, node_data: Mapping[str, object], at: _NodePosition, out: FilteredNode) -> None:
        if CONTEXT_KEY not in node_data:
            return
        context = node_data[CONTEXT_KEY]
        key = at.key(CONTEXT_KEY)
        if isinstance(context, str) and context.strip():
            out.content[CONTEXT_KEY] = context
            out.matched.append(key)
        else:
            out.unmatched.append(f"{key} (context must be a non-empty string)")

    def _child_nodes(self, node_data: Mapping[str, object], at: _NodePosition, out: FilteredNode) -> None:
        """Recurse into this node's declared children, one level down."""
        child_level = self._child_level(at.level)
        for key, value in node_data.items():
            if not isinstance(key, str) or key in RESERVED_KEYS:
                continue
            path = at.key(key)
            if child_level is None:
                level_name = at.level.id if at.level else "the root"
                out.unmatched.append(f"{path} (no guidance level below {level_name})")
            elif not isinstance(value, Mapping):
                out.unmatched.append(f"{path} (node must be a mapping)")
            elif not self._is_declared_child(child_level.id, key, parent_node_id=at.node_id):
                out.unmatched.append(f"{path} (not a declared {child_level.id} of {at.node_id!r})")
            else:
                out.absorb(self.node(value, at.child(child_level, key)), key=key)

    def _child_level(self, level: GuidanceLevel | None) -> GuidanceLevel | None:
        """The level below ``level`` while the document still names its nodes; None once the next
        level's concepts arrive as type slots instead."""
        if level is None:
            return None
        below = [candidate for candidate in self._hierarchy.ordered_levels() if candidate.order > level.order]
        child = below[0] if below else None
        return None if child is None or child.id in _SLOT_LEVELS else child

    def _is_declared_child(self, level_id: str, node_id: str, *, parent_node_id: str) -> bool:
        return any(
            node.level_id == level_id and node.node_id == node_id and node.parent_node_id == parent_node_id
            for node in self._hierarchy.nodes
        )

    def _entity_types(self, node_data: Mapping[str, object], at: _NodePosition, out: FilteredNode) -> None:
        """Entity-type slots belong to the node the module declares as the types' parent, so a type
        filed under another node is rejected rather than served under the wrong framing."""
        section = self._section(node_data, ENTITY_TYPES_KEY, at, out)
        if section is None:
            return
        expected_level = self._hierarchy.parent_level_of(ENTITY_TYPE_LEVEL)
        if expected_level is not None and (at.level is None or at.level.id != expected_level.id):
            out.unmatched.append(
                f"{at.key(ENTITY_TYPES_KEY)} (entity types belong under a {expected_level.id} node)"
            )
            return
        known = frozenset(str(name) for name in self._module.entity_types)
        filtered: dict[str, object] = {}
        for type_name, type_data in section.items():
            key = at.key(ENTITY_TYPES_KEY, str(type_name))
            if not isinstance(type_name, str) or type_name not in known:
                out.unmatched.append(key)
                continue
            declared_parent = self._declared_parent(type_name)
            if declared_parent != at.node_id:
                out.unmatched.append(f"{key} (declared under {declared_parent!r}, not {at.node_id!r})")
                continue
            filtered[type_name] = self._type_entry("entity", type_name, type_data, out, key=key)
        if filtered:
            out.content[ENTITY_TYPES_KEY] = filtered

    def _connection_types(self, node_data: Mapping[str, object], at: _NodePosition, out: FilteredNode) -> None:
        """Connection types are declared for the whole meta-ontology — they carry no level of their
        own — so their slot belongs at the root node and nowhere else."""
        section = self._section(node_data, CONNECTION_TYPES_KEY, at, out)
        if section is None:
            return
        if at.prefix:
            out.unmatched.append(
                f"{at.key(CONNECTION_TYPES_KEY)} (connection types belong at the meta-ontology root)"
            )
            return
        known = frozenset(str(name) for name in self._module.connection_types)
        filtered: dict[str, object] = {}
        for type_name, type_data in section.items():
            key = at.key(CONNECTION_TYPES_KEY, str(type_name))
            if not isinstance(type_name, str) or type_name not in known:
                out.unmatched.append(key)
                continue
            filtered[type_name] = self._type_entry("connection", type_name, type_data, out, key=key)
        if filtered:
            out.content[CONNECTION_TYPES_KEY] = filtered

    def _section(
        self, node_data: Mapping[str, object], slot: str, at: _NodePosition, out: FilteredNode
    ) -> Mapping[str, object] | None:
        """One type slot's map, or None when the node has no such slot — reporting a slot that is
        present but not a mapping, since that is authored content going nowhere."""
        section = node_data.get(slot)
        if isinstance(section, Mapping):
            return section
        if slot in node_data:
            out.unmatched.append(f"{at.key(slot)} (must be a mapping)")
        return None

    def _declared_parent(self, type_name: str) -> str | None:
        return next(
            (
                node.parent_node_id
                for node in self._hierarchy.nodes
                if node.level_id == ENTITY_TYPE_LEVEL and node.node_id == type_name
            ),
            None,
        )

    def _type_entry(
        self, concept_kind: ConceptKind, type_name: str, type_data: object, out: FilteredNode, *, key: str
    ) -> object:
        """One type's guidance, with its optional ``specializations`` slugs validated against the
        module's catalog. A non-mapping entry is kept verbatim — the overlay parser tolerates it by
        omission, and rejecting it here would report a key the author can still read in place."""
        out.matched.append(key)
        if not isinstance(type_data, Mapping):
            return type_data
        filtered: dict[str, object] = {k: v for k, v in type_data.items() if k != SPECIALIZATIONS_KEY}
        specializations = type_data.get(SPECIALIZATIONS_KEY)
        if not isinstance(specializations, Mapping):
            return filtered
        known = frozenset(
            spec.slug for spec in self._module.specialization_catalog.for_type(concept_kind, type_name)
        )
        filtered_specializations: dict[str, object] = {}
        for slug, slug_data in specializations.items():
            slug_key = f"{key}.{SPECIALIZATIONS_KEY}.{slug}"
            if slug in known:
                out.matched.append(slug_key)
                filtered_specializations[str(slug)] = slug_data
            else:
                out.unmatched.append(slug_key)
        if filtered_specializations:
            filtered[SPECIALIZATIONS_KEY] = filtered_specializations
        return filtered
