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
from src.infrastructure.candidates.repository import NotStored
from src.infrastructure.diagram_composition import DiagramComposition, render_composition
from src.infrastructure.rendering.layout.diagram_geometry import geometry_response, stored_geometry
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

#: The diagram type a generated view is drawn as: the layered ArchiMate picture a viewpoint draws ad hoc.
GENERATED_VIEW_TYPE = "archimate-layered"


def drawing(
    repo: Any, diagram: str | None, scope: Iterable[str], name: str, root: Path, ontology: DeclaresElementKinds,
) -> dict[str, Any] | None:
    """The stored *diagram*'s geometry, else a view generated from *scope*; None where there is neither."""
    return (stored_drawing(repo, diagram, root, ontology) if diagram
            else generated_drawing(repo, scope, name, root, ontology))


def stored_drawing(repo: Any, diagram: str, root: Path, ontology: DeclaresElementKinds) -> dict[str, Any]:
    """The geometry of the stored *diagram*, as it is drawn now."""
    record = repo.get_diagram(diagram)
    if record is None:
        raise NotStored(f"No diagram {diagram} is stored.")
    return stored_geometry(parse_diagram_file(record.path), record.artifact_id, root, ontology)


def generated_drawing(
    repo: Any, scope: Iterable[str], name: str, root: Path, ontology: DeclaresElementKinds,
) -> dict[str, Any] | None:
    """A view generated from the model's entities in *scope* and the relations among them; None for none."""
    body = generated_composition(repo, scope, name)
    if not body.entity_ids:
        return None
    composed = render_composition(body, repo=repo, repo_root=root)
    return geometry_response(
        composed.puml, "", {**composed.statements(body), "artifact-id": ""}, root, ontology, generated=True,
    )


def generated_composition(repo: Any, scope: Iterable[str], name: str) -> DiagramComposition:
    """What a generated view of *scope* draws: the model's entities in it, each once, and the relations among
    them. The one statement of it, for the view drawn on read and for the diagram it is saved as."""
    entities = [entity.artifact_id for ref in dict.fromkeys(scope) if (entity := repo.get_entity(ref)) is not None]
    inside = set(entities)
    relations = [
        str(conn["artifact_id"]) for conn in repo.candidate_connections_for_entities(entities)
        if str(conn["source"]) in inside and str(conn["target"]) in inside
    ] if entities else []
    return DiagramComposition(
        diagram_type=GENERATED_VIEW_TYPE, name=name, entity_ids=entities, connection_ids=relations,
    )
