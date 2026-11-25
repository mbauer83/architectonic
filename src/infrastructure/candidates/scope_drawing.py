"""What a candidate, or a scope about to become one, is drawn on: a stored diagram, else a generated view.

Owner decision Q36: a scope chosen from a viewpoint or a search is drawn on a stored diagram where one
applies, else on a view generated from it. The generated view is the model's entities in the scope and the
relations among them, laid out by PlantUML as a viewpoint's ad hoc picture is, and read into the geometry the
canvas draws — so the same canvas marks, frames and ticks it as it does a stored diagram.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.infrastructure.diagram_composition import DiagramComposition, render_composition
from src.infrastructure.rendering.layout.diagram_geometry import geometry_response, stored_geometry
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

#: The diagram type a generated view is drawn as: the layered ArchiMate picture a viewpoint draws ad hoc.
GENERATED_VIEW_TYPE = "archimate-layered"


class NoStoredDiagram(LookupError):
    """The diagram named to draw on is not stored."""


def stored_drawing(repo: Any, diagram: str, root: Path, ontology: DeclaresElementKinds) -> dict[str, Any]:
    """The geometry of the stored *diagram*, as it is drawn now."""
    record = repo.get_diagram(diagram)
    if record is None:
        raise NoStoredDiagram(f"No diagram {diagram} is stored.")
    return stored_geometry(parse_diagram_file(record.path), record.artifact_id, root, ontology)


def generated_drawing(
    repo: Any, scope: Iterable[str], name: str, root: Path, ontology: DeclaresElementKinds,
) -> dict[str, Any] | None:
    """A view generated from the model's entities in *scope* and the relations among them; None for none."""
    entities = [entity.artifact_id for ref in dict.fromkeys(scope) if (entity := repo.get_entity(ref)) is not None]
    if not entities:
        return None
    inside = set(entities)
    relations = [
        str(conn["artifact_id"]) for conn in repo.candidate_connections_for_entities(entities)
        if str(conn["source"]) in inside and str(conn["target"]) in inside
    ]
    body = DiagramComposition(
        diagram_type=GENERATED_VIEW_TYPE, name=name, entity_ids=entities, connection_ids=relations,
    )
    composed = render_composition(body, repo=repo, repo_root=root)
    return geometry_response(
        composed.puml, "", {**composed.statements(body), "artifact-id": ""}, root, ontology, generated=True,
    )
