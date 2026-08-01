"""Diagram context-building helpers for the diagram GUI router."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache as _lru_cache
from typing import TYPE_CHECKING, Any

from src.application._diagram_entity_extraction import (
    extract_diagram_connections,
    extract_diagram_entities,
)
from src.application.artifact_parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.application.entity_type_predicates import is_internal_entity_type
from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._viewpoint_scope import resolve_viewpoint_scope

if TYPE_CHECKING:
    from src.application.runtime_catalogs import RuntimeCatalogs


@_lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def _workspace_entity_types(catalogs: RuntimeCatalogs, diagram_type: str) -> frozenset[str]:
    """Workspace-scoped entity types for a diagram type (e.g. datatype 'classifier').

    Diagram-context extraction must use the same scoping the verifier and candidate
    repository use, so a workspace-scoped diagram entity resolves to its canonical
    artifact id (``CLF@…``) — which exists in the index and loads detail — rather than a
    diagram-local ``{diagram}#{type}/{id}`` id that has no standalone file.
    """
    from src.application.verification._verifier_contribution_runner import (  # noqa: PLC0415
        workspace_types_from_catalogs,
    )

    return workspace_types_from_catalogs(catalogs).get(diagram_type, frozenset())


def declared_aliases_in_puml(puml: str) -> set[str]:
    return extract_declared_puml_aliases(puml)


def puml_contains(d: DiagramRecord, *aliases: str) -> bool:
    try:
        puml = d.path.read_text(encoding="utf-8")
        return all(normalize_puml_alias(a) in declared_aliases_in_puml(puml) for a in aliases)
    except OSError:
        return False


def entity_display_item(rec: EntityRecord, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    ontology = catalogs.module_catalog.ontology_for_entity_type(EntityTypeName(rec.artifact_type))
    section_id = ontology.display_section_id if ontology else "archimate"
    arch_data: dict[str, Any] = {}
    raw_block = rec.display_blocks.get(section_id, "")
    if raw_block and ontology:
        parsed = ontology.extract_display_section(raw_block)
        if parsed:
            arch_data = parsed
    return {
        "artifact_id": rec.artifact_id,
        "name": rec.name,
        "artifact_type": rec.artifact_type,
        "domain": rec.domain,
        "subdomain": rec.subdomain,
        "status": rec.status,
        "display_alias": rec.display_alias,
        "element_type": rec.artifact_type,
        "element_label": str(arch_data.get("label") or rec.name),
        # Diagram-owned constructs (swimlanes, lifelines, actions, …) are pickable in
        # diagram contexts but must never outrank — or be confusable with — model
        # entities, so every display surface can partition on this flag.
        "diagram_internal": rec.host_diagram_id is not None,
    }


def diagram_entities_and_puml(
    repo: Any, diag_rec: DiagramRecord, catalogs: RuntimeCatalogs
) -> tuple[list[dict[str, Any]], str]:
    try:
        puml = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        return [], ""
    aliases = declared_aliases_in_puml(puml)
    ws = _workspace_entity_types(catalogs, diag_rec.diagram_type)
    records = {rec.artifact_id: rec for rec in repo.list_entities()}
    records.update({rec.artifact_id: rec for rec in extract_diagram_entities(diag_rec, ws)})
    entities = []
    for rec in records.values():
        # Diagram-only entities from a *different* diagram must never bleed in.
        if rec.host_diagram_id is not None and rec.host_diagram_id != diag_rec.artifact_id:
            continue
        is_owned = rec.host_diagram_id == diag_rec.artifact_id
        if is_owned or (rec.display_alias and normalize_puml_alias(rec.display_alias) in aliases):
            row = s.entity_to_summary(rec)
            row["display_alias"] = rec.display_alias
            entities.append(row)
    ordered_domains = catalogs.ontology.domain_order()
    entities.sort(
        key=lambda e: (
            ordered_domains.index(e["domain"]) if e["domain"] in ordered_domains else 99,
            e["name"],
        )
    )
    return entities, puml


def candidate_connections_for_entities(repo: Any, entity_ids: list[str]) -> list[dict[str, Any]]:
    return repo.candidate_connections_for_entities(entity_ids)


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


def diagram_context_payload(repo: Any, diag_rec: DiagramRecord, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    from src.infrastructure.gui.routers.diagrams import _read_diagram_impl  # noqa: PLC0415

    version = repo.read_model_version()
    diagram = _read_diagram_impl(diag_rec.artifact_id, catalogs)
    entities, puml = diagram_entities_and_puml(repo, diag_rec, catalogs)
    entity_ids = [str(entity["artifact_id"]) for entity in entities]
    ws = _workspace_entity_types(catalogs, diag_rec.diagram_type)
    extracted_entities = {rec.artifact_id: rec for rec in extract_diagram_entities(diag_rec, ws)}
    in_diagram = {}
    for entity in entities:
        entity_id = str(entity["artifact_id"])
        rec = repo.get_entity(entity_id) or extracted_entities.get(entity_id)
        if rec is not None:
            in_diagram[entity_id] = rec
    explicit_pairs = parse_explicit_connection_pairs(puml)
    raw_el = diag_rec.extra.get("edge-labels") if diag_rec.extra else None
    edge_labels: dict[str, str] = dict(raw_el) if isinstance(raw_el, dict) else {}
    connections: list[dict[str, Any]] = []
    seen: set[str] = set()
    connection_records = {conn.artifact_id: conn for conn in repo.list_connections()}
    connection_records.update({
        conn.artifact_id: conn for conn in extract_diagram_connections(diag_rec, ws)
    })
    for conn in connection_records.values():
        if conn.artifact_id in seen:
            continue
        src = in_diagram.get(conn.source)
        tgt = in_diagram.get(conn.target)
        if src is None or tgt is None:
            continue
        sa = normalize_puml_alias(src.display_alias or "")
        ta = normalize_puml_alias(tgt.display_alias or "")
        is_owned = conn.path == diag_rec.path and "#conn/" in conn.artifact_id
        if not is_owned and (sa, ta) not in explicit_pairs and (ta, sa) not in explicit_pairs:
            continue
        if (sa, ta) in explicit_pairs:
            edge_key = f"{sa}:{ta}"
        else:
            edge_key = f"{ta}:{sa}"
        d = s.connection_to_dict(conn)
        d["source_name"] = src.name
        d["target_name"] = tgt.name
        d["source_alias"] = sa
        d["target_alias"] = ta
        d["edge_key"] = edge_key
        d["edge_label_override"] = edge_labels.get(edge_key)
        connections.append(d)
        seen.add(conn.artifact_id)
    raw_de = diag_rec.extra.get("diagram-entities") if diag_rec.extra else None
    diagram_entities: dict[str, Any] = raw_de if isinstance(raw_de, dict) else {}
    dt = catalogs.diagram_types.find_diagram_type(diag_rec.diagram_type)
    type_extras = dt.build_context_extras(repo, diag_rec.artifact_id, diagram_entities) if dt else {}
    return {
        "diagram": diagram,
        "entities": entities,
        "connections": connections,
        "candidate_connections": candidate_connections_for_entities(repo, entity_ids),
        "suggested_entities": hop_suggestions(repo, entity_ids, catalogs, max_hops=2, limit_per_hop=25),
        "explicit_connection_pairs": [list(pair) for pair in sorted(explicit_pairs)],
        "generation": version.generation,
        "etag": version.etag,
        # Namespaced, not merged: the envelope declares its own fields, and a hook free to add a key
        # beside them would make the whole response a contract promising nothing.
        "type_extras": type_extras or None,
    }


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
            and not is_internal_entity_type(rec.artifact_type, _catalogs().ontology)
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


def fuzzy_entity_hits(
    repo: Any,
    q: str,
    limit: int,
    excluded: set[str],
    catalogs: RuntimeCatalogs,
    accepted_entity_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    query = q.strip().lower()
    if not query or limit <= 0:
        return []
    scored: list[tuple[float, EntityRecord]] = []
    for rec in repo.list_entities():
        if is_internal_entity_type(rec.artifact_type, _catalogs().ontology) or rec.artifact_id in excluded:
            continue
        if accepted_entity_types is not None and rec.artifact_type not in accepted_entity_types:
            continue
        haystack = " ".join((rec.name, rec.artifact_type, rec.domain, rec.subdomain, rec.content_text[:400]))
        score = SequenceMatcher(None, query, haystack.lower()).ratio()
        if score >= 0.35:
            scored.append((score, rec))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entity_display_item(rec, catalogs) for _, rec in scored[:limit]]


def diagram_kind_entity_type_items(
    diagram_type: str, catalogs: RuntimeCatalogs, *, viewpoint: str | None = None
) -> list[dict[str, Any]]:
    kind = catalogs.diagram_types.get_diagram_type(diagram_type)
    viewpoint_scope = resolve_viewpoint_scope(viewpoint, catalogs)
    ordered_domains = catalogs.ontology.domain_order()
    items = [
        {
            "artifact_type": artifact_type,
            "prefix": info.prefix,
            "domain": info.hierarchy[0] if info.hierarchy else "",
            "classes": list(info.classes),
        }
        for artifact_type, info in kind.effective_entity_types().items()
        if not info.internal and (viewpoint_scope is None or viewpoint_scope.admits_entity_type(artifact_type, info))
    ]
    items.sort(
        key=lambda item: (
            ordered_domains.index(str(item["domain"])) if item["domain"] in ordered_domains else 99,
            item["artifact_type"],
        )
    )
    return items


def diagram_kind_connection_type_items(
    diagram_type: str, catalogs: RuntimeCatalogs, *, viewpoint: str | None = None
) -> list[dict[str, Any]]:
    kind = catalogs.diagram_types.get_diagram_type(diagram_type)
    viewpoint_scope = resolve_viewpoint_scope(viewpoint, catalogs)
    items = [
        {
            "connection_type": connection_type,
            "conn_lang": info.conn_lang,
            "symmetric": info.symmetric,
            "classes": list(info.classes),
        }
        for connection_type, info in kind.effective_connection_types().items()
        if viewpoint_scope is None or viewpoint_scope.admits_connection_type(connection_type)
    ]
    items.sort(key=lambda item: item["connection_type"])
    return items
