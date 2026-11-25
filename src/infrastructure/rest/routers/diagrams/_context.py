"""Diagram context-building helpers for the diagram GUI router."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from src.application._diagram_entity_extraction import (
    NOTHING_HELD,
    HeldRecordScope,
    axis_entity_ids,
    extract_diagram_entities,
)
from src.application.artifacts.parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.modeling.diagram_kind_palette import (
    diagram_kind_connection_types,
    diagram_kind_entity_types,
)
from src.application.modeling.proposal_standing import standing_subject
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.diagrams.element_correspondence import element_correspondences
from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.viewpoints._scope import resolve_viewpoint_scope


def _held_record_scope(catalogs: RuntimeCatalogs, diagram_type: str) -> HeldRecordScope:
    """What this diagram's type says it holds — the same reading the index and the verifier use.

    So a workspace-scoped record resolves to its canonical id (``CLF@…``), which exists in the index
    and loads detail, rather than a ``{diagram}#{type}/{id}`` id with no standalone file; and a
    statement about instances (an ArchiMate occurrence) is never taken for a record.
    """
    from src.application.verification._verifier_contribution_runner import (  # noqa: PLC0415
        held_record_scopes_from_catalogs,
    )

    return held_record_scopes_from_catalogs(catalogs).get(diagram_type, NOTHING_HELD)


def declared_aliases_in_puml(puml: str) -> set[str]:
    return extract_declared_puml_aliases(puml)


def puml_contains(d: DiagramRecord, *aliases: str) -> bool:
    try:
        puml = d.path.read_text(encoding="utf-8")
        return all(normalize_puml_alias(a) in declared_aliases_in_puml(puml) for a in aliases)
    except OSError:
        return False


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


def diagram_entities_and_puml(
    repo: Any, diag_rec: DiagramRecord, catalogs: RuntimeCatalogs
) -> tuple[list[dict[str, Any]], str]:
    try:
        puml = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        return [], ""
    return drawn_entities(repo, diag_rec, puml, catalogs), puml


def drawn_entities(repo: Any, diag_rec: DiagramRecord, puml: str, catalogs: RuntimeCatalogs) -> list[dict[str, Any]]:
    """Each entity the picture *puml* of *diag_rec* draws, as the editor lists it, in domain order."""
    aliases = declared_aliases_in_puml(puml)
    scope = _held_record_scope(catalogs, diag_rec.diagram_type)
    records = {rec.artifact_id: rec for rec in repo.list_entities()}
    records.update({rec.artifact_id: rec for rec in extract_diagram_entities(diag_rec, scope)})
    # What each element on this diagram says it corresponds to, read once through the module that
    # owns the `bindings:` block rather than walked here.
    correspondences = element_correspondences(diag_rec.extra.get("bindings"))
    # A diagram's members are what its body declares, and what it lays out on axes — a matrix has no
    # body to declare them in, and listed none (B90).
    axis_members = set(axis_entity_ids(diag_rec.extra or {}))
    entities = []
    standing_of = s.baseline_standing_reader()
    for rec in records.values():
        # Diagram-only entities from a *different* diagram must never bleed in.
        if rec.host_diagram_id is not None and rec.host_diagram_id != diag_rec.artifact_id:
            continue
        is_owned = rec.host_diagram_id == diag_rec.artifact_id
        on_an_axis = rec.artifact_id in axis_members
        if is_owned or on_an_axis or (rec.display_alias and normalize_puml_alias(rec.display_alias) in aliases):
            row = s.entity_to_summary(rec, standing=standing_of(standing_subject(rec)))
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
    from src.infrastructure.rest.routers.diagrams._picture_context import picture_context_payload  # noqa: PLC0415
    from src.infrastructure.rest.routers.diagrams.router import _read_diagram_impl  # noqa: PLC0415

    diagram = _read_diagram_impl(diag_rec.artifact_id, catalogs)
    try:
        puml = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        puml = ""
    return {"diagram": diagram, **picture_context_payload(
        repo, diag_rec, puml, catalogs, read_entities=diagram.get("diagram_entities") or {},
    )}


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
            and not is_internal_entity_type(rec.artifact_type, process_runtime_catalogs().ontology)
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
        ontology = process_runtime_catalogs().ontology
        if is_internal_entity_type(rec.artifact_type, ontology) or rec.artifact_id in excluded:
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
    """The palette, with the `?viewpoint=` slug resolved to a scope here.

    A thin adapter over `application.modeling.diagram_kind_palette`, which is where the composition
    moved so authoring guidance can answer with the same lists. What stays is the HTTP-shaped half:
    turning a slug into a scope, and answering 404 when it names nothing.
    """
    return diagram_kind_entity_types(
        diagram_type, catalogs, scope=resolve_viewpoint_scope(viewpoint, catalogs)
    )


def diagram_kind_connection_type_items(
    diagram_type: str, catalogs: RuntimeCatalogs, *, viewpoint: str | None = None
) -> list[dict[str, Any]]:
    return diagram_kind_connection_types(
        diagram_type, catalogs, scope=resolve_viewpoint_scope(viewpoint, catalogs)
    )
