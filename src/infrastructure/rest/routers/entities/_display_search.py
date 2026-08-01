"""Entity-display search — the picker's single backend (WU-A1, decision D-1).

Filters (domain/entity-type) via the shared `EntityFilter` predicate; cursor-paginated with a
stable sort key so pages never skip or duplicate an entity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams._context import entity_display_item, fuzzy_entity_hits
from src.infrastructure.rest.routers.entities._filter import EntityFilter
from src.infrastructure.rest.routers.viewpoints._scope import resolve_viewpoint_scope


def accepted_entity_types(
    diagram_type: str | None, catalogs: RuntimeCatalogs, *, viewpoint: str | None = None
) -> set[str] | None:
    if diagram_type is None:
        return None
    kind = catalogs.diagram_types.find_diagram_type(diagram_type)
    if kind is None:
        raise HTTPException(404, f"Diagram type not found: {diagram_type!r}")
    viewpoint_scope = resolve_viewpoint_scope(viewpoint, catalogs)
    types = {
        str(entity_type)
        for entity_type, info in kind.effective_entity_types().items()
        if viewpoint_scope is None or viewpoint_scope.admits_entity_type(entity_type, info)
    }
    return types if types else None


@dataclass(frozen=True)
class EntityDisplaySearchResult:
    items: list[dict[str, Any]]
    next_cursor: str | None


def entity_display_search_impl(
    q: str,
    limit: int,
    diagram_type: str | None,
    catalogs: RuntimeCatalogs,
    *,
    domains: str | None = None,
    entity_types: str | None = None,
    keywords: str | None = None,
    cursor: str | None = None,
    viewpoint: str | None = None,
) -> EntityDisplaySearchResult:
    repo = s.get_repo()
    ontology = catalogs.ontology
    accepted_types = accepted_entity_types(diagram_type, catalogs, viewpoint=viewpoint)
    entity_filter = EntityFilter.from_params(domains=domains, entity_types=entity_types, keywords=keywords)
    offset = int(cursor) if cursor and cursor.isdigit() else 0

    if not q.strip():
        ordered_domains = ontology.domain_order()
        candidates = [
            rec
            for rec in repo.list_entities()
            if entity_filter.matches(rec, ontology=ontology, accepted_entity_types=accepted_types)
        ]
        candidates.sort(
            key=lambda rec: (
                rec.host_diagram_id is not None,
                ordered_domains.index(rec.domain) if rec.domain in ordered_domains else 99,
                rec.name,
                rec.artifact_id,
            )
        )
        page = candidates[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(candidates) else None
        return EntityDisplaySearchResult(
            items=[entity_display_item(rec, catalogs) for rec in page],
            next_cursor=next_cursor,
        )

    selected_types_raw = entity_filter.entity_types & accepted_types if (
        entity_filter.entity_types and accepted_types is not None
    ) else (entity_filter.entity_types or accepted_types)
    selected_types: set[str] | None = set(selected_types_raw) if selected_types_raw else None
    search_limit = offset + limit
    hits = repo.search_artifacts(
        q,
        limit=search_limit,
        domain=sorted(entity_filter.domains) or None,
        artifact_type=sorted(selected_types) if selected_types else None,
        include_connections=False,
        include_diagrams=False,
        include_documents=False,
    ).hits
    items: list[dict[str, Any]] = []
    for h in hits:
        if h.record_type != "entity" or not isinstance(h.record, EntityRecord):
            continue
        rec = h.record
        if is_internal_entity_type(rec.artifact_type, ontology):
            continue
        if entity_filter.keywords and not entity_filter.keywords.issubset(rec.keywords):
            continue
        items.append(entity_display_item(rec, catalogs))
    # Fuzzy augmentation returns display items without their keyword lists, so it cannot honor
    # the exact-keyword facet — skip it entirely rather than dilute a faceted result.
    if len(items) < search_limit and not entity_filter.keywords:
        seen = {str(item["artifact_id"]) for item in items}
        fuzzy = fuzzy_entity_hits(repo, q, search_limit - len(items), seen, catalogs, selected_types)
        if entity_filter.domains:
            fuzzy = [item for item in fuzzy if item["domain"] in entity_filter.domains]
        items.extend(fuzzy)
    # Model entities always rank above diagram-owned constructs (stable within each
    # partition, so relevance order is preserved on both sides of the divider).
    items = [i for i in items if not i["diagram_internal"]] + [i for i in items if i["diagram_internal"]]
    page = items[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(items) else None
    return EntityDisplaySearchResult(items=page, next_cursor=next_cursor)
