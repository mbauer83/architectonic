"""Artifact search endpoints (full-text and reference/linking search)."""

from __future__ import annotations

import logging
from functools import lru_cache as _lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from src.application.entity_type_predicates import is_assurance_entity_type, is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._entity_filter import EntityFilter
from src.infrastructure.gui.routers._global_search import (
    filter_global_hits,
    hidden_diagram_entity_types,
    prioritize_global_hits,
)
from src.infrastructure.gui.routers._openapi import TAG_DOCUMENTS, TAG_ENTITIES, TAG_TAXONOMY, OpenMapResponse

logger = logging.getLogger(__name__)


@_lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

router = APIRouter()


def _score_reference_hit(name: str, artifact_id: str, query: str) -> tuple[int, str, str]:
    q = query.strip().lower()
    if not q:
        return (3, name.lower(), artifact_id.lower())
    name_lc, id_lc = name.lower(), artifact_id.lower()
    if name_lc == q or id_lc == q:
        return (0, name_lc, id_lc)
    if name_lc.startswith(q) or id_lc.startswith(q):
        return (1, name_lc, id_lc)
    return (2, name_lc, id_lc)


def _try_assurance_hits(q: str, limit: int) -> list[dict[str, Any]]:
    """Return assurance search hits when the store is unlocked; silent empty on any failure."""
    try:
        from src.application.assurance_exposure import AssuranceExposurePolicy  # noqa: PLC0415
        from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context  # noqa: PLC0415
        ctx = get_assurance_context()
        pol = AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())
        if pol.check_locked():
            return []
        raw = ctx.store.search_nodes(q.strip(), limit=limit * 2)
        visible, _ = pol.filter_nodes(raw)
        return [
            {
                "score": 1.0,
                "record_type": "assurance-node",
                "artifact_id": str(n["node_id"]),
                "name": str(n.get("name", "")),
                "artifact_type": str(n.get("node_type", "")),
                "status": str(n.get("status", "")),
                "path": "",
            }
            for n in visible[:limit]
        ]
    except Exception:  # noqa: BLE001
        logger.debug("Assurance search unavailable for global merge", exc_info=False)
        return []


@router.get("/api/artifact-search", tags=[TAG_ENTITIES], summary="Display-oriented artifact search",
    response_model=OpenMapResponse)
