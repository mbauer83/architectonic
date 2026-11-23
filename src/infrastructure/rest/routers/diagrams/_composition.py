"""Render the composition requested by the diagram preview and write routes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.artifact_id import stable_conn_id
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.diagram_selection import resolve_diagram_selection
from src.infrastructure.rest.routers._failures import rejected_input
from src.infrastructure.rest.routers.diagrams._write_bodies import DiagramComposition


def _split_diagram_entities(
    diagram_entities: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Separate the transport-only `_connections` key from entity data."""
    if diagram_entities is None:
        return None, None
    conns = diagram_entities.get("_connections")
    if conns is None:
        return diagram_entities, None
    clean = {k: v for k, v in diagram_entities.items() if k != "_connections"}
    return clean or None, conns if isinstance(conns, list) else None


def _extract_conn_bindings(
    connections: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Strip `backing_conn_id` from connections; return (clean, binding_dicts)."""
    if not connections:
        return connections, []
    bindings: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            clean.append(conn)
            continue
        backing_id = conn.get("backing_conn_id")
        conn_id = conn.get("id")
        if backing_id and conn_id:
            bindings.append({
                "id": f"bind-conn-{conn_id}",
                "subject": {"kind": "connection", "id": conn_id},
                "correspondence_kind": "represents",
                "target": {"connection_id": backing_id},
            })
        clean.append({k: v for k, v in conn.items() if k != "backing_conn_id"})
    return clean or None, bindings


@dataclass(frozen=True)
class RenderedComposition:
    """One composition, resolved and rendered — the same way for every surface that shows it."""

    entities: list[Any]
    connections: list[Any]
    entity_ids_used: list[str]
    connection_ids_used: list[str]
    diagram_entities: dict[str, Any] | None
    diagram_connections: list[dict[str, Any]] | None
    conn_bindings: list[dict[str, Any]]
    puml: str

    def statements(self, body: DiagramComposition) -> dict[str, Any]:
        """The membership and grouping declarations that key the rendered picture."""
        return {
            "name": body.name, "diagram-type": body.diagram_type,
            "entity-ids-used": self.entity_ids_used, "connection-ids-used": self.connection_ids_used,
            "diagram-entities": self.diagram_entities, "connections": self.diagram_connections,
            "authored-groupings": body.authored_groupings, "bindings": self.conn_bindings,
        }


def render_composition(
    body: DiagramComposition, *, repo: Any, repo_root: Path,
    proposed_entities: tuple[EntityRecord, ...] = (), proposed_connections: tuple[ConnectionRecord, ...] = (),
) -> RenderedComposition:
    """Resolve a composition and render it, once, for preview and for both writes.

    The three surfaces used to assemble this themselves, and drifted twice over: preview never passed
    `authored_groupings`, so custom boxes were invisible until the write; and preview rendered with
    connection *bindings* still attached while the writes stripped them first, so the two were not
    rendering the same input either. A preview is only worth having if it is the write's own picture.
    """
    from src.infrastructure.icons.diagram_icons import DiagramIconSource  # noqa: PLC0415
    from src.infrastructure.icons.library_source import LibraryIconSource  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_body_preparation import with_icons_prepared  # noqa: PLC0415

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo, body.entity_ids, body.connection_ids
    )
    entities.extend(proposed_entities)
    # A draft can change the annotations on an already selected model relation.
    # Preserve its position and its identity in the drawing, as in the eventual write.
    proposals = {stable_conn_id(c.artifact_id): c for c in proposed_connections}
    connections = [proposals.pop(stable_conn_id(c.artifact_id), c) for c in connections]
    connections.extend(proposals.values())
    entity_ids_used.extend(entity.artifact_id for entity in proposed_entities)
    connection_ids_used.extend(connection.artifact_id for connection in proposals.values())
    de, dc = _split_diagram_entities(body.diagram_entities)
    try:
        de = with_icons_prepared(de) if de is not None else None
    except ValueError as exc:  # an upload the normaliser refuses is the caller's to correct
        raise rejected_input(str(exc), field="diagram_entities") from exc
    dc, conn_bindings = _extract_conn_bindings(dc)
    puml = generate_archimate_puml_body(
        body.name,
        entities,
        connections,
        diagram_type=body.diagram_type,
        repo_root=repo_root,
        diagram_entities=de,
        diagram_connections=dc,
        authored_groupings=body.authored_groupings,
        # The diagram's own icons first, uploads not yet saved included, so a preview draws what the save will.
        icon_source=DiagramIconSource(de, LibraryIconSource(repo)),
    )
    return RenderedComposition(
        entities=entities, connections=connections,
        entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
        diagram_entities=de, diagram_connections=dc, conn_bindings=conn_bindings, puml=puml,
    )
