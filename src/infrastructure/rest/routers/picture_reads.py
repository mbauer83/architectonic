"""What the diagram routes and a candidate's picture routes both answer from, owned by neither router.

A candidate's picture starts from a stored diagram's, and its editor reads the same things a diagram's
does: the diagram read, the geometry, the shapes drawn at a new size. The reading itself is transport
neutral (`src.infrastructure.picture_reading`); this is the REST side of it — the served repository handed
in as `PictureSources`, and one mapping of a reading's refusals onto HTTP answers.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from src.application.artifacts.parsing import parse_diagram_source
from src.application.modeling.diagram_revision import replaced_revision
from src.application.modeling.proposal_standing import standing_subject
from src.application.repo_path_helpers import rendered_dir_for_diagram
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.baseline_standing import BASELINE_STANDING
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.diagram_body_ownership import stated_diagram_entities, written_by_hand
from src.infrastructure.picture_reading.shape_drawing import DrawShapesBody, shape_drawings
from src.infrastructure.picture_reading.sources import PictureSources
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout.diagram_picture import RendererUnavailable
from src.infrastructure.rest.routers import state as s


def repo_root() -> Path:
    """The engagement repository being served; 404 where none is open."""
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(404, "No engagement repository is open")
    return root


def picture_sources(catalogs: RuntimeCatalogs) -> PictureSources:
    """The served repository as a picture's reading takes it, with REST's own element and relation rows."""
    standing = functools.cache(s.baseline_standing_reader)
    return PictureSources(
        repo=s.get_repo(),
        catalogs=catalogs,
        repo_root=s.maybe_engagement_root(),
        registry=lambda: s.get_write_deps(catalogs)[1],
        entity_row=lambda rec: s.entity_to_summary(rec, standing=standing()(standing_subject(rec))),
        connection_row=s.connection_to_dict,
    )


@contextmanager
def renderer_available() -> Iterator[None]:
    """A server that cannot run PlantUML answers 503: the request was not at fault, and may be retried."""
    try:
        yield
    except RendererUnavailable as unavailable:
        raise HTTPException(503, str(unavailable)) from unavailable


def geometry_read(read: Callable[[], dict[str, object]]) -> dict[str, object]:
    """A geometry read, refused as 422 where the picture cannot be drawn or the layout cannot be read."""
    try:
        with renderer_available():
            return read()
    except ValueError as refusal:  # MalformedLayout is a ValueError
        raise HTTPException(422, str(refusal)) from refusal


def drawn_shapes(body: DrawShapesBody) -> dict[str, object]:
    """Each shape of *body* drawn at its new size; 422 where a drawing cannot be read back."""
    try:
        return shape_drawings(body)
    except Unreadable as unreadable:
        raise HTTPException(422, f"This shape cannot be drawn: {unreadable.met}") from unreadable


def rendered_image(d: DiagramRecord, suffix: str) -> Path | None:
    """Resolve a diagram's rendered image, honouring its group-collection subdirectory.

    The rendered tree mirrors the source tree (diagrams/<coll>/x.puml → rendered/<coll>/x.svg),
    so the lookup is anchored on the diagram's own source path rather than the flat rendered
    root — otherwise a grouped diagram's image is never found and the endpoint needlessly
    re-renders on demand (the failure mode that surfaced the stale-body 500).
    """
    root = s.maybe_engagement_root()
    if root is None:
        return None
    rendered_dir = rendered_dir_for_diagram(d.path, root)
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


def _written_by_hand(frontmatter: dict[str, object], body: str, catalogs: RuntimeCatalogs) -> str | None:
    """Why a save may not regenerate this diagram's body; None where it may, or where that cannot be told.

    A stored composition that no longer renders is not a reason to fail the read: the replacement asks the
    same question before it writes, and refuses there.
    """
    try:
        return written_by_hand(
            frontmatter, body, repo=s.get_repo(), repo_root=repo_root(), diagram_types=catalogs.diagram_types,
        )
    except ValueError:
        return None


def diagram_read(artifact_id: str, catalogs: RuntimeCatalogs) -> dict[str, Any]:
    """A stored diagram as the diagram read answers it; 404 where *artifact_id* names no diagram."""
    result = s.get_repo().read_artifact(artifact_id, mode="full")
    if result is None or result.get("record_type") != "diagram":
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    result["revision"] = replaced_revision(str(result.get("puml_source", "")))
    diag_rec = s.get_repo().get_diagram(artifact_id)
    if diag_rec:
        # As a composition carries them (`stated_diagram_entities`), which is what the editor sends back: the
        # binding shorthand the persist path strips restored, since `occurrencesOf` matches on
        # `backing_entity_id`, and the diagram's own connections under `_connections`.
        diagram_entities = stated_diagram_entities(diag_rec.extra) or {}
        result["diagram_entities"] = diagram_entities or None
        _png = rendered_image(diag_rec, ".png")
        result["rendered_filename"] = _png.name if _png is not None else None
        result["is_global"] = s.is_global(diag_rec.path)
        result[BASELINE_STANDING] = s.baseline_standing_reader()(standing_subject(diag_rec)).to_mapping()
        parsed = parse_diagram_source(str(result.get("puml_source", "")))
        frontmatter = parsed["frontmatter"]
        entity_ids_used = frontmatter.get("entity-ids-used")
        connection_ids_used = frontmatter.get("connection-ids-used")
        if isinstance(entity_ids_used, list):
            result["entity_ids_used"] = [str(x) for x in entity_ids_used]
        if isinstance(connection_ids_used, list):
            result["connection_ids_used"] = [str(x) for x in connection_ids_used]
        authored_groupings = frontmatter.get("authored-groupings")
        if isinstance(authored_groupings, list):
            result["authored_groupings"] = [g for g in authored_groupings if isinstance(g, dict)]
        if isinstance(layout := frontmatter.get(LAYOUT_KEY), dict):
            result["layout"] = layout
        result["viewpoint"] = frontmatter.get("viewpoint")
        if not result["is_global"]:
            result["written_by_hand"] = _written_by_hand(frontmatter, str(parsed["puml_body"]), catalogs)
        dt = catalogs.diagram_types.find_diagram_type(diag_rec.diagram_type)
        if dt:
            # Two hooks, because the module is doing two things. A replacement for a field the
            # envelope declares goes into that field; the module's own keys go under `type_extras`,
            # which is the one level of this response whose properties are the module's to decide.
            resolved = dt.resolve_diagram_entities(parsed, diagram_entities)
            if resolved is not None:
                result["diagram_entities"] = resolved
            result["type_extras"] = dt.read_diagram_extras(parsed) or None
    return result
