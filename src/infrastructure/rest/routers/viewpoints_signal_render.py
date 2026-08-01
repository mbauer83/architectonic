"""D11 signal-render surface: the classification banner for ephemeral
signal-styled renders and the stamped export endpoint — the ONLY sanctioned
way styled output leaves the browser. Split from `viewpoints.py` for size;
mounted by it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.evaluate_viewpoint import (
    ViewpointExecutionRequest,
    evaluate_viewpoint,
)
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
    viewpoints_execution_max_entities,
    viewpoints_execution_timeout_seconds,
    viewpoints_legibility_budget,
)
from src.domain.clock import utc_now_iso
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_derived_attribute_deferral import declares_signal_source
from src.infrastructure.assurance.signal_attribute_capability import (
    composed_signal_attribute_capability,
)
from src.infrastructure.rendering.svg_banner import stamp_svg_banner
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import TAG_VIEWPOINTS, media_response
from src.infrastructure.rest.routers._viewpoint_freshness import (
    fresh_viewpoints_runtime_catalogs_dependency,
)

signal_render_router = APIRouter()


def _registry_snapshot(catalogs: RuntimeCatalogs, repo_roots: list) -> RegistrySnapshot:  # type: ignore[type-arg]
    return build_registry_snapshot(
        catalogs,
        repo_roots,
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )


def signal_banner_for(
    slug: str | None, catalogs: RuntimeCatalogs, entity_ids: list[str],
) -> dict[str, object] | None:
    """D11 banner for signal-declaring definitions: computed classification
    (max of visible contributors), per-anchor basis snapshots, and the generation
    timestamp. None for plain viewpoints — the response stays cacheable."""
    definition = catalogs.viewpoints.get(slug) if slug else None
    if definition is None or not declares_signal_source(definition):
        return None
    batch = composed_signal_attribute_capability().fetch_metrics(tuple(entity_ids), ())
    return {
        "classification": batch.classification if batch.available else None,
        "available": batch.available,
        "note": batch.note,
        "basis_snapshots": [
            {"anchor_entity_id": snapshot.anchor_entity_id,
             "snapshot_id": snapshot.snapshot_id,
             "activated_at": snapshot.activated_at}
            for snapshot in batch.basis_snapshots
        ],
        "generated_at": utc_now_iso(),
    }


@signal_render_router.post("/api/viewpoints/export-render", tags=[TAG_VIEWPOINTS],
    summary="Export a viewpoint render",
    response_class=Response,
    responses=media_response("image/svg+xml", "The stamped render, as attachment bytes"))
def export_viewpoint_render(
    slug: Annotated[str | None, Body()] = None,
    query: Annotated[dict[str, object] | None, Body()] = None,
    parameters: Annotated[dict[str, object] | None, Body()] = None,
    svg: Annotated[str | None, Body()] = None,
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    """Stamped export (D11): returns the styled render as attachment bytes with
    the classification banner burned into the SVG. The persisted-diagram
    download route is never used for signal-styled content; this endpoint is
    the ONLY sanctioned way styled output leaves the browser.

    Slug-only by contract: stamped exports are for saved definitions, and the client
    supplies the already-styled SVG, so an ephemeral presentation override does not apply
    here (there is no server-side presentation to override for this route)."""
    if svg is None or not svg.strip():
        raise HTTPException(400, "svg (the client-styled render) is required")
    if slug is None:
        raise HTTPException(400, "slug is required — stamped exports are for saved definitions")
    definition = catalogs.viewpoints.get(slug)
    if definition is None:
        raise HTTPException(400, f"unknown viewpoint slug {slug!r}")
    repo = s.get_repo()
    request = ViewpointExecutionRequest(
        slug=slug, query=None, limit=viewpoints_execution_max_entities(), parameters=parameters,
    )
    registries = _registry_snapshot(catalogs, repo.repo_roots)
    result = evaluate_viewpoint(
        request,
        catalog=catalogs.viewpoints,
        read_access=repo,
        registries=registries,
        index_generation=repo.read_model_version().generation,
        max_entities=viewpoints_execution_max_entities(),
        default_limit=viewpoints_execution_max_entities(),
        timeout_seconds=viewpoints_execution_timeout_seconds(),
        default_legibility_budget=viewpoints_legibility_budget(),
        signal_capability=composed_signal_attribute_capability(),
    )
    banner = signal_banner_for(slug, catalogs, [item.id for item in result.entities])
    stamped = stamp_svg_banner(svg, _banner_text(slug, banner))
    filename = f"{slug}-{utc_now_iso().replace(':', '')}.svg"
    return Response(
        content=stamped,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _banner_text(slug: str, banner: dict[str, object] | None) -> str:
    if banner is None:
        return f"{slug} — generated {utc_now_iso()}"
    classification = banner.get("classification") or "signals unavailable"
    raw_snapshots = banner.get("basis_snapshots")
    snapshots: list[dict[str, str]] = raw_snapshots if isinstance(raw_snapshots, list) else []
    basis_part = ", ".join(
        f"{s['anchor_entity_id']}: {s['snapshot_id']}" for s in snapshots
    ) or "no active snapshot"
    return f"{classification} — basis {basis_part} — generated {banner.get('generated_at')}"
