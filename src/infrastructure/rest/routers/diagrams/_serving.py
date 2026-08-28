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
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from src.application.repo_path_helpers import rendered_dir_for_diagram
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, RENDERED
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS, media_response
from src.infrastructure.rest.routers.diagrams._reading_lens_request import lens_from_query
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


def _rendered_path(d: DiagramRecord, suffix: str) -> Path | None:
    """Resolve a diagram's rendered image, honouring its group-collection subdirectory.

    The rendered tree mirrors the source tree (diagrams/<coll>/x.puml → rendered/<coll>/x.svg),
    so the lookup is anchored on the diagram's own source path rather than the flat rendered
    root — otherwise a grouped diagram's image is never found and the endpoint needlessly
    re-renders on demand (the failure mode that surfaced the stale-body 500).
    """
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        return None
    rendered_dir = rendered_dir_for_diagram(d.path, repo_root)
    candidate = rendered_dir / f"{d.artifact_id}{suffix}"
    if candidate.exists():
        return candidate
    if rendered_dir.is_dir():
        parts = d.artifact_id.split(".")
        if len(parts) >= 3:
            legacy = rendered_dir / f"{'.'.join(parts[2:])}{suffix}"
            if legacy.exists():
                return legacy
        for f in rendered_dir.iterdir():
            if f.suffix == suffix and f.stem in d.artifact_id:
                return f
    return None


def _declared_type_labels(catalogs: RuntimeCatalogs) -> dict[str, str]:
    """What each element type is called, where its own name is not it — keyed as a legend spells it.

    The ontology states this (`EntityTypeInfo.label`) so that every surface naming a type for a reader
    says the same thing; the legend takes it rather than deriving a second answer. Keyed on the spaced
    lower-case form because that is what `readable_label` has in hand at the point it decides.
    """
    return {
        info.artifact_type.replace("-", " "): info.label
        for info in catalogs.ontology.all_entity_types().values()
        if info.label
    }


def _lensed_body(
    artifact_id: str,
    diagram_path: Path,
    lens: ReadingLens,
    catalogs: RuntimeCatalogs,
    repo_root: Path,
) -> str:
    """The diagram's body with the lens applied, or its authored body when the lens is empty.

    The entities are resolved by `resolve_placed_entities` — the same function the attribute panel
    asks — so a reader cannot be offered an attribute here that the panel would not have listed, nor
    the other way round. The snapshot comes from `configured_registry_snapshot`, so the lens reads
    attributes under exactly the reach the rest of the surface uses.

    The catalogues are *given*, not read from process state: they arrive through the same freshness
    dependency the attribute panel takes, which is what lets a test override them and what
    `test_runtime_catalogs_have_one_accessor` requires of a router. It caught this module reading them
    directly.
    """
    from src.application.viewpoints.diagram_attribute_panel import (  # noqa: PLC0415
        offers_for_diagram,
        palette_members,
        palette_unset,
    )
    from src.application.viewpoints.diagram_reading_lens import apply_reading_lens  # noqa: PLC0415
    from src.application.viewpoints.placed_occurrences import (  # noqa: PLC0415
        placed_connection_triples,
        resolve_placed_entities,
    )
    from src.infrastructure.rendering.diagram_legend_for_reading import (  # noqa: PLC0415
        body_with_reading_legend,
    )
    from src.infrastructure.rendering.diagram_notation_in_use import notation_in_use  # noqa: PLC0415
    from src.infrastructure.viewpoints_snapshot import configured_registry_snapshot  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    body = parse_diagram_file(diagram_path).puml_body
    if lens.is_empty:
        return body
    repo = s.get_repo()
    diag_rec = repo.get_diagram(artifact_id)
    if diag_rec is None:
        return body
    _, registry, _ = s.get_write_deps(catalogs)
    registries = configured_registry_snapshot(catalogs, repo.repo_roots)
    entities = resolve_placed_entities(dict(diag_rec.extra), registry)
    # The same offers the panel showed the reader, so "palette or ramp" is decided once and the
    # picture, its legend and the controls cannot disagree about an attribute. Resolved here rather
    # than inside either consumer because both need the answer and it is one lookup.
    offers = offers_for_diagram(
        entities,
        repo_root,
        specialization_catalog=catalogs.specializations,
        profile_registry=catalogs.profiles,
    ) if lens.colour_by else None
    palette = palette_members(offers, lens.colour_by) if offers is not None else ()
    # The member a schema declares as its default: what a reader sees on an entity nobody has
    # assessed, so it is drawn as unset rather than given a place on the scale.
    unset = palette_unset(offers, lens.colour_by) if offers is not None else None
    lensed = apply_reading_lens(
        body, entities, lens=lens, read_access=repo, registries=registries, palette=palette,
        unset=unset
    )
    if not lens.legend:
        return lensed
    # The legend composes over the lensed body rather than being woven into it: it is appended, and
    # keeping it a second step is what lets a reader ask for one on an otherwise untouched diagram.
    notation = notation_in_use(
        body,
        placed_connection_triples(dict(diag_rec.extra), registry),
        repo_root=repo_root,
        relation_notations=catalogs.connections.all_relation_notations(),
    )
    return body_with_reading_legend(
        lensed,
        lens=lens,
        declarations=notation.declarations,
        members=palette,
        unset=unset,
        declared_labels=_declared_type_labels(catalogs),
        connection_notations=notation.connection_notations,
        nested_types=notation.nested_types,
    )