def search_artifacts(
    q: str,
    limit: int = Query(default=20, le=100),
    include_entities: bool = True,
    include_connections: bool = False,
    include_diagrams: bool = True,
    include_documents: bool = True,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    result = repo.search_artifacts(
        q,
        limit=limit * 3,
        include_entities=include_entities,
        include_connections=include_connections,
        include_diagrams=include_diagrams,
        include_documents=include_documents,
        excluded_entity_types=hidden_diagram_entity_types(catalogs),
    )
    hits: list[dict[str, Any]] = []
    visible_hits = filter_global_hits(result.hits, catalogs)
    for h in prioritize_global_hits(visible_hits)[:limit]:
        aid = getattr(h.record, "artifact_id", "")
        hits.append({
            "score": h.score,
            "record_type": h.record_type,
            "artifact_id": aid,
            "name": getattr(h.record, "name", getattr(h.record, "title", "")),
            "status": getattr(h.record, "status", ""),
            "path": str(h.record.path),
        })
    hits.extend(_try_assurance_hits(q, limit))
    return {"query": result.query, "hits": hits}


@router.get("/api/reference-search", tags=[TAG_DOCUMENTS], summary="Search entities for document references",
    response_model=OpenMapResponse)
def search_reference_artifacts(
    q: str = "",
    kind: str | None = None,
    domains: str | None = None,
    entity_types: str | None = None,
    doc_types: str | None = None,
    limit: int = Query(default=30, le=100),
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    repo = s.get_repo()
    entity_filter = EntityFilter.from_params(domains=domains, entity_types=entity_types)
    selected_doc_types = {v.strip() for v in (doc_types or "").split(",") if v.strip()}
    q_lc = q.strip().lower()
    hits: list[dict[str, Any]] = []

    if kind in (None, "entity"):
        for entity in repo.list_entities():
            if not entity_filter.matches(entity, ontology=_catalogs().ontology):
                continue
            if q_lc and q_lc not in entity.name.lower() and q_lc not in entity.artifact_id.lower():
                continue
            hits.append({
                "artifact_id": entity.artifact_id,
                "record_type": "entity",
                "name": entity.name,
                "status": entity.status,
                "path": str(entity.path),
                "domain": entity.domain,
                "artifact_type": entity.artifact_type,
                "is_global": s.is_global(entity.path),
            })

    if kind in (None, "diagram"):
        for diagram in repo.list_diagrams():
            domain = catalogs.diagram_types.diagram_type_domain(diagram.diagram_type)
            if entity_filter.domains and (domain is None or domain not in entity_filter.domains):
                continue
            if q_lc and q_lc not in diagram.name.lower() and q_lc not in diagram.artifact_id.lower():
                continue
            hits.append({
                "artifact_id": diagram.artifact_id,
                "record_type": "diagram",
                "name": diagram.name,
                "status": diagram.status,
                "path": str(diagram.path),
                "diagram_type": diagram.diagram_type,
                "domain": domain,
            })

    if kind in (None, "document"):
        for document in repo.list_documents():
            if selected_doc_types and document.doc_type not in selected_doc_types:
                continue
            if q_lc and q_lc not in document.title.lower() and q_lc not in document.artifact_id.lower():
                continue
            hits.append({
                "artifact_id": document.artifact_id,
                "record_type": "document",
                "name": document.title,
                "status": document.status,
                "path": str(document.path),
                "doc_type": document.doc_type,
                "sections": list(document.sections),
            })

    hits.sort(key=lambda h: _score_reference_hit(str(h["name"]), str(h["artifact_id"]), q))
    return {"query": q, "hits": hits[:limit]}


@router.get("/api/entity-taxonomy", tags=[TAG_TAXONOMY], summary="Entity taxonomy tree", response_model=OpenMapResponse)
def get_entity_taxonomy(
    request: Request,
    scope: str | None = None,
    meta_ontology: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    from src.infrastructure.app_bootstrap import (  # noqa: PLC0415
        module_registry_from_app,
        resolve_meta_ontology_artifact_types,
    )

    registry = module_registry_from_app(request.app)
    repo = s.get_repo()
    # Keep taxonomy aligned with /api/entities: diagram-owned nodes are queryable by diagram
    # tooling but are not standalone model catalog entries.
    entities = [e for e in repo.list_entities(group=group) if e.host_diagram_id is None]
    if scope == "global":
        _cat = _catalogs()
        entities = [
            e for e in entities
            if s.is_global(e.path)
            and not is_internal_entity_type(e.artifact_type, _cat.ontology)
            and not is_assurance_entity_type(e.artifact_type, _cat.module_catalog)
        ]
    elif scope == "engagement":
        _cat = _catalogs()
        entities = [
            e for e in entities
            if not s.is_global(e.path)
            and not is_internal_entity_type(e.artifact_type, _cat.ontology)
            and not is_assurance_entity_type(e.artifact_type, _cat.module_catalog)
        ]
    else:
        _cat = _catalogs()
        entities = [
            e for e in entities
            if not is_internal_entity_type(e.artifact_type, _cat.ontology)
            and not is_assurance_entity_type(e.artifact_type, _cat.module_catalog)
        ]

    allowed_types = resolve_meta_ontology_artifact_types(meta_ontology or "", registry)
    if allowed_types is not None:
        entities = [e for e in entities if e.artifact_type in allowed_types]

    domain_type_counts: dict[str, dict[str, int]] = {}
    for entity in entities:
        domain = entity.domain or ""
        tc = domain_type_counts.setdefault(domain, {})
        tc[entity.artifact_type] = tc.get(entity.artifact_type, 0) + 1

    ordered = registry.domain_order()
    extra = [d for d in domain_type_counts if d not in ordered]
    domains = []
    for domain_name in ordered + extra:
        tc = domain_type_counts.get(domain_name, {})
        if not tc:
            continue
        types = [{"name": t, "count": c} for t, c in sorted(tc.items())]
        domains.append({"name": domain_name, "count": sum(tc.values()), "types": types})
    return {"domains": domains}
