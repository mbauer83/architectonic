"""WU-0.4: Workspace-scoped diagram entities are indexed with bare local_id as artifact_id.

Verifies the full extraction path: extract_diagram_entities, diagram_local_to_full,
extract_diagram_connections, and the scan_mount workspace_types threading.
"""

from __future__ import annotations

from pathlib import Path

from src.application._diagram_entity_extraction import (
    diagram_local_to_full,
    extract_diagram_connections,
    extract_diagram_entities,
)
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._service_incremental import apply_diagram_change

_DIAG_ID = "DT-X"
_DIAG_TYPE = "datatype"


def _make_diag(extra: dict) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=_DIAG_ID,
        artifact_type=_DIAG_TYPE,
        diagram_type=_DIAG_TYPE,
        name="Test Diagram",
        version="0.1.0",
        status="active",
        path=Path("/fake/diagram.md"),
        extra=extra,
    )


# ── extract_diagram_entities ──────────────────────────────────────────────────


def test_workspace_entity_uses_bare_local_id():
    """Classifier (workspace-scoped) gets artifact_id == local_id."""
    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.customer", "label": "Customer"}],
        }
    })
    entities = extract_diagram_entities(diag, workspace_entity_types=frozenset({"classifier"}))
    assert len(entities) == 1
    e = entities[0]
    assert e.artifact_id == "CLF@1.ab.customer"
    assert e.host_diagram_id == _DIAG_ID
    assert e.display_alias == "CLF@1.ab.customer"


def test_diagram_scoped_entity_uses_qualified_id():
    """Non-workspace entity gets artifact_id == '{diag_id}#{type}/{local_id}'."""
    diag = _make_diag({
        "diagram-entities": {
            "attribute": [{"id": "attr-1", "label": "name"}],
        }
    })
    entities = extract_diagram_entities(diag, workspace_entity_types=frozenset())
    assert len(entities) == 1
    assert entities[0].artifact_id == f"{_DIAG_ID}#attribute/attr-1"


def test_mixed_entity_types_both_scopes():
    """Classifier uses bare id; attribute uses qualified id in the same diagram."""
    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.cust", "label": "Cust"}],
            "attribute": [{"id": "a1", "label": "name"}],
        }
    })
    entities = extract_diagram_entities(diag, workspace_entity_types=frozenset({"classifier"}))
    by_type = {e.artifact_type: e for e in entities}
    assert by_type["classifier"].artifact_id == "CLF@1.ab.cust"
    assert by_type["attribute"].artifact_id == f"{_DIAG_ID}#attribute/a1"


def test_host_diagram_id_always_set():
    """host_diagram_id is always set to the owning diagram regardless of scope."""
    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.x", "label": "X"}],
        }
    })
    entities = extract_diagram_entities(diag, workspace_entity_types=frozenset({"classifier"}))
    assert entities[0].host_diagram_id == _DIAG_ID


# ── diagram_local_to_full ─────────────────────────────────────────────────────


def test_local_to_full_workspace_identity():
    """Workspace-scoped local_id maps to itself."""
    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.x", "label": "X"}],
        }
    })
    mapping = diagram_local_to_full(diag, workspace_entity_types=frozenset({"classifier"}))
    assert mapping["CLF@1.ab.x"] == "CLF@1.ab.x"


def test_local_to_full_diagram_scoped():
    """Diagram-scoped local_id maps to qualified form."""
    diag = _make_diag({
        "diagram-entities": {
            "attribute": [{"id": "a1", "label": "name"}],
        }
    })
    mapping = diagram_local_to_full(diag, workspace_entity_types=frozenset())
    assert mapping["a1"] == f"{_DIAG_ID}#attribute/a1"


# ── extract_diagram_connections ───────────────────────────────────────────────


def test_connections_resolve_workspace_endpoints():
    """Connection endpoints referencing workspace-scoped entities use bare ids."""
    diag = _make_diag({
        "diagram-entities": {
            "classifier": [
                {"id": "CLF@1.ab.a", "label": "A"},
                {"id": "CLF@1.ab.b", "label": "B"},
            ],
        },
        "connections": [
            {"source": "CLF@1.ab.a", "target": "CLF@1.ab.b", "conn_type": "has-attribute"},
        ],
    })
    conns = extract_diagram_connections(diag, workspace_entity_types=frozenset({"classifier"}))
    assert len(conns) == 1
    c = conns[0]
    assert c.source == "CLF@1.ab.a"
    assert c.target == "CLF@1.ab.b"


# ── apply_diagram_change ──────────────────────────────────────────────────────


def test_apply_diagram_change_workspace_types(tmp_path):
    """apply_diagram_change indexes workspace-scoped entity with bare artifact_id."""
    from src.infrastructure.artifact_index._sqlite_store import _SqliteStore

    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.cust", "label": "Customer"}],
        }
    })
    mem = _MemStore()
    # Pre-populate mem so path lookup works
    mem.diagrams[_DIAG_ID] = diag
    mem.rebuild_path_indexes()

    import hashlib
    name_hash = hashlib.blake2b(b"test-ws", digest_size=10).hexdigest()
    db = _SqliteStore(name_hash, mem, lambda p: "engagement")

    apply_diagram_change(
        diag.path,
        mem,
        db,
        parsed=diag,
        workspace_types={"datatype": frozenset({"classifier"})},
    )

    # Entity should be re-indexed with bare id
    assert "CLF@1.ab.cust" in mem.entities
    ent = mem.entities["CLF@1.ab.cust"]
    assert ent.host_diagram_id == _DIAG_ID


def test_apply_diagram_change_no_workspace_types(tmp_path):
    """Without workspace_types, classifier gets diagram-qualified id."""
    from src.infrastructure.artifact_index._sqlite_store import _SqliteStore

    diag = _make_diag({
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.cust", "label": "Customer"}],
        }
    })
    mem = _MemStore()
    mem.diagrams[_DIAG_ID] = diag
    mem.rebuild_path_indexes()

    import hashlib
    name_hash = hashlib.blake2b(b"test-no-ws", digest_size=10).hexdigest()
    db = _SqliteStore(name_hash, mem, lambda p: "engagement")

    apply_diagram_change(diag.path, mem, db, parsed=diag)

    qualified_id = f"{_DIAG_ID}#classifier/CLF@1.ab.cust"
    assert qualified_id in mem.entities
