"""An unsaved composition drawn into the geometry an editor arranges, over the picture it starts from.

A diagram's editor and a candidate's both draw the same thing: a composition (`DiagramComposition`) with the
elements and relations an edit session proposes, laid over the frontmatter of the picture the session opened
on. For a diagram that is the stored diagram; for a candidate it is where the candidate's picture starts
(`candidates.picture`). One drawing, so the two editors cannot come to draw a session differently.

A composition that draws nothing is the empty picture, not a refusal: PlantUML has no picture of nothing to
read, and an editor opening on a candidate that holds nothing yet still needs a canvas to start on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.diagram_composition import render_composition
from src.infrastructure.rendering.layout.diagram_geometry import empty_geometry, geometry_response
from src.infrastructure.rest.routers.diagrams._geometry_proposals import GeometryPreviewBody


def draws_nothing(body: GeometryPreviewBody) -> bool:
    """Whether *body* draws no element at all, the model's or a proposed one."""
    return not body.entity_ids and not body.proposed_elements


def previewed_geometry(
    body: GeometryPreviewBody, base: Mapping[str, object], *, artifact_id: str, repo: Any, root: Path,
    catalogs: RuntimeCatalogs, previous: frozenset[str] = frozenset(),
    lensed: Callable[[str], str] | None = None, restyle: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """*body* drawn over the frontmatter *base*; *previous* are the instances the picture already placed.

    *lensed* turns the composed body into the one a reader's lens draws, *restyle* restyles it as drawn.
    Raises ValueError where a proposal or the picture cannot be drawn.
    """
    if draws_nothing(body):
        return empty_geometry(artifact_id, body.name)
    elements, relations = body.proposals(catalogs, repo)
    composed = render_composition(
        body, repo=repo, repo_root=root, proposed_entities=elements, proposed_connections=relations,
    )
    frontmatter = {**base, **composed.statements(body)}
    puml = lensed(composed.puml) if lensed else composed.puml
    return geometry_response(
        puml, artifact_id, frontmatter, root, catalogs.ontology, generated=True,
        arrangement=body.arrangement, previous=previous, restyle_prepared=restyle,
    )
