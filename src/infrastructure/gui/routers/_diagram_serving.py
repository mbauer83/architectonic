"""Diagram image-serving endpoints: rendered PNG, on-demand SVG, and download.

The SVG endpoint doubles as the confidential-assurance viewer: a confidential assurance
diagram (no on-disk image, per rule G-f) is rendered on demand in memory and served only
when the confidential store is unlocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from src.application.repo_path_helpers import rendered_dir_for_diagram
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, RENDERED
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS, media_response

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
def get_diagram_svg(artifact_id: str) -> Response:
    id = artifact_id
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

    if diag_rec:
        svg_path = _rendered_path(diag_rec, ".svg")
        if svg_path is not None:
            return Response(content=svg_path.read_bytes(), media_type="image/svg+xml")
    from src.infrastructure.rendering.diagram_builder import render_puml_svg
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    parsed = parse_diagram_file(diagram_path)
    svg, warnings = render_puml_svg(parsed.puml_body, repo_root, diagram_type)
    if svg is None:
        raise HTTPException(500, f"SVG render failed: {'; '.join(warnings)}")
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/diagrams/{artifact_id}/download", tags=[TAG_DIAGRAMS],
    summary="Download a diagram source file",
    # Either image type, chosen by `format`; the attachment disposition is set by the handler.
    response_class=FileResponse,
    responses={**READ_RESPONSES,
               200: {"content": {"image/svg+xml": {}, "image/png": {}},
                     "description": "The rendered diagram, as an attachment"}})
def download_diagram(artifact_id: str, format: Literal["png", "svg"] = "png") -> FileResponse:
    id = artifact_id
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    diag_rec = s.get_repo().get_diagram(id)
    if diag_rec is None:
        raise HTTPException(404, f"Diagram '{id}' not found")
    suffix = ".svg" if format == "svg" else ".png"
    media = "image/svg+xml" if format == "svg" else "image/png"
    path = _rendered_path(diag_rec, suffix)
    if path is not None:
        return FileResponse(
            path,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
        )
    raise HTTPException(404, f"{format.upper()} not yet rendered — save the diagram first")