@router.get("/api/diagram-images/{filename}", tags=[TAG_DIAGRAMS], summary="Serve a rendered diagram image",
    response_class=FileResponse,
    responses={**READ_RESPONSES, **media_response("image/png", "The rendered image")})
def get_diagram_image(filename: str) -> FileResponse:
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    rendered_root = repo_root / DIAGRAM_CATALOG / RENDERED
    path = rendered_root / filename
    if not path.exists():
        # Group collections mirror the source tree under rendered/<coll>/; the rendered
        # filename is artifact-id-unique, so resolve it wherever it lives in that tree.
        found = next((p for p in rendered_root.rglob(filename) if p.is_file()), None)
        if found is None:
            raise HTTPException(404, f"Rendered image not found: {filename}")
        path = found
    return FileResponse(path, media_type="image/png")


@router.get("/api/diagrams/{artifact_id}/svg", tags=[TAG_DIAGRAMS], summary="Serve a diagram as SVG",
    response_class=Response,
    responses={**READ_RESPONSES, **media_response("image/svg+xml", "The rendered diagram")})
def get_diagram_svg(
    artifact_id: str,
    colour_by: Annotated[str, Query(description="Attribute to colour the drawn elements by")] = "",
    printed: Annotated[
        list[str], Query(alias="print", description="Attribute values to print with the elements")
    ] = [],  # noqa: B006
    ramp: Annotated[
        str, Query(description="A gradient for a continuous attribute, as `near:far` in #rrggbb")
    ] = "",
    key: Annotated[
        list[str], Query(description="A colour for one value, as `member:#rrggbb`; repeatable")
    ] = [],  # noqa: B006
    legend: Annotated[
        bool, Query(description="Draw a legend explaining the notation this diagram uses")
    ] = False,
    gradient: Annotated[
        str,
        Query(description="Which named gradient an ordered value set is spread along — "
                          "`red-green`, `yellow-blue` for a red/green colour-blind reader, or "
                          "either reversed (`green-red`, `blue-yellow`) for a scale whose high end "
                          "is the bad one. Absent leaves a graded set on the default and a ramp on "
                          "its magnitude pair"),
    ] = "",
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    id = artifact_id
    lens = lens_from_query(colour_by, printed, ramp, key, legend, gradient)
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    diag_rec = s.get_repo().get_diagram(id)
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
        svg_path = _rendered_path(diag_rec, ".svg")
        if svg_path is not None:
            return Response(content=svg_path.read_bytes(), media_type="image/svg+xml")
    from src.infrastructure.rendering.diagram_builder import render_puml_svg  # noqa: PLC0415

    svg, warnings = render_puml_svg(
        _lensed_body(id, diagram_path, lens, catalogs, repo_root), repo_root, diagram_type
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
    colour_by: Annotated[str, Query(description="Attribute the current display is coloured by")] = "",
    printed: Annotated[
        list[str], Query(alias="print", description="Attribute values the current display prints")
    ] = [],  # noqa: B006
    ramp: Annotated[
        str, Query(description="A gradient for a continuous attribute, as `near:far` in #rrggbb")
    ] = "",
    key: Annotated[
        list[str], Query(description="A colour for one value, as `member:#rrggbb`; repeatable")
    ] = [],  # noqa: B006
    legend: Annotated[
        bool, Query(description="Draw a legend explaining the notation this diagram uses")
    ] = False,
    gradient: Annotated[
        str,
        Query(description="Which named gradient an ordered value set is spread along — "
                          "`red-green`, `yellow-blue` for a red/green colour-blind reader, or "
                          "either reversed (`green-red`, `blue-yellow`) for a scale whose high end "
                          "is the bad one. Absent leaves a graded set on the default and a ramp on "
                          "its magnitude pair"),
    ] = "",
    catalogs: RuntimeCatalogs = Depends(fresh_viewpoints_runtime_catalogs_dependency),
) -> Response:
    """The diagram as an attachment — the authored image, or the reader's current display.

    A lensed download renders rather than serving the file on disk, and it renders through the *same*
    call the browser display uses. That is the whole reason the lens is a parameter here: "export what
    I am looking at" and "show me this" have to be one render, or the export is a second opinion about
    the display that will drift from it.
    """
    id = artifact_id
    lens = lens_from_query(colour_by, printed, ramp, key, legend, gradient)
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    diag_rec = s.get_repo().get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram '{id}' not found")
    suffix = ".svg" if format == "svg" else ".png"
    media = "image/svg+xml" if format == "svg" else "image/png"
    if lens.is_empty:
        path = _rendered_path(diag_rec, suffix)
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
    from src.infrastructure.rendering.puml_runtime import render_puml_bytes  # noqa: PLC0415

    image, produced, warnings = render_puml_bytes(
        _lensed_body(id, diagram_path, lens, catalogs, repo_root), repo_root, format, diag_rec.diagram_type
    )
    if image is None:
        raise HTTPException(500, f"{format.upper()} render failed: {'; '.join(warnings)}")
    return Response(
        content=image,
        media_type=produced,
        headers={"Content-Disposition": f'attachment; filename="{id}{suffix}"'},
    )
