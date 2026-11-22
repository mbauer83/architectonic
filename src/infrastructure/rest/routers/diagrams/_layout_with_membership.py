"""The layout a diagram replacement stores: the whole block a caller sent, or its patch reconciled (D12).

A canvas that removes or adds members saves once: the membership and the layout in one write, so the
stored layout always matches the body that write generates. It sends the layout as a patch against the
layout it read; that patch is applied to the stored layout and then pruned to what the new membership
holds — the same identities the write itself checks a layout against.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from src.application.modeling.diagram_identities import diagram_identities, drawn_instances, strings_of
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, joined_to_its_picture
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout
from src.infrastructure.rendering.layout.diagram_picture import plantuml_drawing
from src.infrastructure.rendering.layout.membership_placement import with_new_members
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams._composition import RenderedComposition
from src.infrastructure.rest.routers.diagrams._write_bodies import EditDiagramGuiBody
from src.infrastructure.write.artifact_write.diagram_layout_patch import reconciled_layout
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file


def layout_to_store(
    artifact_id: str, body: EditDiagramGuiBody, composed: RenderedComposition,
    repo_root: Path, ontology: DeclaresElementKinds,
) -> dict[str, object] | None:
    """*body*'s whole layout, or its patch applied to the stored one and pruned to the new membership."""
    if body.layout_patch is None:
        return body.layout
    if body.layout is not None:
        raise HTTPException(400, "State either layout or layout_patch, not both.")
    record = s.get_repo().get_diagram(artifact_id)
    if record is None or not Path(record.path).exists():
        raise HTTPException(404, f"Diagram '{artifact_id}' not found")
    before = parse_diagram_file(Path(record.path)).frontmatter
    identities = diagram_identities(
        entity_ids_used=composed.entity_ids_used, connection_ids_used=composed.connection_ids_used,
        diagram_entities=composed.diagram_entities, diagram_connections=composed.diagram_connections,
        authored_groupings=body.authored_groupings, bindings=composed.conn_bindings or None,
    )
    previous = drawn_instances(
        strings_of(before.get("entity-ids-used")), before.get("diagram-entities"), before.get("bindings"),
    )
    changed = previous != identities.instances or before.get("authored-groupings") != body.authored_groupings

    def place(layout: Layout) -> Layout:
        picture = plantuml_drawing(composed.puml, repo_root, body.diagram_type).picture
        diagram = joined_to_its_picture(composed.statements(body), layout, ontology)
        return with_new_members(picture, diagram, identities.instances - previous)

    return reconciled_layout(
        stored=before.get(LAYOUT_KEY), patch=body.layout_patch, identities=identities,
        place_members=place if changed else None,
    )
