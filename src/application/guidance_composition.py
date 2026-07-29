"""Compose broader-level guidance context along a concept's ancestry path (v2 layered guidance).

Serving a concept's authoring guidance additively layers the context attached to each ancestor
in its module's guidance hierarchy, broadest first (e.g. the domain context sitting above an
entity type, then the type, then a specialization). The per-type/-specialization
``create_when``/``never_create_when`` text is served separately and unchanged; this use case
only assembles the NEW ordered context chain, so existing guidance consumers are unaffected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.guidance.guidance import GuidanceContextKey, GuidanceOverlay
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy
from src.domain.guidance.guidance_hierarchy_source import (
    ENTITY_TYPE_LEVEL,
    SPECIALIZATION_LEVEL,
    specialization_node_id,
)


@dataclass(frozen=True)
class ComposedContext:
    """One resolved context layer in a concept's ancestry chain."""

    level_id: str
    node_id: str
    text: str


def compose_context(
    *,
    module_alias: str,
    hierarchy: GuidanceHierarchy,
    overlay: GuidanceOverlay,
    leaf_level_id: str,
    leaf_node_id: str,
) -> tuple[ComposedContext, ...]:
    """The context layers along the ancestry of ``(leaf_level_id, leaf_node_id)``, broadest first.

    Only ancestors that actually carry context text appear (a level with no context is skipped,
    not rendered as an empty layer). Returns ``()`` for an unknown node or an empty overlay.

    The overlay keys context by node path, since the guidance document's nesting is that path;
    the ancestry walked here is what turns a path back into the labelled ``level_id`` the layer
    carries.
    """
    layers: list[ComposedContext] = []
    path: tuple[str, ...] = ()
    for node in hierarchy.ancestry(leaf_level_id, leaf_node_id):
        path = (*path, node.node_id)
        text = overlay.context_for(GuidanceContextKey(module_alias, path))
        if text:
            layers.append(ComposedContext(node.level_id, node.node_id, text))
    return tuple(layers)


def compose_type_context(
    *,
    module_alias: str,
    hierarchy: GuidanceHierarchy,
    overlay: GuidanceOverlay,
    type_name: str,
    specialization: str | None = None,
) -> tuple[ComposedContext, ...]:
    """Context chain for an entity type, or for one of its specializations when ``specialization``
    is given — bridging the serving vocabulary (type name + specialization slug) to the
    ancestry lookup (a specialization's node id is qualified ``type::slug``)."""
    if specialization:
        return compose_context(
            module_alias=module_alias,
            hierarchy=hierarchy,
            overlay=overlay,
            leaf_level_id=SPECIALIZATION_LEVEL,
            leaf_node_id=specialization_node_id(type_name, specialization),
        )
    return compose_context(
        module_alias=module_alias,
        hierarchy=hierarchy,
        overlay=overlay,
        leaf_level_id=ENTITY_TYPE_LEVEL,
        leaf_node_id=type_name,
    )


@dataclass(frozen=True)
class GuidanceContextView:
    """Serving-time carrier on RuntimeCatalogs: composes a type's/specialization's ancestry
    context without the caller needing overlays or hierarchies.

    Keyed on the meta-ontology ALIAS (the guidance-document alias, e.g. ``archimate-4``) — which
    is what the overlay's context keys use — NOT the module's registry name (``archimate-4-0``).
    ``sources`` holds each alias's (hierarchy, overlay); ``type_alias`` maps an entity type name
    to its owning alias. ``workspace`` holds the alias-independent, workspace-scope layer (level_id
    ``"workspace"``) prepended to EVERY result — including for a type whose alias is unknown — so
    workspace guidance is always the broadest of all. An empty view (no workspace, no sources) is
    a no-op — every lookup returns ``()``.
    """

    sources: Mapping[str, tuple[GuidanceHierarchy, GuidanceOverlay]] = field(default_factory=dict)
    type_alias: Mapping[str, str] = field(default_factory=dict)
    workspace: tuple[ComposedContext, ...] = ()

    def context_for(self, type_name: str, specialization: str | None = None) -> tuple[ComposedContext, ...]:
        alias = self.type_alias.get(type_name)
        if alias is None or alias not in self.sources:
            return self.workspace
        hierarchy, overlay = self.sources[alias]
        return (
            *self.workspace,
            *compose_type_context(
                module_alias=alias,
                hierarchy=hierarchy,
                overlay=overlay,
                type_name=type_name,
                specialization=specialization,
            ),
        )
