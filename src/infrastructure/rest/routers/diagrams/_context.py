"""Diagram context-building helpers for the diagram GUI router: the REST side of a picture's context, and
the element search and palette rows beside it (`picture_reading.picture_context` reads the picture)."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.application.artifacts.parsing import extract_declared_puml_aliases, normalize_puml_alias
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.modeling.diagram_kind_palette import (
    diagram_kind_connection_types,
    diagram_kind_entity_types,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.picture_reading.picture_context import (
    drawn_entities,
    entity_display_item,
    picture_context_payload,
)
from src.infrastructure.rest.routers.picture_reads import diagram_read, picture_sources
from src.infrastructure.rest.routers.viewpoints._scope import resolve_viewpoint_scope


def declared_aliases_in_puml(puml: str) -> set[str]:
    return extract_declared_puml_aliases(puml)


def puml_contains(d: DiagramRecord, *aliases: str) -> bool:
    try:
        puml = d.path.read_text(encoding="utf-8")
        return all(normalize_puml_alias(a) in declared_aliases_in_puml(puml) for a in aliases)
    except OSError:
        return False


def diagram_entities_and_puml(
    diag_rec: DiagramRecord, catalogs: RuntimeCatalogs
) -> tuple[list[dict[str, Any]], str]:
    try:
        puml = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        return [], ""
    return drawn_entities(picture_sources(catalogs), diag_rec, puml), puml


def candidate_connections_for_entities(repo: Any, entity_ids: list[str]) -> list[dict[str, Any]]:
    return repo.candidate_connections_for_entities(entity_ids)


def diagram_context_payload(diag_rec: DiagramRecord, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    diagram = diagram_read(diag_rec.artifact_id, catalogs)
    try:
        puml = diag_rec.path.read_text(encoding="utf-8")
    except OSError:
        puml = ""
    return {"diagram": diagram, **picture_context_payload(
        picture_sources(catalogs), diag_rec, puml, read_entities=diagram.get("diagram_entities") or {},
    )}


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
