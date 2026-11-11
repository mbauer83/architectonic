"""A statement a diagram makes about its instances is never indexed as a record (B111).

Extraction turned every list of items with an ``id`` under ``diagram-entities`` into records, whatever the
diagram's type declared. An ArchiMate diagram's ``occurrence`` statements — "draw this model element a
second time" — were indexed as entities of type ``occurrence``, inflated the counts, appeared in
listings, and were exposed to an entity delete that reached the host diagram (B109). A diagram type now
says which keys hold records (``held_record_keys``), and extraction reads only those.
"""

from __future__ import annotations

from pathlib import Path

from src.application._diagram_entity_extraction import (
    NOTHING_HELD,
    extract_diagram_entities,
    held_record_scopes,
)
from src.application.artifacts.query import ArtifactRepository
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.app_bootstrap import get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from tests.support.diagram_held_records import NOTE_ID, repository_with_held_records

ARCHIMATE_ID = "ARC@1700000000.OccAbc.two-drawings"
ARCHIMATE = f"""\
---
artifact-id: {ARCHIMATE_ID}
artifact-type: diagram
name: "Two drawings"
diagram-type: archimate-motivation
version: 0.1.0
status: draft
last-updated: '2026-11-11'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  occurrence:
    - id: occ-second-drawing
      backing_entity_id: GOL@1700000000.AbCdEf.a-goal
  display_labels:
    occ-second-drawing: Again
---
@startuml two-drawings
@enduml
"""

SCOPES = held_record_scopes(get_module_registry().all_diagram_types().items())


def test_an_archimate_occurrence_is_not_indexed_but_held_records_still_are(tmp_path: Path) -> None:
    root = repository_with_held_records(tmp_path, "ENG-OCC")
    (root / "diagram-catalog" / "diagrams" / f"{ARCHIMATE_ID}.puml").write_text(ARCHIMATE, encoding="utf-8")

    entities = ArtifactRepository(shared_artifact_index([root])).list_entities()

    assert not [e for e in entities if e.artifact_type == "occurrence"]
    assert NOTE_ID in {e.artifact_id for e in entities}, "an activity diagram's records are still indexed"


def test_every_diagram_type_scope_names_only_what_its_diagrams_hold() -> None:
    assert SCOPES["archimate-motivation"].keys == frozenset()
    assert SCOPES["gsn"].keys == frozenset({"nodes"})
    assert "note" in SCOPES["activity"].keys
    assert SCOPES["datatype"].workspace_types == frozenset({"classifier", "generalization_set"})


def test_gsn_nodes_are_still_records_and_an_unknown_type_holds_none() -> None:
    gsn = DiagramRecord(
        artifact_id="GSN@1700000000.GsnAbc.case", artifact_type="diagram", name="Case",
        diagram_type="gsn", version="0.1.0", status="draft", path=Path("/tmp/case.puml"),
        extra={"diagram-entities": {"nodes": [{"node_id": "g1", "name": "Safe"}]}},
    )

    assert [e.artifact_id for e in extract_diagram_entities(gsn, SCOPES["gsn"])] == [f"{gsn.artifact_id}#nodes/g1"]
    assert extract_diagram_entities(gsn, NOTHING_HELD) == []
