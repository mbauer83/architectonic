"""GUI helper: PUML body generation and ephemeral preview rendering.

Used by the GUI REST server to build ArchiMate diagram PUML from a set of
entity + connection records chosen via the create-diagram form, and to render
transient PNG/SVG previews without persisting any files to the model.

Both the PUML generation and the PlantUML rendering reuse the same conventions
as the ``model_create_diagram`` / ``model_verify_file`` MCP tools (shared library
code from ``src.common``).
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.diagram_type_registry import get_diagram_type
from src.infrastructure.rendering._diagram_nesting import build_visual_nesting
from src.infrastructure.rendering.puml_runtime import (
    render_puml_preview as render_puml_preview,
)
from src.infrastructure.rendering.puml_runtime import render_puml_svg as render_puml_svg


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


@lru_cache(maxsize=None)
def junction_type_names() -> frozenset[str]:
    """The entity types the ontology classes as junctions. Shared with the selection rule, which
    needs the same answer to decide whether an unselected endpoint may be pulled into a diagram."""
    return frozenset(_registry().entity_types_with_class(ElementClassName("junction")))


@lru_cache(maxsize=None)
def _nesting_conn_types() -> frozenset[str]:
    return frozenset(_registry().connection_types_with_class("nesting"))


@lru_cache(maxsize=None)
def _flow_conn_types() -> frozenset[str]:
    return frozenset(_registry().connection_types_with_class("dynamic"))


def inject_archimate_includes(puml_body: str, repo_root: Path) -> str:
    from src.infrastructure.rendering.generic_puml_renderer import inject_archimate_includes as _inject

    return _inject(puml_body, repo_root)


@lru_cache(maxsize=1)
def _entity_type_order() -> list[str]:
    return list(_registry().all_entity_types())


def _entity_stereotype_key(entity: EntityRecord) -> str:
    """Return the PlantUML stereotype key for *entity*.

    Derived from ``artifact_type`` using snake_case convention.
    """
    return entity.artifact_type.replace("-", "_")


def _pluralize_label(label: str) -> str:
    words = label.split()
    if not words:
        return label
    last = words[-1]
    lower = last.lower()
    if lower.endswith(("s", "x", "z")) or lower.endswith(("ch", "sh")):
        last = last + "es"
    elif lower.endswith("y") and (len(lower) == 1 or lower[-2] not in "aeiou"):
        last = last[:-1] + "ies"
    else:
        last = last + "s"
    words[-1] = last
    return " ".join(words)


def _type_group_label(entity: EntityRecord) -> str:
    return _pluralize_label(entity.artifact_type.replace("-", " ").title())


def _ordered_type_groups(entities: list[EntityRecord]) -> list[tuple[str, list[EntityRecord]]]:
    grouped: dict[str, list[EntityRecord]] = defaultdict(list)
    labels: dict[str, str] = {}
    for entity in entities:
        grouped[entity.artifact_type].append(entity)
        labels.setdefault(entity.artifact_type, _type_group_label(entity))
    ordered_types = [t for t in _entity_type_order() if t in grouped]
    for artifact_type in grouped:
        if artifact_type not in ordered_types:
            ordered_types.append(artifact_type)
    return [(labels[artifact_type], grouped[artifact_type]) for artifact_type in ordered_types]


def _build_visual_nesting(
    entity_records: list[EntityRecord],
    connection_records: list[ConnectionRecord],
    alias_by_id: dict[str, str],
    entity_by_alias: dict[str, EntityRecord],
) -> tuple[dict[str, list[EntityRecord]], set[str]]:
    entity_order = {
        normalize_puml_alias(entity.display_alias): index
        for index, entity in enumerate(entity_records)
        if entity.display_alias
    }
    structural_edges: list[tuple[str, str]] = []
    neighbor_edges: list[tuple[str, str]] = []
    for conn in connection_records:
        src_alias = alias_by_id.get(conn.source)
        tgt_alias = alias_by_id.get(conn.target)
        if not src_alias or not tgt_alias:
            continue
        ct = _registry().all_connection_types().get(ConnectionTypeName(conn.conn_type))
        if ct and ct.artifact_type in _nesting_conn_types() and tgt_alias in entity_by_alias:
            structural_edges.append((src_alias, tgt_alias))
            continue
        neighbor_edges.append((src_alias, tgt_alias))

    children_map, nested_aliases = build_visual_nesting(
        item_by_alias=entity_by_alias,
        structural_edges=structural_edges,
        neighbor_edges=neighbor_edges,
        junction_aliases={
            alias for alias, entity in entity_by_alias.items() if entity.artifact_type in junction_type_names()
        },
    )
    for parent_alias, children in children_map.items():
        children.sort(
            key=lambda entity: entity_order.get(normalize_puml_alias(entity.display_alias), len(entity_order))
        )
    return children_map, nested_aliases


def generate_archimate_puml_body(
    name: str,
    entity_records: list[EntityRecord],
    connection_records: list[ConnectionRecord],
    *,
    diagram_type: str = "archimate-business",
    repo_root: Path = Path("."),
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    edge_labels: dict[str, str] | None = None,
    label_attribute: str | None = None,
    authored_groupings: list[dict[str, object]] | None = None,
) -> str:
    diagram_type_mod = get_diagram_type(diagram_type)
    extra: dict[str, object] = {}
    if edge_labels:
        extra["edge_labels"] = edge_labels
    if label_attribute:
        extra["label_attribute"] = label_attribute
    if authored_groupings:
        extra["authored_groupings"] = authored_groupings
    return diagram_type_mod.renderer.render_body(
        name,
        entity_records,
        connection_records,
        diagram_type,
        repo_root,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
        **extra,
    )
