"""WU-2.1: attribute_type_refs table is populated and kept consistent.

Tests cover: upsert populates rows, edit replaces rows, delete clears rows,
rebuild from mem produces the same result as incremental (rebuild==incremental).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._service_incremental import apply_diagram_change
from src.infrastructure.artifact_index._sqlite_store import _SqliteStore

_DIAG_PATH = Path("/fake/DT-001.md")
_DIAG_ID = "DT-001"
_CLF_A = "CLF@1.aa.order"
_CLF_B = "CLF@1.bb.customer"


def _unique_hash() -> str:
    return hashlib.blake2b(str(uuid.uuid4()).encode(), digest_size=10).hexdigest()


def _make_store() -> tuple[_MemStore, _SqliteStore]:
    mem = _MemStore()
    db = _SqliteStore(_unique_hash(), mem, lambda _: "engagement")
    return mem, db


def _make_diag(
    diagram_id: str,
    extra: dict,
    diagram_type: str = "datatype",
    path: Path | None = None,
) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=diagram_id,
        artifact_type="diagram",
        diagram_type=diagram_type,
        name="Test",
        version="0.1.0",
        status="draft",
        path=path or Path(f"/fake/{diagram_id}.md"),
        extra=extra,
    )


def _classifier_extra(classifiers: list[dict]) -> dict:
    return {"diagram-entities": {"classifier": classifiers}}


def _clf(clf_id: str, attrs: list[dict]) -> dict:
    return {"id": clf_id, "label": clf_id, "attributes": attrs}


def _clf_attr(name: str, type_id: str) -> dict:
    return {"name": name, "type": {"kind": "classifier", "id": type_id}}


def _prim_attr(name: str, pname: str) -> dict:
    return {"name": name, "type": {"kind": "primitive", "name": pname}}


def _query_refs(db: _SqliteStore, diagram_id: str) -> list[tuple[str, str, str, str]]:
    with db.reader() as conn:
        rows = conn.execute(
            "SELECT diagram_id, classifier_local_id, attr_name, type_id "
            "FROM attribute_type_refs WHERE diagram_id=? ORDER BY classifier_local_id, attr_name",
            (diagram_id,),
        ).fetchall()
    return [tuple(row) for row in rows]  # type: ignore[return-value]


def _query_refs_for_type(db: _SqliteStore, type_id: str) -> list[tuple]:
    with db.reader() as conn:
        rows = conn.execute(
            "SELECT diagram_id, classifier_local_id, attr_name, type_id "
            "FROM attribute_type_refs WHERE type_id=?",
            (type_id,),
        ).fetchall()
    return [tuple(row) for row in rows]  # type: ignore[return-value]


def _extractor(diag: DiagramRecord) -> list[tuple[str, str, str]]:
    if diag.diagram_type != "datatype":
        return []
    refs: list[tuple[str, str, str]] = []
    de = diag.extra.get("diagram-entities") or {}
    for clf in (de.get("classifier") or []):
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


def _apply(mem: _MemStore, db: _SqliteStore, diag: DiagramRecord | None, path: Path = _DIAG_PATH) -> None:
    apply_diagram_change(path, mem, db, parsed=diag, attr_type_ref_fn=_extractor)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_upsert_populates_rows():
    """Inserting a datatype diagram with a classifier-typed attribute creates a row."""
    mem, db = _make_store()
    diag = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("customer", _CLF_B)])]))
    _apply(mem, db, diag)
    rows = _query_refs(db, _DIAG_ID)
    assert rows == [(_DIAG_ID, _CLF_A, "customer", _CLF_B)]


def test_edit_replaces_rows():
    """Editing a diagram with the same id replaces the old type-ref rows."""
    mem, db = _make_store()
    diag_v1 = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("old_attr", _CLF_B)])]))
    _apply(mem, db, diag_v1)

    diag_v2 = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("new_attr", _CLF_B)])]))
    _apply(mem, db, diag_v2)

    rows = _query_refs(db, _DIAG_ID)
    assert rows == [(_DIAG_ID, _CLF_A, "new_attr", _CLF_B)]


def test_delete_removes_rows():
    """Deleting a diagram removes its attribute_type_refs entries."""
    mem, db = _make_store()
    diag = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("attr", _CLF_B)])]))
    _apply(mem, db, diag)
    _apply(mem, db, None)
    assert _query_refs(db, _DIAG_ID) == []


def test_non_datatype_diagram_produces_no_rows():
    """An extractor that ignores non-datatype diagrams inserts no rows."""
    mem, db = _make_store()
    diag = _make_diag(
        _DIAG_ID,
        _classifier_extra([_clf(_CLF_A, [_clf_attr("attr", _CLF_B)])]),
        diagram_type="c4",
    )
    _apply(mem, db, diag)
    assert _query_refs(db, _DIAG_ID) == []


def test_primitive_attrs_not_indexed():
    """Classifier-typed attrs are indexed; primitive-typed attrs are not."""
    mem, db = _make_store()
    diag = _make_diag(
        _DIAG_ID,
        _classifier_extra([_clf(_CLF_A, [
            _clf_attr("ref_attr", _CLF_B),
            _prim_attr("prim_attr", "String"),
        ])]),
    )
    _apply(mem, db, diag)
    rows = _query_refs(db, _DIAG_ID)
    assert len(rows) == 1
    assert rows[0][2] == "ref_attr"


def test_type_id_index_lookup():
    """Rows are findable by type_id via the index (used by diagrams_referencing_type_id)."""
    mem, db = _make_store()
    diag = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("attr", _CLF_B)])]))
    _apply(mem, db, diag)
    rows = _query_refs_for_type(db, _CLF_B)
    assert len(rows) == 1
    assert rows[0][0] == _DIAG_ID


def test_rebuild_matches_incremental():
    """Full rebuild produces same attribute_type_refs as incremental population."""
    mem, db = _make_store()
    diag = _make_diag(_DIAG_ID, _classifier_extra([_clf(_CLF_A, [_clf_attr("attr", _CLF_B)])]))
    _apply(mem, db, diag)
    rows_incremental = _query_refs(db, _DIAG_ID)

    db.rebuild()
    rows_rebuilt = _query_refs(db, _DIAG_ID)
    assert rows_rebuilt == rows_incremental


def test_multiple_classifiers_and_attrs():
    """Multiple classifiers with multiple refs each are all indexed."""
    mem, db = _make_store()
    clf_c = "CLF@1.cc.item"
    diag = _make_diag(
        _DIAG_ID,
        _classifier_extra([
            _clf(_CLF_A, [_clf_attr("customer", _CLF_B), _clf_attr("item", clf_c)]),
            _clf(_CLF_B, [_clf_attr("order", _CLF_A)]),
        ]),
    )
    _apply(mem, db, diag)
    rows = _query_refs(db, _DIAG_ID)
    assert len(rows) == 3
    attr_names = {r[2] for r in rows}
    assert attr_names == {"customer", "item", "order"}
