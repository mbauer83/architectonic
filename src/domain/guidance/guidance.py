"""Guidance overlay domain types: imported authoring help, never a governance tier.

Guidance text (``create_when``/``never_create_when``) ships empty in ontology modules for
license reasons and is optionally restored at bootstrap from one deployment-level,
out-of-repo cache (never per engagement/enterprise repo). This module only defines the
overlay shape and parsing; loading the cache and threading the result into ``EntityTypeInfo``
and ``ConnectionTypeInfo`` is application/infrastructure wiring. Guidance authored directly
in committed declarations (e.g. specialization guidance in ``.arch-repo/specializations.yaml``)
does not flow through ``GuidanceOverlay`` at all, so it is never at risk of being overridden
by an imported cache.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

ConceptKind = Literal["entity", "connection"]

# The one guidance-document format version: what the importer accepts, what a written cache is
# stamped with, and what the operational upgrade migrates an older cache to. Bump it only together
# with a migration in ``deployment_upgrade.steps.guidance_cache_format``.
GUIDANCE_FORMAT = 4

CONTEXT_KEY = "context"
ENTITY_TYPES_KEY = "entity_types"
CONNECTION_TYPES_KEY = "connection_types"
SPECIALIZATIONS_KEY = "specializations"
CONCEPT_SECTIONS: dict[str, ConceptKind] = {ENTITY_TYPES_KEY: "entity", CONNECTION_TYPES_KEY: "connection"}
# Structural keys, reserved at every nesting depth: a node id equal to one of these would be read
# as this node's own context/type slots instead of as a child node. Node ids are concept slugs
# (``motivation``, ``goal``), so this only guards against an accidental collision.
RESERVED_KEYS = frozenset({CONTEXT_KEY, *CONCEPT_SECTIONS})


@dataclass(frozen=True)
class GuidanceKey:
    """Identifies one guidance slot: a module's entity/connection type, optionally a specialization."""

    module_alias: str
    concept_kind: ConceptKind
    type_name: str
    specialization: str | None = None


@dataclass(frozen=True)
class GuidanceContextKey:
    """Identifies one broader-level context slot by the node path that reaches it — from the
    module's root node down to the node itself, e.g. ``("archimate-4", "motivation")`` for the
    motivation domain's context. Leaf-level guidance uses :class:`GuidanceKey`.

    A path rather than a ``(level_id, node_id)`` pair because the document's nesting *is* the
    path, and this parser must stay hierarchy-free: the overlay is loaded to build the very
    module whose hierarchy would name the levels, so it cannot consult it. The level id is
    recovered where it is actually needed — at composition time, from the hierarchy's ancestry.
    """

    module_alias: str
    path: tuple[str, ...]


@dataclass(frozen=True)
class GuidanceEntry:
    """One resolved guidance text pair."""

    create_when: str
    never_create_when: str


