"""Render the `' Connections` section: one arrow line per non-nested connection.

Extracted from GenericPumlRenderer.render_body — same behavior, explicit inputs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.application.artifact_parsing import normalize_puml_alias
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.relationships.relationship_reachability import is_derived_connection_id
from src.infrastructure.rendering._diagram_text import insert_arrow_direction, insert_arrow_line_style
from src.infrastructure.rendering.archimate_relation_rendering import (
    display_connection_label,
    format_influence_polarity,
    format_specializations_guillemet,
)


def render_connection_lines(
    connections: Sequence[ConnectionRecord],
    *,
    alias_by_id: Mapping[str, str],
    children_map: Mapping[str, list[EntityRecord]],
    layout_direction_hints: Mapping[tuple[str, str], str],
    single_domain: bool,
    group_index_by_alias: Mapping[str, int],
    domain_rank_by_alias: Mapping[str, int],
    specialization_catalog: SpecializationCatalog,
    edge_labels: Mapping[str, str] | None,
    nesting_conn_types: frozenset[str],
    connection_info: Callable[[str], ConnectionTypeInfo | None],
    visible_label: Callable[[ConnectionRecord], str],
) -> list[str]:
    conn_lines: list[str] = []
    for conn in connections:
        conn_info = connection_info(conn.conn_type)
        if conn_info and conn.conn_type in nesting_conn_types:
            parent_alias = alias_by_id.get(conn.source, "")
            child_alias = alias_by_id.get(conn.target, "")
            drawn_as_nesting = any(
                normalize_puml_alias(child.display_alias) == child_alias
                for child in children_map.get(parent_alias, ())
            )
            if drawn_as_nesting:
                continue
            # Not nested visually (e.g. the member belongs to an authored group,
            # which wins) — the relation must still be EXPRESSED: draw its arrow.
        src = alias_by_id.get(conn.source)
        tgt = alias_by_id.get(conn.target)
        if not src or not tgt:
            continue
        direction: str | None = layout_direction_hints.get((src, tgt))
        if single_domain:
            src_group = group_index_by_alias.get(src)
            tgt_group = group_index_by_alias.get(tgt)
            if direction is None and src_group is not None and tgt_group is not None and src_group != tgt_group:
                direction = "down" if src_group < tgt_group else "up"
        else:
            src_rank = domain_rank_by_alias.get(src)
            tgt_rank = domain_rank_by_alias.get(tgt)
            if direction is None and src_rank is not None and tgt_rank is not None and src_rank != tgt_rank:
                # The ontology's layer order outranks the arrow's natural rank pull.
                direction = "down" if src_rank < tgt_rank else "up"
        resolved_specs = [
            specialization_catalog.get("connection", conn.conn_type, slug) for slug in conn.specializations
        ]
        # Primary specialization drives notation (arrow line style, marker); the label
        # below shows all of them (§15.2 comma-separated list).
        conn_spec = next((info for info in resolved_specs if info is not None), None)
        arrow = conn_info.puml_arrow if conn_info else "-->"
        if is_derived_connection_id(conn.artifact_id):
            certainty = conn.extra.get("certainty") if isinstance(conn.extra, Mapping) else None
            arrow = insert_arrow_line_style(arrow, "dashed" if certainty == "certain" else "dotted")
        elif conn_spec is not None and conn_spec.notation.line_style:
            arrow = insert_arrow_line_style(arrow, conn_spec.notation.line_style)
        if direction:
            arrow = insert_arrow_direction(arrow, direction)
        override = edge_labels.get(f"{src}:{tgt}") if edge_labels else None
        if override is not None:
            label = override
        else:
            visible = visible_label(conn)
            polarity = format_influence_polarity(conn.conn_type, conn.attributes)
            if polarity:
                visible = f"{polarity} {visible}".strip()
            if conn_spec is not None and conn_spec.notation.label_marker:
                visible = f"{conn_spec.notation.label_marker} {visible}".strip()
            show_stereo = conn_info.show_stereotype if conn_info is not None else True
            if show_stereo:
                label = f"<<{display_connection_label(conn.conn_type)}>>"
                if visible:
                    label = f"{label} {visible}"
            else:
                label = visible
            guillemet = format_specializations_guillemet(
                [info.name for info in resolved_specs if info is not None]
            )
            if guillemet:
                label = f"{label} {guillemet}".strip() if label else guillemet
        if label:
            conn_lines.append(f"{src} {arrow} {tgt} : {label}")
        else:
            conn_lines.append(f"{src} {arrow} {tgt}")
    return conn_lines
