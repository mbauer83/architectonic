"""What an editor reads about a picture beside the diagram it draws: its elements and relations, what the model
relates them to, and what lies one and two steps away.

One reading for every picture an editor opens on: a stored diagram's, and a candidate's, which starts from a
stored diagram or from a view generated from what the candidate reads over. *reach* widens what the relations
and the neighbourhood are read around beyond what the picture draws: a candidate reads over elements its
starting picture may not draw yet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from src.application._diagram_entity_extraction import (
    HELD_CONNECTION_MARK,
    NOTHING_HELD,
    HeldRecordScope,
    axis_entity_ids,
    extract_diagram_connections,
    extract_diagram_entities,
)
from src.application.artifacts.parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_contribution_runner import held_record_scopes_from_catalogs
from src.domain.artifact_id import stable_conn_id
from src.domain.diagrams.element_correspondence import element_correspondences
from src.domain.diagrams.relation_key import labels_by_relation
from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.infrastructure.picture_reading.derived_entities import derived_entity_rows
from src.infrastructure.picture_reading.sources import PictureSources
from src.infrastructure.rendering.archimate_occurrences import drawn_labels_by_instance


def held_record_scope(catalogs: RuntimeCatalogs, diagram_type: str) -> HeldRecordScope:
    """What this diagram's type says it holds — the same reading the index and the verifier use.

    So a workspace-scoped record resolves to its canonical id (``CLF@…``), which exists in the index
    and loads detail, rather than a ``{diagram}#{type}/{id}`` id with no standalone file; and a
    statement about instances (an ArchiMate occurrence) is never taken for a record.
    """
    return held_record_scopes_from_catalogs(catalogs).get(diagram_type, NOTHING_HELD)


def element_label(rec: EntityRecord, catalogs: RuntimeCatalogs) -> str:
    """What the element is called where it is drawn: its display block's label, else its name.

    One resolution for both the picker row and the diagram's own entity row, so the two cannot show
    the same element under two labels.
    """
    ontology = catalogs.module_catalog.ontology_for_entity_type(EntityTypeName(rec.artifact_type))
    section_id = ontology.display_section_id if ontology else "archimate"
    arch_data: dict[str, Any] = {}
    raw_block = rec.display_blocks.get(section_id, "")
    if raw_block and ontology:
        parsed = ontology.extract_display_section(raw_block)
        if parsed:
            arch_data = parsed
    return str(arch_data.get("label") or rec.name)


def entity_display_item(rec: EntityRecord, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    return {
        "artifact_id": rec.artifact_id,
        "name": rec.name,
        "artifact_type": rec.artifact_type,
        "domain": rec.domain,
        "subdomain": rec.subdomain,
        "status": rec.status,
        "display_alias": rec.display_alias,
        "element_type": rec.artifact_type,
        "element_label": element_label(rec, catalogs),
        # Diagram-owned constructs (swimlanes, lifelines, actions, …) are pickable in
        # diagram contexts but must never outrank — or be confusable with — model
        # entities, so every display surface can partition on this flag.
        "diagram_internal": rec.host_diagram_id is not None,
    }


def drawn_entities(sources: PictureSources, diag_rec: DiagramRecord, puml: str) -> list[dict[str, Any]]:
    """Each entity the picture *puml* of *diag_rec* draws, as the editor lists it, in domain order."""
    catalogs = sources.catalogs
    aliases = extract_declared_puml_aliases(puml)
    scope = held_record_scope(catalogs, diag_rec.diagram_type)
    records = {rec.artifact_id: rec for rec in sources.repo.list_entities()}
    records.update({rec.artifact_id: rec for rec in extract_diagram_entities(diag_rec, scope)})
    # What each element on this diagram says it corresponds to, read once through the module that
    # owns the `bindings:` block rather than walked here.
    correspondences = element_correspondences(diag_rec.extra.get("bindings"))
    # A diagram's members are what its body declares, and what it lays out on axes — a matrix has no
    # body to declare them in, and listed none (B90).
    axis_members = set(axis_entity_ids(diag_rec.extra or {}))
    entities = []
    for rec in records.values():
        # Diagram-only entities from a *different* diagram must never bleed in.
        if rec.host_diagram_id is not None and rec.host_diagram_id != diag_rec.artifact_id:
            continue
        is_owned = rec.host_diagram_id == diag_rec.artifact_id
        on_an_axis = rec.artifact_id in axis_members
        if is_owned or on_an_axis or (rec.display_alias and normalize_puml_alias(rec.display_alias) in aliases):
            row = sources.entity_row(rec)
            row["display_alias"] = rec.display_alias
            row["element_label"] = element_label(rec, catalogs)
            declared = correspondences.get(rec.display_alias)
            if declared:
                row["bindings"] = [
                    {
                        "correspondence_kind": item.correspondence_kind,
                        "artifact_id": item.entity_id,
                        # Resolved from what this route already holds: a client fetching each target
                        # to render a label would issue one request per bound element. None where the
                        # id resolves to nothing — a dangling binding should look like one.
                        "name": getattr(records.get(item.entity_id), "name", None),
                    }
                    for item in declared
                ]
            entities.append(row)
    ordered_domains = catalogs.ontology.domain_order()
    entities.sort(
        key=lambda e: (
            ordered_domains.index(e["domain"]) if e["domain"] in ordered_domains else 99,
            e["name"],
        )
    )
    return entities


def parse_explicit_connection_pairs(puml: str) -> set[tuple[str, str]]:
    """Return (src_alias, tgt_alias) pairs for visible connection lines in PUML."""
    _conn_re = re.compile(
        r"^\s*(\w+)\s+"
        r"([-.*|o<>][^\s]*[-.*|o<>])"
        r"\s+(\w+)"
    )
    _macro_re = re.compile(
        r"^\s*Rel_[A-Za-z0-9]+(?:_(?:Up|Down|Left|Right))?"
        r"\(\s*(\w+)\s*,\s*(\w+)"
    )
    _gsn_macro_re = re.compile(
        r"^\s*\$Gsn(?:SupportedBy|InContextOf)\(\s*(\w+)\s*,\s*(\w+)\s*\)"
    )
    pairs: set[tuple[str, str]] = set()
    for line in puml.splitlines():
        stripped = line.strip()
        if stripped.startswith("'") or "[hidden]" in stripped:
            continue
        m = _conn_re.match(line)
        if m:
            pairs.add((normalize_puml_alias(m.group(1)), normalize_puml_alias(m.group(3))))
            continue
        macro = _macro_re.match(line)
        if macro:
            pairs.add((normalize_puml_alias(macro.group(1)), normalize_puml_alias(macro.group(2))))
            continue
        gsn_macro = _gsn_macro_re.match(line)
        if gsn_macro:
            pairs.add((normalize_puml_alias(gsn_macro.group(1)), normalize_puml_alias(gsn_macro.group(2))))
    return pairs


def hop_suggestions(
    repo: Any,
    entity_ids: list[str],
    catalogs: RuntimeCatalogs,
    *,
    max_hops: int,
    limit_per_hop: int,
) -> list[dict[str, Any]]:
    ordered_domains = catalogs.ontology.domain_order()
    frontier = set(entity_ids)
    visited = set(entity_ids)
    groups: list[dict[str, Any]] = []
    for hop in range(1, max(max_hops, 0) + 1):
        next_frontier: set[str] = set()
        for entity_id in frontier:
            context = repo.read_entity_context(entity_id)
            if context is None:
                continue
            for bucket in ("outbound", "inbound", "symmetric"):
                for conn in context["connections"][bucket]:
                    other_id = str(conn["other_entity_id"])
                    if other_id not in visited:
                        next_frontier.add(other_id)
        next_frontier.difference_update(visited)
        if not next_frontier:
            break
        items = [
            entity_display_item(rec, catalogs)
            for entity_id in sorted(next_frontier)
            if (rec := repo.get_entity(entity_id)) is not None
            and not is_internal_entity_type(rec.artifact_type, catalogs.ontology)
        ]
        items.sort(
            key=lambda item: (
                ordered_domains.index(item["domain"]) if item["domain"] in ordered_domains else 99,
                item["name"],
            )
        )
        if items:
            groups.append({"hop": hop, "items": items[:limit_per_hop]})
        visited.update(next_frontier)
        frontier = next_frontier
    return groups


def picture_context_payload(
    sources: PictureSources, record: DiagramRecord, puml: str, *,
    read_entities: Mapping[str, Any], reach: Iterable[str] = (),
) -> dict[str, Any]:
    """Everything the context read answers about the picture *puml* of *record*, but the diagram itself.

    *read_entities* are the diagram-entities as the diagram read serves them, which the type's projection reads.
    """
    repo, catalogs = sources.repo, sources.catalogs
    version = repo.read_model_version()
    entities = drawn_entities(sources, record, puml)
    entity_ids = [str(entity["artifact_id"]) for entity in entities]
    scope = held_record_scope(catalogs, record.diagram_type)
    extracted = {rec.artifact_id: rec for rec in extract_diagram_entities(record, scope)}
    in_picture = {
        entity_id: rec for entity_id in entity_ids
        if (rec := repo.get_entity(entity_id) or extracted.get(entity_id)) is not None
    }
    explicit_pairs = parse_explicit_connection_pairs(puml)
    raw_entities = record.extra.get("diagram-entities") if record.extra else None
    diagram_entities: dict[str, Any] = raw_entities if isinstance(raw_entities, dict) else {}
    dt = catalogs.diagram_types.find_diagram_type(record.diagram_type)
    type_extras = dt.build_context_extras(repo, record.artifact_id, diagram_entities) if dt else {}
    # What the type's projection draws and as what, from the diagram-entities the read serves: the
    # same rows the preview answers, so an editor is right before its first preview.
    root = sources.repo_root
    derived = (
        derived_entity_rows(dt, record.diagram_type, dict(read_entities), root)
        if dt is not None and root is not None else None
    )
    reached = list(dict.fromkeys([*entity_ids, *reach]))
    return {
        "entities": entities,
        "connections": _drawn_connections(sources, record, in_picture, explicit_pairs, scope),
        # What each instance is called in the body as it stands, by instance id. Read off the body
        # rather than derived, because a hand-laid body may call an element something its record
        # does not — and an editor that cannot see that would revert it on the first save.
        "drawn_labels": drawn_labels_by_instance(puml, diagram_entities, in_picture),
        "candidate_connections": repo.candidate_connections_for_entities(reached),
        "suggested_entities": hop_suggestions(repo, reached, catalogs, max_hops=2, limit_per_hop=25),
        "explicit_connection_pairs": [list(pair) for pair in sorted(explicit_pairs)],
        "generation": version.generation,
        "etag": version.etag,
        # Namespaced, not merged: the envelope declares its own fields, and a hook free to add a key
        # beside them would make the whole response a contract promising nothing.
        "type_extras": type_extras or None,
        "derived_entities": derived,
    }


def _drawn_connections(
    sources: PictureSources, record: DiagramRecord, in_picture: Mapping[str, Any],
    explicit_pairs: set[tuple[str, str]], scope: HeldRecordScope,
) -> list[dict[str, Any]]:
    """Each relation the picture draws between two of its elements, as the editor lists it."""
    edge_labels = labels_by_relation(record.extra.get("edge-labels") if record.extra else None)
    connection_records = {conn.artifact_id: conn for conn in sources.repo.list_connections()}
    connection_records.update({conn.artifact_id: conn for conn in extract_diagram_connections(record, scope)})
    connections: list[dict[str, Any]] = []
    for conn in connection_records.values():
        src, tgt = in_picture.get(conn.source), in_picture.get(conn.target)
        if src is None or tgt is None:
            continue
        sa = normalize_puml_alias(src.display_alias or "")
        ta = normalize_puml_alias(tgt.display_alias or "")
        is_owned = conn.path == record.path and HELD_CONNECTION_MARK in conn.artifact_id
        if not is_owned and (sa, ta) not in explicit_pairs and (ta, sa) not in explicit_pairs:
            continue
        # The key a statement about this drawn relation is filed under: a connection the diagram
        # holds by its id within the diagram, a model connection by its own.
        edge_key = conn.artifact_id.partition(HELD_CONNECTION_MARK)[2] if is_owned else stable_conn_id(conn.artifact_id)
        d = sources.connection_row(conn)
        d.update(source_name=src.name, target_name=tgt.name, source_alias=sa, target_alias=ta, edge_key=edge_key,
                 edge_label_override=edge_labels.get(edge_key))
        connections.append(d)
    return connections