@dataclass(frozen=True)
class GuidanceOverlay:
    """Immutable guidance lookup, keyed by :class:`GuidanceKey`.

    An empty overlay is a no-op: every lookup misses, so callers keep whatever text the
    ontology module shipped inline. Keys absent from a given layer pass through unchanged;
    they are not errors.
    """

    entries: Mapping[GuidanceKey, GuidanceEntry] = field(default_factory=dict)
    context_entries: Mapping[GuidanceContextKey, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.entries and not self.context_entries

    def get(self, key: GuidanceKey) -> GuidanceEntry | None:
        return self.entries.get(key)

    def context_for(self, key: GuidanceContextKey) -> str | None:
        return self.context_entries.get(key)


@dataclass(frozen=True)
class WorkspaceGuidance:
    """Alias-independent, workspace-scope guidance: one text for the whole workspace level.

    Prepended to every composed guidance chain regardless of meta-ontology — including for a type
    whose alias is unknown — so it is broadest of all. Kept separate from :class:`GuidanceOverlay`
    because it is not keyed on a module alias. One level, one text: the workspace level has no
    sub-nodes to key text by.
    """

    context: str = ""

    def is_empty(self) -> bool:
        return not self.context


def resolved_type_guidance(
    overlay: GuidanceOverlay,
    *,
    module_alias: str,
    concept_kind: ConceptKind,
    type_name: str,
    declared: Mapping[str, object],
) -> tuple[str, str]:
    """The imported ``(create_when, never_create_when)`` for one entity/connection type, falling
    back to whatever the module declares inline — empty in a shipped module, for license reasons.

    One helper for every module loader, so no module can drift into a different precedence or quietly
    skip a concept kind: an imported pair overrides, an absent one leaves the declaration alone.
    """
    entry = overlay.get(GuidanceKey(module_alias, concept_kind, type_name))
    if entry is not None:
        return entry.create_when, entry.never_create_when
    return str(declared.get("create_when", "")), str(declared.get("never_create_when", ""))


def workspace_guidance_from_mapping(data: Mapping[str, object]) -> WorkspaceGuidance:
    """Parse the top-level ``workspace:`` section — a plain string — into a
    :class:`WorkspaceGuidance`. A missing, blank, or non-string section is tolerated by omission
    (never an error)."""
    section = data.get("workspace")
    if not isinstance(section, str) or not section.strip():
        return WorkspaceGuidance()
    return WorkspaceGuidance(context=section.strip())


def guidance_overlay_from_mapping(data: Mapping[str, object]) -> GuidanceOverlay:
    """Parse one already-YAML-loaded guidance-cache file into an overlay.

    Under ``meta_ontologies.<alias>`` the document's **nesting mirrors the module's guidance
    hierarchy**: the alias is the module's root node, and each of its non-reserved keys is a node
    of the next declared level (for archimate-4, a domain), recursively. Every node carries:

    * ``context`` — that node's broader-level guidance text, keyed here by the node path that
      reaches it (see :class:`GuidanceContextKey`);
    * ``entity_types`` / ``connection_types`` — the leaf slots, each type carrying
      ``create_when``/``never_create_when`` and, optionally, the same pair per
      ``specializations.<slug>``. An absent base key means "fall back to module-inline text",
      not "override with empty text". A type slot is read wherever it appears: which node a type
      belongs under is validated against the hierarchy at import (``--strict``), so the runtime
      cache is already clean and this parser never needs the hierarchy — which is derived from
      the very module being built, a cycle it must not depend on.

    Composition along the ancestry path happens later, at serving time. Malformed/missing
    structure is tolerated by omission.
    """
    entries: dict[GuidanceKey, GuidanceEntry] = {}
    context_entries: dict[GuidanceContextKey, str] = {}
    meta_ontologies = data.get("meta_ontologies")
    if not isinstance(meta_ontologies, Mapping):
        return GuidanceOverlay()
    for alias, module_data in meta_ontologies.items():
        if not isinstance(alias, str) or not isinstance(module_data, Mapping):
            continue
        for path, node_data in _walk_nodes(alias, module_data):
            entries.update(_entries_for_node(alias, node_data))
            context = node_data.get(CONTEXT_KEY)
            if isinstance(context, str) and context.strip():
                context_entries[GuidanceContextKey(alias, path)] = context.strip()
    return GuidanceOverlay(entries, context_entries)


def _walk_nodes(
    alias: str, module_data: Mapping[str, object]
) -> list[tuple[tuple[str, ...], Mapping[str, object]]]:
    """Every node in one alias's document, breadth-first, paired with the path that reaches it.

    Iterative rather than recursive so a pathologically deep document degrades into ignored
    nodes instead of a recursion error — malformed structure is tolerated by omission.
    """
    found: list[tuple[tuple[str, ...], Mapping[str, object]]] = []
    pending: deque[tuple[tuple[str, ...], Mapping[str, object]]] = deque([((alias,), module_data)])
    while pending:
        path, node_data = pending.popleft()
        found.append((path, node_data))
        pending.extend(
            ((*path, key), value)
            for key, value in node_data.items()
            if isinstance(key, str) and key not in RESERVED_KEYS and isinstance(value, Mapping)
        )
    return found


def _entries_for_node(alias: str, node_data: Mapping[str, object]) -> dict[GuidanceKey, GuidanceEntry]:
    """The leaf-slot guidance one node carries, across both concept kinds."""
    out: dict[GuidanceKey, GuidanceEntry] = {}
    for section, kind in CONCEPT_SECTIONS.items():
        concept_map = node_data.get(section)
        if not isinstance(concept_map, Mapping):
            continue
        for type_name, type_data in concept_map.items():
            if isinstance(type_name, str) and isinstance(type_data, Mapping):
                out.update(_entries_for_type(alias, kind, type_name, type_data))
    return out


def _entry_from_mapping(data: Mapping[str, object]) -> GuidanceEntry:
    return GuidanceEntry(
        create_when=str(data.get("create_when", "")),
        never_create_when=str(data.get("never_create_when", "")),
    )


def _entries_for_type(
    alias: str, kind: ConceptKind, type_name: str, data: Mapping[str, object]
) -> dict[GuidanceKey, GuidanceEntry]:
    out: dict[GuidanceKey, GuidanceEntry] = {}
    if "create_when" in data or "never_create_when" in data:
        out[GuidanceKey(alias, kind, type_name)] = _entry_from_mapping(data)
    specializations = data.get(SPECIALIZATIONS_KEY)
    if isinstance(specializations, Mapping):
        for slug, spec_data in specializations.items():
            if isinstance(slug, str) and isinstance(spec_data, Mapping):
                out[GuidanceKey(alias, kind, type_name, slug)] = _entry_from_mapping(spec_data)
    return out
