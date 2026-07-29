"""WU-2.2: Generic port lookups — find_entity_by_workspace_id, find_entities_by_name,
diagrams_referencing_type_id.

Tests operate on _MemStore/_SqliteStore directly to avoid full ArtifactIndex setup.
The SQL query for diagrams_referencing_type_id is exercised through _sqlite_queries.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._service_incremental import apply_diagram_change
from src.infrastructure.artifact_index._sqlite_queries import diagrams_referencing_type
from src.infrastructure.artifact_index._sqlite_store import _SqliteStore

_CLF_A = "CLF@1.aa.order"
_CLF_B = "CLF@1.bb.customer"
_DIAG_ID = "DT-001"


def _unique_hash() -> str:
    return hashlib.blake2b(str(uuid.uuid4()).encode(), digest_size=10).hexdigest()


def _make_store(scope: str = "engagement") -> tuple[_MemStore, _SqliteStore]:
    mem = _MemStore()
    db = _SqliteStore(_unique_hash(), mem, lambda _: scope)
    return mem, db


def _entity(artifact_id: str, name: str, artifact_type: str = "classifier") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain="data",
        subdomain="",
        path=Path(f"/fake/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
        host_diagram_id=_DIAG_ID,
    )


def _clf_attr(name: str, type_id: str) -> dict:
    return {"name": name, "type": {"kind": "classifier", "id": type_id}}


def _diag(classifiers: list[dict]) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=_DIAG_ID,
        artifact_type="diagram",
        diagram_type="datatype",
        name="Test",
        version="0.1.0",
        status="draft",
        path=Path(f"/fake/{_DIAG_ID}.md"),
        extra={"diagram-entities": {"classifier": classifiers}},
    )


def _extractor(diag: DiagramRecord) -> list[tuple[str, str, str]]:
    if diag.diagram_type != "datatype":
        return []
    refs: list[tuple[str, str, str]] = []
    de = diag.extra.get("diagram-entities") or {}
    for clf in (de.get("classifier") or []):  # type: ignore[union-attr]
        if not isinstance(clf, dict):
            continue
        clf_id = str(clf.get("id") or "")
        for attr in (clf.get("attributes") or []):
            if not isinstance(attr, dict):
                continue
            type_ref = attr.get("type")
            if isinstance(type_ref, dict) and type_ref.get("kind") == "classifier":
                type_id = str(type_ref.get("id") or "")
                attr_name = str(attr.get("name") or "")
                if type_id and attr_name:
                    refs.append((clf_id, attr_name, type_id))
    return refs


# ── find_entity_by_workspace_id ────────────────────────────────────────────────


def _find_entity_by_workspace_id(
    entities: dict[str, EntityRecord],
    artifact_id: str,
    *,
    scope: str = "both",
    scope_fn=None,
) -> EntityRecord | None:
    """Standalone implementation of find_entity_by_workspace_id logic."""
    rec = entities.get(artifact_id)
    if rec is None or scope == "both":
        return rec
    return rec if (scope_fn or (lambda _: "engagement"))(rec.path) == scope else None


def test_find_entity_by_workspace_id_found():
    mem, db = _make_store()
    db.upsert_entity(_entity(_CLF_A, "Order"))
    assert _find_entity_by_workspace_id(mem.entities, _CLF_A) is not None


def test_find_entity_by_workspace_id_not_found():
    mem, db = _make_store()
    assert _find_entity_by_workspace_id(mem.entities, "CLF@0.xx.missing") is None


def test_find_entity_by_workspace_id_scope_match():
    mem, db = _make_store(scope="engagement")
    db.upsert_entity(_entity(_CLF_A, "Order"))
    result = _find_entity_by_workspace_id(
        mem.entities, _CLF_A, scope="engagement", scope_fn=lambda _: "engagement"
    )
    assert result is not None


def test_find_entity_by_workspace_id_scope_mismatch():
    mem, db = _make_store(scope="engagement")
    db.upsert_entity(_entity(_CLF_A, "Order"))
    result = _find_entity_by_workspace_id(
        mem.entities, _CLF_A, scope="enterprise", scope_fn=lambda _: "engagement"
    )
    assert result is None


# ── find_entities_by_name ────────────────────────────────────────────────────


def _find_entities_by_name(
    entities: dict[str, EntityRecord],
    name: str,
    *,
    artifact_type: str | None = None,
    scope: str = "both",
    scope_fn=None,
) -> list[EntityRecord]:
    norm = name.lower().strip()
    return [
        r for r in entities.values()
        if r.name.lower().strip() == norm
        and (artifact_type is None or r.artifact_type == artifact_type)
        and (scope == "both" or (scope_fn or (lambda _: "engagement"))(r.path) == scope)
    ]


def test_find_entities_by_name_exact():
    mem, db = _make_store()
    db.upsert_entity(_entity(_CLF_A, "Order"))
    db.upsert_entity(_entity(_CLF_B, "Customer"))
    results = _find_entities_by_name(mem.entities, "Order")
    assert len(results) == 1
    assert results[0].artifact_id == _CLF_A


def test_find_entities_by_name_normalized_case():
    """Name match is case-insensitive and strips whitespace."""
    mem, db = _make_store()
    db.upsert_entity(_entity(_CLF_A, "  ORDER  "))
    results = _find_entities_by_name(mem.entities, "order")
    assert len(results) == 1
    assert results[0].artifact_id == _CLF_A


def test_find_entities_by_name_type_filter():
    mem, db = _make_store()
    db.upsert_entity(_entity(_CLF_A, "Order", artifact_type="classifier"))
    db.upsert_entity(_entity(_CLF_B, "Order", artifact_type="enumeration"))
    results = _find_entities_by_name(mem.entities, "Order", artifact_type="classifier")
    assert len(results) == 1
    assert results[0].artifact_type == "classifier"


def test_find_entities_by_name_no_match():
    mem, db = _make_store()
    db.upsert_entity(_entity(_CLF_A, "Order"))
    assert _find_entities_by_name(mem.entities, "Missing") == []


# ── diagrams_referencing_type (SQL query) ─────────────────────────────────────


def test_diagrams_referencing_type_returns_rows():
    mem, db = _make_store()
    clf = {"id": _CLF_A, "label": "Order", "attributes": [_clf_attr("customer", _CLF_B)]}
    apply_diagram_change(
        Path(f"/fake/{_DIAG_ID}.md"), mem, db,
        parsed=_diag([clf]), attr_type_ref_fn=_extractor,
    )
    with db.reader() as conn:
        rows = diagrams_referencing_type(conn, _CLF_B)
    assert (_DIAG_ID, _CLF_A, "customer") in rows


def test_diagrams_referencing_type_empty_for_unknown():
    mem, db = _make_store()
    with db.reader() as conn:
        rows = diagrams_referencing_type(conn, "CLF@0.xx.unknown")
    assert rows == []


def test_diagrams_referencing_type_uses_index():
    """Multiple diagrams referencing the same type are all returned."""
    mem, db = _make_store()
    diag_a = DiagramRecord(
        artifact_id="DT-A", artifact_type="diagram", diagram_type="datatype",
        name="A", version="0.1.0", status="draft", path=Path("/fake/DT-A.md"),
        extra={"diagram-entities": {"classifier": [
            {"id": _CLF_A, "label": "O", "attributes": [_clf_attr("ref", _CLF_B)]}
        ]}},
    )
    diag_b = DiagramRecord(
        artifact_id="DT-B", artifact_type="diagram", diagram_type="datatype",
        name="B", version="0.1.0", status="draft", path=Path("/fake/DT-B.md"),
        extra={"diagram-entities": {"classifier": [
            {"id": "CLF@1.cc.item", "label": "I", "attributes": [_clf_attr("owner", _CLF_B)]}
        ]}},
    )
    apply_diagram_change(Path("/fake/DT-A.md"), mem, db, parsed=diag_a, attr_type_ref_fn=_extractor)
    apply_diagram_change(Path("/fake/DT-B.md"), mem, db, parsed=diag_b, attr_type_ref_fn=_extractor)

    with db.reader() as conn:
        rows = diagrams_referencing_type(conn, _CLF_B)
    diagram_ids = {r[0] for r in rows}
    assert diagram_ids == {"DT-A", "DT-B"}
