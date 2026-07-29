"""Build the FTS row for a diagram, including the names of the entities it contains.

A diagram is discoverable by its own title/type and by the names of its member
entities — diagram-local nodes (resolved via ``host_diagram_id``) and bound workspace
entities (matrix axes, C4 bindings). The resolved member names occupy the
``member_names`` FTS column.
"""

from __future__ import annotations

from src.application._diagram_entity_extraction import diagram_member_text
from src.domain.ontology_representation.artifact_types import DiagramRecord

from ._mem_store import _MemStore


def diagram_fts_row(rec: DiagramRecord, mem: _MemStore) -> tuple[str, str, str, str, str]:
    def name_of(entity_id: str) -> str | None:
        entity = mem.entities.get(entity_id)
        return entity.name if entity is not None else None

    local_names = [name for eid in mem.entities_by_diagram.get(rec.artifact_id, ()) if (name := name_of(eid))]
    member_names = diagram_member_text(rec, local_names=local_names, name_of=name_of)
    return (rec.artifact_id, rec.name, rec.diagram_type, rec.artifact_type, member_names)
