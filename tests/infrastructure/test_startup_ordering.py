"""WS9 — startup ordering + fail-closed duplicate scan.

Verifies the §6 startup contract: durable-transaction recovery and group-registry
repair both run *before* the index build (so the index equals disk at first serve,
INV-2), and a genuine cross-mount stable-id collision aborts startup (INV-1/WS2).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.ports import Candidate
from src.infrastructure.artifact_index._identity_resolver import _IdentityResolver
from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._rwlock import _RWLock

# ── duplicate-scan detection (WS2 multimap) ─────────────────────────────────


def _resolver(mem: _MemStore) -> _IdentityResolver:
    return _IdentityResolver(mem, _RWLock(), lambda: None, lambda p: "engagement")


def _candidate(short: str, path: Path, scope: str = "engagement") -> Candidate:
    return Candidate(artifact_id=f"{short}.slug", path=path, scope=scope)


def test_scan_detects_same_scope_duplicate(tmp_path: Path) -> None:
    a, b = tmp_path / "APP@1.aa.x.md", tmp_path / "APP@1.aa.y.md"
    a.write_text("x")
    b.write_text("y")
    mem = _MemStore()
    mem.identity_candidates["APP@1.aa"] = [_candidate("APP@1.aa", a), _candidate("APP@1.aa", b)]

    duplicates = _resolver(mem).scan_duplicates()

    assert set(duplicates["APP@1.aa"]) == {a, b}


def test_scan_ignores_cross_scope_copies(tmp_path: Path) -> None:
    eng, ent = tmp_path / "eng.md", tmp_path / "ent.md"
    eng.write_text("x")
    ent.write_text("y")
    mem = _MemStore()
    mem.identity_candidates["APP@1.aa"] = [
        _candidate("APP@1.aa", eng, scope="engagement"),
        _candidate("APP@1.aa", ent, scope="enterprise"),
    ]

    assert _resolver(mem).scan_duplicates() == {}


def test_scan_ignores_missing_and_repeated_paths(tmp_path: Path) -> None:
    live = tmp_path / "live.md"
    live.write_text("x")
    gone = tmp_path / "gone.md"  # never created
    mem = _MemStore()
    mem.identity_candidates["APP@1.aa"] = [
        _candidate("APP@1.aa", live),
        _candidate("APP@1.aa", live),  # duplicate record, same path → not a collision
        _candidate("APP@1.aa", gone),  # path absent → ignored
    ]

    assert _resolver(mem).scan_duplicates() == {}


# ── startup ordering + fail-closed wiring ───────────────────────────────────


class _FakeGate:
    @contextmanager
    def privileged_writing(self):  # noqa: ANN201 - test stub
        yield


class _FakeIndex:
    def __init__(self, order: list[str], duplicates: dict[str, list[Path]] | None = None) -> None:
        self._order = order
        self._duplicates = duplicates or {}

    def refresh(self) -> None:
        self._order.append("index_build")

    def scan_duplicate_short_ids(self) -> dict[str, list[Path]]:
        self._order.append("duplicate_scan")
        return self._duplicates


def _patch_initialise(monkeypatch: pytest.MonkeyPatch, order: list[str], index: _FakeIndex) -> None:
    import src.infrastructure.backend.arch_backend as backend

    monkeypatch.setattr(
        "src.infrastructure.artifact_index.shared_artifact_index", lambda roots: index, raising=True
    )
    monkeypatch.setattr(
        "src.infrastructure.write.artifact_write.m4_transaction.recover_transactions",
        lambda root, rebuild_index: order.append("recover") or 0,
        raising=True,
    )
    monkeypatch.setattr(
        "src.application.group_registry_validation.validate_and_repair_group_registry",
        lambda root, valid_meta_ontologies, read_only=False: (order.append("group_repair"), [])[1],
        raising=True,
    )
    monkeypatch.setattr(
        "src.infrastructure.workspace.mutation_gate.get_workspace_gate", lambda: _FakeGate(), raising=True
    )

    class _FakeRepo:
        def __init__(self, idx: _FakeIndex, *, excluded_entity_types: frozenset[str] = frozenset()) -> None:
            self._idx = idx
            self._excluded_entity_types = excluded_entity_types

        def refresh(self) -> None:
            self._idx.refresh()

    monkeypatch.setattr("src.application.artifact_query.ArtifactRepository", _FakeRepo, raising=True)
    return backend


def test_recover_and_repair_run_before_index_build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    order: list[str] = []
    backend = _patch_initialise(monkeypatch, order, _FakeIndex(order))

    backend._initialise_repo(tmp_path, None, SimpleNamespace(admin_mode=False, read_only=False))

    assert order.index("recover") < order.index("index_build")
    assert order.index("group_repair") < order.index("index_build")
    assert order.index("index_build") < order.index("duplicate_scan")


def test_duplicate_scan_aborts_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    order: list[str] = []
    dup = {"APP@1.aa": [tmp_path / "a.md", tmp_path / "b.md"]}
    backend = _patch_initialise(monkeypatch, order, _FakeIndex(order, duplicates=dup))

    with pytest.raises(SystemExit) as exc:
        backend._initialise_repo(tmp_path, None, SimpleNamespace(admin_mode=False, read_only=False))

    assert exc.value.code == 1
