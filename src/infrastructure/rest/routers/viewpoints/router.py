"""Read-only REST endpoints for execution, projection, and diagram previews."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.artifact_projection import project_artifact_by_frontmatter
from src.application.viewpoints.derived_connection_records import derived_connection_record
from src.application.viewpoints.evaluate_viewpoint import (
    UnknownViewpointSlugError,
    ViewpointExecutionRequest,
    ViewpointExecutionTimeoutError,
    evaluate_viewpoint,
    project_viewpoint_repository,
)
from src.application.viewpoints.export_csv import build_execution_csv
from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
    viewpoints_diagram_render_max_entities,
    viewpoints_execution_max_entities,
    viewpoints_execution_timeout_seconds,
    viewpoints_legibility_budget,
)
from src.domain.relationships.relationship_reachability import DerivationLimitError, is_derived_connection_id
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoints import PresentationSpec, TargetKind
from src.infrastructure.assurance.signal_attribute_capability import (
    composed_signal_attribute_capability,
)
from src.infrastructure.rest.contracts.viewpoint_execution import (
    ViewpointDiagramRenderResponse,
    ViewpointExecutionResponse,
)
from src.infrastructure.rest.contracts.viewpoint_projection import (
    DiagramViewpointProjectionResponse,
    ViewpointProjectionResponse,
)

# Named as a module at the call sites: every one of these turns an execution failure into the
# published envelope, and `failures.derivation_limit(...)` says that where four bare names did not.
from src.infrastructure.rest.routers import _failures as failures
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_VIEWPOINTS, media_response
from src.infrastructure.rest.routers.diagrams._selection import resolve_diagram_selection
from src.infrastructure.rest.routers.viewpoints._freshness import fresh_viewpoints_runtime_catalogs_dependency
from src.infrastructure.rest.routers.viewpoints._request_parsing import parse_presentation, parse_query
from src.infrastructure.rest.routers.viewpoints.signal_render import (
    signal_banner_for,
    signal_render_router,
)

router = APIRouter()
router.include_router(signal_render_router)

# Fixed notation for unpersisted diagram previews. Styling overlays are applied by the
# client to the returned SVG, so this endpoint returns unstyled notation only.
_AD_HOC_DIAGRAM_TYPE = "archimate-layered"


def _registry_snapshot(catalogs: RuntimeCatalogs, repo_roots: list[Path]) -> RegistrySnapshot:
    return build_registry_snapshot(
        catalogs,
        repo_roots,
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )


def _effective_presentation(
    slug: str | None, override: PresentationSpec | None, catalogs: RuntimeCatalogs
) -> PresentationSpec | None:
    """The presentation actually used for this execution: an inline/override presentation
    when supplied, else the saved definition's own (slug), else None (bare ad-hoc query).
    Column/label helpers consume this rather than unconditionally re-fetching the saved
    catalog definition — so a slug + presentation override renders under the override."""
    if override is not None:
        return override
    if slug is None:
        return None
    definition = catalogs.viewpoints.get(slug)
    return definition.presentation if definition is not None else None


def _presentation_label_attribute(presentation: PresentationSpec | None) -> str | None:
    if presentation is None:
        return None
    value = presentation.display_options.get("label_attribute")
    return value if isinstance(value, str) and value else None


@router.post("/api/viewpoints/execute", tags=[TAG_VIEWPOINTS], summary="Execute a viewpoint query",
    response_model=ViewpointExecutionResponse)
def execute_viewpoint(
    slug: Annotated[str | None, Body()] = None,
    query: Annotated[dict[str, object] | None, Body()] = None,
    limit: Annotated[int | None, Body()] = None,
    parameters: Annotated[dict[str, object] | None, Body()] = None,
    presentation: Annotated[dict[str, object] | None, Body()] = None,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> dict[str, object]:
    """Execute a viewpoint by ``slug`` (catalog definition) or ``query`` (ad-hoc). An
    optional ``presentation`` is additive on both paths — the inline presentation for a
    query, or an ephemeral override for a slug (the stored definition is never mutated);
    omitting it uses the saved presentation (slug) or exploration (bare query). Its
    response matches the MCP result."""
    if (slug is None) == (query is None):
        raise HTTPException(400, "exactly one of 'slug' or 'query' must be provided")

    parsed_query = parse_query(query)
    parsed_presentation = parse_presentation(presentation)
    request = ViewpointExecutionRequest(
        slug=slug, query=parsed_query, limit=limit, parameters=parameters, presentation=parsed_presentation
    )
    repo = s.get_repo()
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    max_entities = viewpoints_execution_max_entities()
    try:
        result = evaluate_viewpoint(
            request,
            catalog=catalogs.viewpoints,
            read_access=repo,
            registries=registries,
            index_generation=repo.read_model_version().generation,
            max_entities=max_entities,
            default_limit=max_entities,
            timeout_seconds=viewpoints_execution_timeout_seconds(),
            default_legibility_budget=viewpoints_legibility_budget(),
            signal_capability=composed_signal_attribute_capability(),
        )
    except UnknownViewpointSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ViewpointExecutionTimeoutError as exc:
        raise failures.execution_timeout(str(exc)) from exc
    except ViewpointParameterError as exc:
        raise failures.parameter_error(exc) from exc
    except BindingCardinalityError as exc:
        raise failures.binding_cardinality(exc) from exc
    except DerivationLimitError as exc:
        raise failures.derivation_limit(str(exc)) from exc
    return asdict(result)


@router.post("/api/viewpoints/export-csv", tags=[TAG_VIEWPOINTS], summary="Execute a viewpoint and export CSV",
    response_class=Response,
    responses=media_response("text/csv", "The complete result set, as an attachment"))
def export_viewpoint_csv(
    slug: Annotated[str | None, Body()] = None,
    query: Annotated[dict[str, object] | None, Body()] = None,
    parameters: Annotated[dict[str, object] | None, Body()] = None,
    presentation: Annotated[dict[str, object] | None, Body()] = None,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    """COMPLETE, generation-pinned CSV of an execution: the full result set (one snapshot
    execution — never the visible page of a paginated view) with a provenance header
    block. Column selection/order follows the effective presentation (inline/override when
    supplied, else the saved definition's). Client-side CSV of rendered rows is deliberately
    not the mechanism."""
    if (slug is None) == (query is None):
        raise HTTPException(400, "exactly one of 'slug' or 'query' must be provided")
    parsed_query = parse_query(query)
    parsed_presentation = parse_presentation(presentation)
    repo = s.get_repo()
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    max_entities = viewpoints_execution_max_entities()
    request = ViewpointExecutionRequest(
        slug=slug, query=parsed_query, limit=max_entities, parameters=parameters, presentation=parsed_presentation
    )
    try:
        result = evaluate_viewpoint(
            request,
            catalog=catalogs.viewpoints,
            read_access=repo,
            registries=registries,
            index_generation=repo.read_model_version().generation,
            max_entities=max_entities,
            default_limit=max_entities,
            timeout_seconds=viewpoints_execution_timeout_seconds(),
            default_legibility_budget=viewpoints_legibility_budget(),
            signal_capability=composed_signal_attribute_capability(),
        )
    except UnknownViewpointSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ViewpointExecutionTimeoutError as exc:
        raise failures.execution_timeout(str(exc)) from exc
    except ViewpointParameterError as exc:
        raise failures.parameter_error(exc) from exc
    except BindingCardinalityError as exc:
        raise failures.binding_cardinality(exc) from exc
    except DerivationLimitError as exc:
        raise failures.derivation_limit(str(exc)) from exc
    effective_presentation = _effective_presentation(slug, parsed_presentation, catalogs)
    columns = effective_presentation.columns if effective_presentation is not None else None
    text = build_execution_csv(result, columns, parameters)
    filename = f"{result.slug or 'viewpoint-export'}-gen{result.index_generation}.csv"
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/viewpoints/execute-projection", tags=[TAG_VIEWPOINTS], summary="Execute a viewpoint projection",
    response_model=ViewpointProjectionResponse)
def execute_viewpoint_projection(
    slug: Annotated[str | None, Body()] = None,
    query: Annotated[dict[str, object] | None, Body()] = None,
    parameters: Annotated[dict[str, object] | None, Body()] = None,
    presentation: Annotated[dict[str, object] | None, Body()] = None,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> dict[str, object]:
    """Return GUI projection items with style tokens for the selected population. An optional
    ``presentation`` overrides styling/columns ephemerally (inline query, or slug override)."""
    if (slug is None) == (query is None):
        raise HTTPException(400, "exactly one of 'slug' or 'query' must be provided")
    parsed_query = parse_query(query)
    parsed_presentation = parse_presentation(presentation)
    repo = s.get_repo()
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    index_generation = repo.read_model_version().generation
    try:
        projection = project_viewpoint_repository(
            slug,
            parsed_query,
            catalog=catalogs.viewpoints,
            read_access=repo,
            registries=registries,
            parameters=parameters,
            signal_capability=composed_signal_attribute_capability(),
            presentation=parsed_presentation,
        )
    except UnknownViewpointSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ViewpointParameterError as exc:
        raise failures.parameter_error(exc) from exc
    except BindingCardinalityError as exc:
        raise failures.binding_cardinality(exc) from exc
    except DerivationLimitError as exc:
        raise failures.derivation_limit(str(exc)) from exc
    # Same provenance contract as /execute: consumers correlating an execution result
    # with its styled projection can verify both came from the same model snapshot.
    return {"applied": True, "index_generation": index_generation, **asdict(projection)}


@router.post("/api/viewpoints/execute-diagram", tags=[TAG_VIEWPOINTS],
    summary="Execute a viewpoint against a diagram", response_model=ViewpointDiagramRenderResponse)
def execute_viewpoint_diagram(
    response: Response,
    slug: Annotated[str | None, Body()] = None,
    query: Annotated[dict[str, object] | None, Body()] = None,
    parameters: Annotated[dict[str, object] | None, Body()] = None,
    presentation: Annotated[dict[str, object] | None, Body()] = None,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> dict[str, object]:
    """Render an unpersisted ArchiMate diagram for the evaluated population.

    Entirely in memory. An optional ``presentation`` supplies the ephemeral diagram
    options (e.g. label attribute) for an inline query or as a slug override. When the
    definition declares a security-signal source the response is marked no-store and carries
    a `signal_banner` (computed classification + basis runs + generation timestamp) — the D11
    ephemeral render; downloads go through /api/viewpoints/export-render."""
    if (slug is None) == (query is None):
        raise HTTPException(400, "exactly one of 'slug' or 'query' must be provided")
    parsed_query = parse_query(query)
    parsed_presentation = parse_presentation(presentation)
    repo = s.get_repo()
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    max_entities = viewpoints_execution_max_entities()
    request = ViewpointExecutionRequest(
        slug=slug, query=parsed_query, limit=max_entities, parameters=parameters, presentation=parsed_presentation
    )
    try:
        result = evaluate_viewpoint(
            request,
            catalog=catalogs.viewpoints,
            read_access=repo,
            registries=registries,
            index_generation=repo.read_model_version().generation,
            max_entities=max_entities,
            default_limit=max_entities,
            timeout_seconds=viewpoints_execution_timeout_seconds(),
            default_legibility_budget=viewpoints_legibility_budget(),
            signal_capability=composed_signal_attribute_capability(),
        )
    except UnknownViewpointSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ViewpointExecutionTimeoutError as exc:
        raise failures.execution_timeout(str(exc)) from exc
    except ViewpointParameterError as exc:
        raise failures.parameter_error(exc) from exc
    except BindingCardinalityError as exc:
        raise failures.binding_cardinality(exc) from exc
    except DerivationLimitError as exc:
        raise failures.derivation_limit(str(exc)) from exc

    render_limit = viewpoints_diagram_render_max_entities()
    if result.total_entity_count > render_limit:
        raise failures.diagram_render_limit(
            f"this result has {result.total_entity_count} entities — too large for diagram rendering "
            f"(limit {render_limit}). Try the exploration or table representation, or narrow the "
            "scope (filter by group/type, or anchor the view).",
            entity_count=result.total_entity_count,
            max_entities=render_limit,
        )

    from src.application.artifacts.parsing import normalize_puml_alias
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body, render_puml_svg

    modeled_connection_ids = [cid for cid in result.connection_ids if not is_derived_connection_id(cid)]
    entities, connections, _, _ = resolve_diagram_selection(repo, list(result.entity_ids), modeled_connection_ids)
    derived_records = [
        derived_connection_record(summary) for summary in result.connections if summary.certainty is not None
    ]
    puml = generate_archimate_puml_body(
        result.slug or "viewpoint-preview",
        entities,
        [*connections, *derived_records],
        diagram_type=_AD_HOC_DIAGRAM_TYPE,
        repo_root=repo_root,
        label_attribute=_presentation_label_attribute(_effective_presentation(slug, parsed_presentation, catalogs)),
    )
    svg, render_warnings = render_puml_svg(puml, repo_root, _AD_HOC_DIAGRAM_TYPE)
    # The rendered SVG's node/edge ids are PlantUML aliases (`normalize_puml_alias`'d from
    # each entity's `display_alias`), never the raw artifact id — the client-side click-to-
    # select overlay needs this mapping to resolve SVG elements back to artifact ids, the
    # same way a real persisted diagram's viewer already does from its own diagram_entities.
    entity_aliases = {e.artifact_id: normalize_puml_alias(e.display_alias) for e in entities if e.display_alias}
    banner = signal_banner_for(slug, catalogs, list(result.entity_ids))
    if banner is not None:
        response.headers["Cache-Control"] = "no-store"
    # ``signal_banner`` is always keyed, null where the definition declares no signal source. It was
    # omitted in that case, which asked a client to read absence and null as two states when there
    # is only one: the render is classified, or it is not.
    return {
        "svg": svg,
        "warnings": [*result.warnings, *render_warnings],
        "entity_aliases": entity_aliases,
        "signal_banner": banner,
    }


@router.get("/api/diagrams/{artifact_id}/viewpoint-projection", tags=[TAG_VIEWPOINTS],
    summary="Viewpoint projection for a diagram", response_model=DiagramViewpointProjectionResponse,
    responses=READ_RESPONSES)
def get_diagram_viewpoint_projection(
    artifact_id: str,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> dict[str, object]:
    """Return the optional saved viewpoint projection for one diagram or matrix."""
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    target_kind: TargetKind = "matrix" if diag_rec.diagram_type == "matrix" else "diagram"
    module = catalogs.diagram_types.find_diagram_type(diag_rec.diagram_type if target_kind == "diagram" else "matrix")
    if module is None:
        raise HTTPException(404, f"Diagram type not found: {diag_rec.diagram_type!r}")
    _, registry, _ = s.get_write_deps(catalogs)
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    projection = project_artifact_by_frontmatter(
        diag_rec.extra,
        target_kind=target_kind,
        target_id=diag_rec.artifact_id,
        catalog=catalogs.viewpoints,
        module=module,
        entity_type_infos=catalogs.ontology.all_entity_types(),
        default_enforcement=catalogs.viewpoint_enforcement,
        registry=registry,
        registries=registries,
    )
    if projection is None:
        return {"applied": False}
    return {"applied": True, **asdict(projection)}
