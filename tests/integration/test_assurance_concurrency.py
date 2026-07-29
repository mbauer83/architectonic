"""Concurrency harness for the confidential assurance store.

Why this exists (regression guard for a production-only failure):
    The assurance store is a *process singleton* unlocked once, then served by the
    backend from a pool of OS threads (FastAPI/anyio threadpool for sync REST
    handlers + FastMCP tool execution). The original SQLCipher adapter opened a
    single connection bound to the *unlock* thread, so any call landing on another
    thread raised "SQLite objects created in a thread can only be used in that same
    thread" — the intermittent 500s users saw.

    The existing assurance HTTP tests use Starlette ``TestClient``, whose single
    portal thread runs unlock + queries together, so the bug *cannot* surface
    there. These tests deliberately drive the store/bundle from a pool of worker
    threads distinct from the unlock thread — the real failure mode — and also
    assert the write path serialises.

These tests must FAIL on the pre-fix code and PASS after the concurrency fix.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def bundle(tmp_path):  # type: ignore[no-untyped-def]
    """An unlocked SQLCipher store + archive + colocated connector, built once.

    Unlocked on the *main* test thread; worker threads below access it — that is
    the cross-thread scenario under test.
    """
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    # Mirror the factory wiring: archive + signal-snapshot store share the store's
    # connection access. Post-fix this is the thread-aware accessor; pre-fix we
    # fall back to the single bound ``_conn`` so the harness reproduces the real
    # cross-thread failure on the unfixed code instead of an AttributeError.
    conn_access = getattr(store, "_thread_conn_or_none", None) or (lambda: store._conn)  # noqa: SLF001
    archive = SQLCipherAssuranceArchive(conn_access)
    snapshot_store = SQLCipherSnapshotStore(conn_access)
    yield store, archive, snapshot_store
    store.lock()


def test_read_on_thread_other_than_unlock_thread(bundle) -> None:  # type: ignore[no-untyped-def]
    """A store read on a thread != the unlock thread must succeed (no cross-thread error)."""
    store, _archive, _connector = bundle
    store.create_node("loss", "Loss on main thread", concern_class="safety")

    result: dict[str, object] = {}

    def _read() -> None:
        result["nodes"] = store.list_nodes()
        result["stats"] = store.stats()

    t = threading.Thread(target=_read)
    t.start()
    t.join()

    assert "error" not in result
    assert len(result["nodes"]) == 1  # type: ignore[arg-type]
    assert result["stats"]["node_count"] == 1  # type: ignore[index]


def test_concurrent_reads_from_threadpool(bundle) -> None:  # type: ignore[no-untyped-def]
    """Many concurrent reads across worker threads (the GUI/agent read load)."""
    store, archive, snapshot_store = bundle
    for i in range(10):
        store.create_node("loss", f"Loss {i}", concern_class="safety")

    errors: list[str] = []

    def _reads(_i: int) -> None:
        try:
            store.list_nodes()
            store.stats()
            store.list_edges()
            archive.list_entries()
            snapshot_store.list_snapshots()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_reads, i) for i in range(60)]
        for f in as_completed(futures):
            f.result()

    assert not errors, f"concurrent-read errors: {errors[:3]}"


def test_writes_serialize_through_queue_no_race(bundle) -> None:  # type: ignore[no-untyped-def]
    """Concurrent write *submissions* serialise on the queue: no audit-log seq race.

    Drives the architecture: reads run free, writes funnel through one worker. The
    audit-log append (SELECT MAX(seq)+1 → INSERT) is the canonical read-then-write
    race; serialised, it must produce a contiguous, collision-free sequence.
    """
    from src.infrastructure.concurrency.single_writer_queue import SingleWriterQueue

    store, archive, _connector = bundle
    queue = SingleWriterQueue("assurance-write-queue-test")
    errors: list[str] = []

    def _write(i: int) -> None:
        store.create_node("hazard", f"Hazard {i}", concern_class="safety")
        archive.append("TEST", payload={"i": i})

    def _submit(i: int) -> None:
        try:
            queue.run_sync(_write, i)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_submit, i) for i in range(40)]
            for f in as_completed(futures):
                f.result()
        assert queue.wait_until_idle(timeout_s=10.0)
        peak_in_flight = queue.max_observed_in_flight
    finally:
        queue.shutdown()

    assert not errors, f"write errors: {errors[:3]}"
    assert peak_in_flight == 1
    assert store.stats()["node_count"] == 40  # type: ignore[index]
    # Audit-log sequence is contiguous and collision-free (no lost/duplicated seq).
    entries = archive.list_entries(limit=1000)
    seqs = sorted(int(e["seq"]) for e in entries)
    assert seqs == list(range(1, len(seqs) + 1))


def test_wal_mode_and_busy_timeout(bundle) -> None:  # type: ignore[no-untyped-def]
    """The store opens connections in WAL mode with a non-zero busy timeout."""
    store, _archive, _connector = bundle
    conn_access = getattr(store, "_thread_conn_or_none", None) or (lambda: store._conn)  # noqa: SLF001
    conn = conn_access()
    assert conn is not None
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()
    mode = journal_mode["journal_mode"] if isinstance(journal_mode, dict) else journal_mode[0]
    assert str(mode).lower() == "wal"
    busy = conn.execute("PRAGMA busy_timeout").fetchone()
    timeout = busy["timeout"] if isinstance(busy, dict) else busy[0]
    assert int(timeout) > 0
