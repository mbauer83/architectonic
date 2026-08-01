"""REST endpoints backing the GUI viewpoints management view: the effective merged
catalog (full definitions, tier-tagged), the criteria-catalog registries snapshot pickers
are built from, a plain-language query-summary preview, and create/edit/delete — the same
``persist_edit``-mode validation and catalog-file persistence as the ``artifact_viewpoint``
MCP tool. One write path, two front ends.

Catalogs are rebuilt fresh per request (``process_runtime_catalogs()``,
not the app-state-cached ``runtime_catalogs_dependency``) — the same pattern every other
write-adjacent GUI router uses, so a definition written here is visible to the very next
request without a backend restart.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.verification.artifact_verifier_types import VALID_STATUSES
from src.application.viewpoints.persist_definition import (
    find_viewpoint_referencers,
)
from src.application.viewpoints.pins import load_pinned_slugs, save_pinned_slugs
from src.application.viewpoints.reference_report_cache import cached_reference_report
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import RESERVED_CONNECTION_PATHS, RESERVED_ENTITY_PATHS
from src.domain.viewpoints.viewpoint_lineage import definition_digest, fork_status
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoint_scope_query import definition_with_scope_query
from src.domain.viewpoints.viewpoint_serialization import viewpoint_definition_to_mapping
from src.domain.viewpoints.viewpoint_summary import render_query_summary
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.rest.contracts.viewpoint_catalogs import (
    CriteriaCatalogResponse,
    ViewpointQuerySummaryResponse,
)
from src.infrastructure.rest.contracts.viewpoint_definition import ViewpointDefinitionListResponse
from src.infrastructure.rest.contracts.viewpoints import (
    ViewpointPinsResponse,
    ViewpointReferencerListResponse,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_VIEWPOINTS, WRITE_RESPONSES
from src.infrastructure.rest.routers.viewpoints._write import router as _write_router
from src.infrastructure.viewpoint_declarations import (
    load_effective_viewpoint_catalog,
    load_viewpoint_catalog_file,
)
from src.infrastructure.write.artifact_write.viewpoint_type_guidance import summarize_scope

router = APIRouter()


def _engagement_root():
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(500, "Engagement repository not initialized")
    return root


def _both_roots() -> list[Any]:
    return list(s.get_repo().repo_roots)


def _tier(slug: str, *, engagement_catalog: ViewpointCatalog, enterprise_catalog: ViewpointCatalog) -> str:
    if engagement_catalog.get(slug) is not None:
        return "engagement"
    if enterprise_catalog.get(slug) is not None:
        return "enterprise"
    return "module"


def _reference_report_settings() -> RegistrySnapshot:
    catalogs = process_runtime_catalogs()
    return build_registry_snapshot(
        catalogs,
        _both_roots(),
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )


def _broken_references(
    definition: ViewpointDefinition, *, registries: RegistrySnapshot, index_generation: int | None
) -> list[dict[str, str]]:
    """The definition's broken references, computed on demand (never persisted) — the ONE
    report rendered three ways: a count badge on the list, per-reference notices in the
    editor, and result warnings at execution."""
    report = cached_reference_report(
        definition, registries=registries, read_access=s.get_repo(), index_generation=index_generation
    )
    return [
        {"kind": broken.kind, "reference": broken.reference, "locus": broken.locus, "severity": broken.severity}
        for broken in report
    ]


def _full_entry(
    definition: ViewpointDefinition,
    *,
    tier: str,
    merged: ViewpointCatalog,
    registries: RegistrySnapshot,
    index_generation: int | None,
) -> dict[str, Any]:
    # The catalog row must describe the ACTIVE selection: a scope-mode definition's
    # (possibly divergent) inactive query never appears as its summary.
    active_query = definition_with_scope_query(definition)[0].query
    return {
        **viewpoint_definition_to_mapping(definition),
        "tier": tier,
        "scope_summary": summarize_scope(definition.scope),
        "query_summary": (
            render_query_summary(active_query, default_derivation_max_hops=viewpoints_derivation_max_hops())
            if active_query is not None
            else None
        ),
        # The definition's CURRENT content digest — verified execution references pin it,
        # and fork staleness is decided against it.
        "definition_digest": definition_digest(definition),
        # Staleness by content-digest comparison against the CURRENT origin, never by
        # version comparison — versions are hand-edited integers.
        "fork_status": fork_status(
            definition.forked_from,
            merged.get(definition.forked_from.slug) if definition.forked_from is not None else None,
        ),
        "broken_references": _broken_references(
            definition, registries=registries, index_generation=index_generation
        ),
    }


@router.get("/api/viewpoints", tags=[TAG_VIEWPOINTS], summary="List viewpoint definitions",
    response_model=ViewpointDefinitionListResponse, response_model_exclude_none=True)
def list_viewpoint_definitions() -> dict[str, Any]:
    """The effective merged catalog (module + enterprise + engagement), each entry
    carrying its full serialized mapping (to populate an edit form) and a ``tier`` so the
    GUI can mark enterprise/module definitions read-only."""
    engagement_root = _engagement_root()
    enterprise_root = s.maybe_enterprise_root()
    engagement_catalog = load_viewpoint_catalog_file(engagement_root)
    enterprise_catalog = (
        load_viewpoint_catalog_file(enterprise_root) if enterprise_root is not None else ViewpointCatalog.empty()
    )
    merged = load_effective_viewpoint_catalog(_both_roots())
    # Registries + model generation resolved ONCE per request; the report is a pure function
    # of (definition, model) and is recomputed on demand, never persisted (Stream R).
    registries = _reference_report_settings()
    index_generation = s.get_repo().read_model_version().generation
    entries = [
        _full_entry(
            d,
            tier=_tier(d.slug, engagement_catalog=engagement_catalog, enterprise_catalog=enterprise_catalog),
            merged=merged,
            registries=registries,
            index_generation=index_generation,
        )
        for d in sorted(merged.entries, key=lambda d: d.slug)
    ]
    return {"viewpoints": entries}


def _known_group_slugs() -> list[str]:
    """Every project/group slug a ``group`` criterion can meaningfully match: declared
    ``model-project`` registry entries plus the distinct ``group`` facet observed on
    indexed entities (covering enterprise-side and legacy/uncategorized groups)."""
    from src.application.group_registry import load_group_registry  # noqa: PLC0415

    slugs = {record.group for record in s.get_repo().list_entities() if record.group}
    engagement_root = s.maybe_engagement_root()
    if engagement_root is not None:
        registry = load_group_registry(engagement_root)
        slugs |= {entry.slug for entry in registry.list_axis("model-project")}
    return sorted(slugs)


@router.get("/api/viewpoints/criteria-catalog", tags=[TAG_VIEWPOINTS],
    summary="Criteria catalog for viewpoint authoring", response_model=CriteriaCatalogResponse)
def get_criteria_catalog() -> dict[str, Any]:
    """Registries snapshot the criteria-tree builder's pickers are fed from — the same
    ``RegistrySnapshot`` save-mode validation itself resolves attribute paths against."""
    catalogs = process_runtime_catalogs()
    registries: RegistrySnapshot = build_registry_snapshot(
        catalogs,
        _both_roots(),
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )
    derivation = {
        str(name): {"role": info.derivation_role, "strength": info.derivation_strength}
        for name, info in catalogs.ontology.all_connection_types().items()
        if info.derivation_role is not None
    }
    entity_type_domains = {
        str(name): info.hierarchy[0] for name, info in registries.entity_type_infos.items() if info.hierarchy
    }
    # Enumerable value sets for the criteria value picker, keyed by the flat attribute-path
    # namespace: schema-declared ``enum`` attributes, plus the enumerable reserved read-model
    # facets (``domain`` from the distinct owning-domain set, ``status`` from the canonical
    # status vocabulary, ``group`` from the project registry plus every group observed on
    # indexed records). Reserved facets take precedence over a like-named schema attribute.
    entity_attribute_enums: dict[str, list[str]] = {
        str(path): list(values) for path, values in registries.entity_attribute_enums.items()
    }
    entity_attribute_enums["domain"] = sorted(set(entity_type_domains.values()))
    entity_attribute_enums["status"] = sorted(VALID_STATUSES)
    entity_attribute_enums["group"] = _known_group_slugs()
    connection_attribute_enums = {
        str(path): list(values) for path, values in registries.connection_attribute_enums.items()
    }
    # Internal entity types (e.g. global-artifact-reference) are system-managed and are
    # excluded from every authoring surface; the validation snapshot itself still knows
    # them, so promotion-created definitions referencing them stay valid.
    authorable_entity_types = [
        entity_type
        for entity_type in sorted(registries.known_entity_types)
        if not is_internal_entity_type(entity_type, catalogs.ontology)
    ]
    return {
        "entity_types": authorable_entity_types,
        "connection_types": sorted(registries.known_connection_types),
        "specialization_slugs": sorted(registries.known_specialization_slugs),
        "entity_attribute_types": dict(registries.entity_attribute_types),
        "connection_attribute_types": dict(registries.connection_attribute_types),
        "entity_attribute_enums": entity_attribute_enums,
        "connection_attribute_enums": connection_attribute_enums,
        "symmetric_connection_types": sorted(registries.symmetric_connection_types),
        "reserved_entity_paths": sorted(RESERVED_ENTITY_PATHS),
        "reserved_connection_paths": sorted(RESERVED_CONNECTION_PATHS),
        "depth_cap": registries.depth_cap,
        "entity_type_domains": entity_type_domains,
        "bindings": {
            "select": ["entity", "connection"],
            "aggregate": ["count", "min", "max", "sum", "average", "first", "last"],
            "result_types": [
                "entity[type-slug]", "connection[type-slug]", "entities[type-slug]", "connections[type-slug]",
                "string", "integer", "number", "date", "boolean", "slug", "optional[result-type]",
                "list[result-type]", "tuple[result-type, ...]",
            ],
        },
        "parameters": {"types": ["string", "integer", "number", "date", "boolean", "slug", "entity-id"]},
        "derived": {
            "traversal": ["direct", "derived"],
            "certainty": ["certain", "potential"],
            "reduce": ["count", "min", "max", "sum", "average", "first", "last"],
        },
        "connection_derivation": derivation,
    }


@router.get("/api/viewpoints/pins", tags=[TAG_VIEWPOINTS], summary="Pinned viewpoints",
    response_model=ViewpointPinsResponse, response_model_exclude_none=True)
def get_viewpoint_pins() -> dict[str, Any]:
    """Pinned definition slugs (Home/management quick access) — an engagement-repo-local
    sidecar list, never definition content and never promoted. Slugs no longer in the
    effective catalog are dropped and reported under ``pruned``."""
    engagement_root = _engagement_root()
    merged = load_effective_viewpoint_catalog(_both_roots())
    known = frozenset(d.slug for d in merged.entries)
    pinned = load_pinned_slugs(engagement_root, known_slugs=known)
    return {"slugs": list(pinned.slugs), "pruned": list(pinned.pruned)}


class ViewpointPinsBody(BaseModel):
    slugs: list[str]


@router.put("/api/viewpoints/pins", tags=[TAG_VIEWPOINTS], summary="Update pinned viewpoints",
    response_model=ViewpointPinsResponse, response_model_exclude_none=True,
    responses=WRITE_RESPONSES)
def put_viewpoint_pins(body: ViewpointPinsBody) -> dict[str, Any]:
    engagement_root = _engagement_root()
    merged = load_effective_viewpoint_catalog(_both_roots())
    known = frozenset(d.slug for d in merged.entries)
    unknown = [slug for slug in body.slugs if slug not in known]
    if unknown:
        raise HTTPException(400, f"unknown viewpoint slug(s): {', '.join(unknown)}")
    s.authorized_write(
            "viewpoints_replace_viewpoint_pins", save_pinned_slugs, engagement_root, tuple(body.slugs))
    return {"slugs": body.slugs}


@router.get("/api/viewpoints/{slug}/referencers", tags=[TAG_VIEWPOINTS],
    summary="Diagrams referencing a viewpoint",
    response_model=ViewpointReferencerListResponse, responses=READ_RESPONSES)
def get_viewpoint_referencers(slug: str) -> dict[str, Any]:
    """Diagrams/matrices whose viewpoint application pins this slug — the management view
    uses this to warn, before a semantic edit, which views a version bump would leave
    pinned to a now-stale version."""
    referencers = find_viewpoint_referencers(slug, read_access=s.get_repo())
    return {"referencers": [asdict(r) for r in referencers]}


class SummarizeQueryBody(BaseModel):
    query: dict[str, Any]


@router.post("/api/viewpoints/summarize", tags=[TAG_VIEWPOINTS], summary="Summarize a viewpoint definition",
    response_model=ViewpointQuerySummaryResponse)
def summarize_query(body: SummarizeQueryBody) -> dict[str, str]:
    """Plain-language rendering of an in-progress (possibly ad-hoc, unsaved) query — the
    same ``render_query_summary`` MCP ``list``/``execute`` and REST execution use, so the
    live builder preview can never disagree with what those surfaces say later.

    Query-only by contract: a summary/count describes the query's target population and is
    independent of presentation, so this route takes no ``presentation`` input."""
    try:
        query = query_from_mapping(body.query, label="query")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"summary": render_query_summary(query, default_derivation_max_hops=viewpoints_derivation_max_hops())}


# Included last, deliberately. The write surface owns ``/api/viewpoints/{slug}``, which would also
# match the literal siblings ``pins`` and ``criteria-catalog`` — Starlette matches in registration
# order, so the literals have to be mounted first or a pin update would arrive as a definition
# replace. ``test_a_literal_sibling_segment_is_not_read_as_a_slug`` asserts the outcome rather than
# the rule.
router.include_router(_write_router)
