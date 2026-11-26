"""Diagram image-serving endpoints: rendered PNG, on-demand SVG, and download.

The SVG endpoint doubles as the confidential-assurance viewer: a confidential assurance
diagram (no on-disk image, per rule G-f) is rendered on demand in memory and served only
when the confidential store is unlocked.

It also carries the **reading lens**: `colour_by` and `print` ask for an ad-hoc colouring by an
attribute and for attribute values printed with the elements. Those are parameters of *these* two
addresses rather than a new operation, and that follows from what a lens is. A reader's choice is
never persisted — it lasts as long as their visit — so the rendered bytes *are* the display, and
"download what I am looking at" is this same render asked for as an attachment. A separate address
would have to answer the same question twice and then keep the two answers in step.

A lens forces a re-render: the on-disk image is the authored diagram, which is exactly what a lensed
request is not asking for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from src.application.repository_confinement import is_within
from src.application.runtime_catalogs import RuntimeCatalogs
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, RENDERED
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.picture_reading.lensed_reading import kind_muting, reading_body
from src.infrastructure.rest.contracts.path_components import PathComponentParameter
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS, media_response
from src.infrastructure.rest.routers.diagrams._reading_lens_request import (
    ColourBy,
    ElementKindColouringParameter,
    Gradient,
    Key,
    Legend,
    Printed,
    Ramp,
    lens_from_query,
)
from src.infrastructure.rest.routers.picture_reads import picture_sources, rendered_image
from src.infrastructure.rest.routers.viewpoints._freshness import (
    fresh_viewpoints_runtime_catalogs_dependency,
)

router = APIRouter()


def _is_confidential_diagram(diagram_path: Path, diagram_type: str) -> bool:
    """True if the diagram at *diagram_path* is a confidential assurance diagram (TLP-gated)."""
    from src.infrastructure.write.artifact_write.diagram_confidentiality import is_confidential_diagram_source
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    tlp = parse_diagram_file(diagram_path).frontmatter.get("tlp")
    return is_confidential_diagram_source(diagram_type, tlp if isinstance(tlp, str) else None)


def _refuse_a_matrix(d: DiagramRecord | None) -> None:
    """A matrix is a diagram of the matrix kind with cells and no drawing, so it has no image to serve.

    Handed to PlantUML it answered "No diagram found" and the request a 500; naming the kind is the
    answer, as `/api/matrices/{id}/config` answers 404 for a diagram that is not a matrix.
    """
    if d is not None and d.diagram_type == "matrix":
        raise HTTPException(404, f"'{d.artifact_id}' is a matrix, which has no drawing; "
                                 f"read its cells at /api/matrices/{d.artifact_id}/config")


@router.get("/api/diagram-images/{filename}", tags=[TAG_DIAGRAMS], summary="Serve a rendered diagram image",
    response_class=FileResponse,
    responses={**READ_RESPONSES, **media_response("image/png", "The rendered image")})
def get_diagram_image(filename: PathComponentParameter) -> FileResponse:
    """A rendered image, found by its file name anywhere in the rendered tree.

    Group collections mirror the source tree under `rendered/<collection>/`, and a rendered file
    name is unique by artifact id, so the name alone finds it. It is compared as a name, never used
    as a pattern: handed to a glob, `*` matched any file. A match must still lie inside the rendered
    tree once links are followed.
    """
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    rendered_root = repo_root / DIAGRAM_CATALOG / RENDERED
    found = next(
        (
            path for path in (rendered_root / filename, *rendered_root.rglob("*"))
            if path.name == filename and path.is_file() and is_within(path, rendered_root)
        ),
        None,
    )
    if found is None:
        raise HTTPException(404, f"Rendered image not found: {filename}")
    return FileResponse(found, media_type="image/png")


@router.get("/api/diagrams/{artifact_id}/svg", tags=[TAG_DIAGRAMS], summary="Serve a diagram as SVG",
    response_class=Response,
    responses={**READ_RESPONSES, **media_response("image/svg+xml", "The rendered diagram")})
def get_diagram_svg(
    artifact_id: str,
    colour_by: ColourBy = "",
    printed: Printed = [],  # noqa: B006
    ramp: Ramp = "",
    key: Key = [],  # noqa: B006
    legend: Legend = False,
    gradient: Gradient = "",
    element_kind_colouring: ElementKindColouringParameter = "keep",
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    id = artifact_id
    lens = lens_from_query(
        colour_by, printed, ramp, key, legend, gradient, element_kind_colouring
    )
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    diag_rec = s.get_repo().get_diagram(id)
    _refuse_a_matrix(diag_rec)
    # Resolve via the index so confidential/ and group-collection subdirectories are found,
    # not just the flat root.
    diagram_path = repo_root / DIAGRAM_CATALOG / DIAGRAMS / f"{id}.puml"
    if not diagram_path.exists() and diag_rec is not None and diag_rec.path.exists():
        diagram_path = diag_rec.path
    if not diagram_path.exists():
        raise HTTPException(404, f"Diagram '{id}' not found")

    # Confidentiality gate: a confidential assurance diagram is rendered on demand in memory
    # (never written to disk, per G-f), and only when the confidential store is unlocked —
    # this endpoint is the gated viewer for assurance content that has no on-disk image.
    diagram_type = diag_rec.diagram_type if diag_rec else None
    if diagram_type and _is_confidential_diagram(diagram_path, diagram_type):
        from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context  # noqa: PLC0415

        try:
            unlocked = get_assurance_context().is_available()
        except Exception:  # noqa: BLE001
            unlocked = False
        if not unlocked:
            raise HTTPException(403, "Confidential assurance diagram: unlock the assurance store to view")

    # The on-disk image is the *authored* diagram, so it answers a lensless request and only that one.
    if diag_rec and lens.is_empty:
        svg_path = rendered_image(diag_rec, ".svg")
        if svg_path is not None:
            return Response(content=svg_path.read_bytes(), media_type="image/svg+xml")
    from src.infrastructure.rendering.diagram_builder import render_puml_svg  # noqa: PLC0415
    from src.infrastructure.rendering.laid_out_rendering import stored_layout  # noqa: PLC0415

    laid_out = stored_layout(diagram_path, catalogs.ontology)
    svg, warnings = render_puml_svg(
        reading_body(
            id, diagram_path, lens, picture_sources(catalogs), repo_root, diagram_type=diagram_type,
            laid_out=laid_out,
            stored_svg=rendered_image(diag_rec, ".svg") if diag_rec else None,
        ),
        repo_root,
        diagram_type,
        restyle_prepared=kind_muting(lens, repo_root),
        laid_out=laid_out,
    )
    if svg is None:
        raise HTTPException(500, f"SVG render failed: {'; '.join(warnings)}")
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/diagrams/{artifact_id}/download", tags=[TAG_DIAGRAMS],
    summary="Download a diagram source file",
    # Either image type, chosen by `format`; the attachment disposition is set by the handler. A
    # `Response` rather than a `FileResponse` because a lensed download has no file: it renders.
    response_class=Response,
    responses={**READ_RESPONSES,
               200: {"content": {"image/svg+xml": {}, "image/png": {}},
                     "description": "The rendered diagram, as an attachment"}})
def download_diagram(
    artifact_id: str,
    format: Literal["png", "svg"] = "png",  # noqa: A002
    colour_by: ColourBy = "",
    printed: Printed = [],  # noqa: B006
    ramp: Ramp = "",
    key: Key = [],  # noqa: B006
    legend: Legend = False,
    gradient: Gradient = "",
    element_kind_colouring: ElementKindColouringParameter = "keep",
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    """The diagram as an attachment — the authored image, or the reader's current display.

    A lensed download renders rather than serving the file on disk, and it renders through the *same*
    call the browser display uses. That is the whole reason the lens is a parameter here: "export what
    I am looking at" and "show me this" have to be one render, or the export is a second opinion about
    the display that will drift from it.
    """
    id = artifact_id
    lens = lens_from_query(
        colour_by, printed, ramp, key, legend, gradient, element_kind_colouring
    )
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    diag_rec = s.get_repo().get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram '{id}' not found")
    _refuse_a_matrix(diag_rec)
    suffix = ".svg" if format == "svg" else ".png"
    media = "image/svg+xml" if format == "svg" else "image/png"
    if lens.is_empty:
        path = rendered_image(diag_rec, suffix)
        if path is not None:
            return FileResponse(
                path,
                media_type=media,
                headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
            )
        raise HTTPException(404, f"{format.upper()} not yet rendered — save the diagram first")

    diagram_path = repo_root / DIAGRAM_CATALOG / DIAGRAMS / f"{id}.puml"
    if not diagram_path.exists() and diag_rec.path.exists():
        diagram_path = diag_rec.path
    if not diagram_path.exists():
        raise HTTPException(404, f"Diagram '{id}' not found")
    from src.infrastructure.rendering.laid_out_rendering import stored_layout  # noqa: PLC0415
    from src.infrastructure.rendering.puml_runtime import render_puml_bytes  # noqa: PLC0415

    laid_out = stored_layout(diagram_path, catalogs.ontology)
    image, produced, warnings = render_puml_bytes(
        reading_body(
            id, diagram_path, lens, picture_sources(catalogs), repo_root, diagram_type=diag_rec.diagram_type,
            laid_out=laid_out, stored_svg=rendered_image(diag_rec, ".svg"),
        ),
        repo_root,
        format,
        diag_rec.diagram_type,
        restyle_prepared=kind_muting(lens, repo_root),
        laid_out=laid_out,
    )
    if image is None:
        raise HTTPException(500, f"{format.upper()} render failed: {'; '.join(warnings)}")
    return Response(
        content=image,
        media_type=produced,
        headers={"Content-Disposition": f'attachment; filename="{id}{suffix}"'},
    )
