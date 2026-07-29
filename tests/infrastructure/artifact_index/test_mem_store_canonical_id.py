"""``_MemStore.canonical_id`` on connection-shaped ids (regression, found during WU-F3a).

``stable_id()`` is entity-shaped (``PREFIX@epoch.random[.slug]``): it strips whatever comes
after the *last* dot. Applied blindly to a whole composite connection id
(``source---target@@type``), the last dot falls inside the target segment, so the
``@@type`` suffix (and part of the target) gets silently dropped — making two different
connection types between the same two entities collide on the same "stable id" and produce
a false-positive match for a connection that was never actually created. The fix reuses the
existing, already-tested ``src.domain.artifact_id.stable_conn_id`` (normalizes each endpoint
independently) rather than inventing a second connection-id normalizer.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.infrastructure.artifact_index._mem_store import _MemStore


def _connection(artifact_id: str, source: str, target: str, conn_type: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("dummy.outgoing.md"),
        extra={},
        content_text="",
    )


SOURCE = "ACT@1000000000.aaaaaa"
TARGET = "ACT@1000000000.bbbbbb"


def _store_with_one_connection(conn_type: str) -> _MemStore:
    store = _MemStore()
    conn_id = f"{SOURCE}---{TARGET}@@{conn_type}"
    store.connections[conn_id] = _connection(conn_id, SOURCE, TARGET, conn_type)
    return store


def test_canonical_id_does_not_false_match_a_different_connection_type() -> None:
    store = _store_with_one_connection("archimate-serving")
    missing_id = f"{SOURCE}---{TARGET}@@archimate-association"

    resolved = store.canonical_id(missing_id)

    assert resolved == missing_id
    assert resolved not in store.connections


def test_canonical_id_exact_match_still_resolves(tmp_path: Path) -> None:
    store = _store_with_one_connection("archimate-serving")
    existing_id = f"{SOURCE}---{TARGET}@@archimate-serving"

    assert store.canonical_id(existing_id) == existing_id
    assert existing_id in store.connections


def test_canonical_id_resolves_connection_id_built_from_stale_slug_endpoints() -> None:
    store = _store_with_one_connection("archimate-serving")
    stale_source = "ACT@1000000000.aaaaaa.old-slug-for-actor-one"
    stale_target = "ACT@1000000000.bbbbbb.old-slug-for-actor-two"
    queried_id = f"{stale_source}---{stale_target}@@archimate-serving"

    resolved = store.canonical_id(queried_id)

    assert resolved == f"{SOURCE}---{TARGET}@@archimate-serving"
    assert resolved in store.connections
