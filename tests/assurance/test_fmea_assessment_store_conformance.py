"""One factor-assessment contract, exercised against every store backend that ships.

The reason this is parameterized rather than written once against SQLCipher: the port declares
these two methods, so a backend that does not implement them breaks the port for whoever is
configured to use it — and it breaks it at the moment they first try to record a judgement, not at
startup. A per-backend conformance run is what makes "all four implement it" a checked statement.

PocketBase is exercised through a stub transport rather than a live server: what needs proving here
is that the adapter speaks the contract (append-only revisions, batched reads, keyed by basis), and
a running PocketBase would test the server instead. The stub lives in `_pocketbase_stub`, shared
with the filing/participation conformance run — two fakes of one server drift apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance.ports import ConfidentialAssuranceStore
from tests.assurance._pocketbase_stub import StubPocketBaseClient


def _private_git_store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore

    store = PrivateGitAssuranceStore(tmp_path / "assurance-repo")
    store.unlock()
    return store


def _encrypted_private_git_store(tmp_path: Path) -> Any:
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance import _credential_store as creds
    from src.infrastructure.assurance._encrypted_private_git_store import (
        EncryptedPrivateGitAssuranceStore,
    )

    creds.set_credential("private-git-encryption-key", Fernet.generate_key().decode())
    store = EncryptedPrivateGitAssuranceStore(tmp_path / ".arch-assurance-git")
    store.unlock()
    return store


def _sqlcipher_store(tmp_path: Path) -> Any:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    return store


def _pocketbase_store(_tmp_path: Path) -> Any:
    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore

    store = PocketBaseAssuranceStore("http://localhost:8090", "admin@example.com", "password")
    store._client = StubPocketBaseClient()  # noqa: SLF001 — stands in for the authenticated client
    return store


_BACKENDS = {
    "sqlcipher": _sqlcipher_store,
    "private-git": _private_git_store,
    "encrypted-private-git": _encrypted_private_git_store,
    "pocketbase": _pocketbase_store,
}


@pytest.fixture(params=sorted(_BACKENDS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    built = _BACKENDS[request.param](tmp_path)
    # Real nodes, because the SQLCipher backend enforces the reference by foreign key: a factor row
    # may only exist for a failure mode that exists. The other backends have no such constraint, so
    # a test writing against a phantom node would pass there and hide the difference.
    _NODE_IDS.clear()
    for name in ("FMD-one", "FMD-two"):
        _NODE_IDS[name] = str(built.create_node("failure-mode", name))
    yield built
    if hasattr(built, "lock"):
        built.lock()


#: Real node ids for this backend, keyed by the placeholder the tests use.
_NODE_IDS: dict[str, str] = {}


def _write(store: Any, node: str = "FMD-one", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "node_id": _NODE_IDS[node],
        "factor": "occurrence",
        "basis_digest": "basis-a",
        "value": "possible",
        "justification": "no field data; comparable component fails twice a year",
        "author": "analyst",
    }
    payload.update(overrides)
    return store.write_fmea_assessment(**payload)  # type: ignore[arg-type]


class TestEveryBackendSatisfiesThePort:
    def test_the_backend_declares_both_methods(self, store: Any) -> None:
        assert isinstance(store, ConfidentialAssuranceStore)
        assert callable(store.read_fmea_assessments)
        assert callable(store.write_fmea_assessment)

    def test_a_written_judgement_reads_back(self, store: Any) -> None:
        _write(store)

        found = store.read_fmea_assessments([_NODE_IDS["FMD-one"]])

        rows = found[_NODE_IDS["FMD-one"]]
        assert [row["value"] for row in rows] == ["possible"]
        assert str(rows[0]["justification"]).startswith("no field data")
        assert rows[0]["author"] == "analyst"

    def test_reads_are_batched_across_nodes(self, store: Any) -> None:
        """One call, several nodes — the shape a matrix needs, keyed by node id."""
        _write(store, node="FMD-one")
        _write(store, node="FMD-two", value="rare")

        found = store.read_fmea_assessments([_NODE_IDS["FMD-one"], _NODE_IDS["FMD-two"]])

        assert set(found) == {_NODE_IDS["FMD-one"], _NODE_IDS["FMD-two"]}
        assert found[_NODE_IDS["FMD-two"]][0]["value"] == "rare"

    def test_asking_for_no_nodes_reads_nothing(self, store: Any) -> None:
        _write(store)

        assert store.read_fmea_assessments([]) == {}

    def test_a_node_with_no_judgement_is_simply_absent(self, store: Any) -> None:
        assert store.read_fmea_assessments([_NODE_IDS["FMD-two"]]) == {}


class TestRevisionsAreAppendOnly:
    def test_re_judging_the_same_basis_adds_a_revision(self, store: Any) -> None:
        first = _write(store, value="possible")
        second = _write(store, value="likely")

        assert (first["revision"], second["revision"]) == (1, 2)

    def test_the_superseded_revision_is_retained(self, store: Any) -> None:
        """The earlier judgement is what shows a reader that this changed, and from what."""
        _write(store, value="possible")
        _write(store, value="likely")

        revisions = store.read_fmea_assessments([_NODE_IDS["FMD-one"]])[_NODE_IDS["FMD-one"]]

        assert [row["value"] for row in revisions] == ["possible", "likely"]

    def test_a_judgement_against_a_new_basis_starts_its_own_revision_count(self, store: Any) -> None:
        """Revisions count how often this question was answered against THIS picture of the model,
        so a changed basis is a fresh question rather than a continuation."""
        _write(store, basis_digest="basis-a", value="possible")

        against_new_basis = _write(store, basis_digest="basis-b", value="likely")

        assert against_new_basis["revision"] == 1

    def test_judgements_for_different_bases_coexist(self, store: Any) -> None:
        _write(store, basis_digest="basis-a", value="possible")
        _write(store, basis_digest="basis-b", value="likely")

        rows = store.read_fmea_assessments([_NODE_IDS["FMD-one"]])[_NODE_IDS["FMD-one"]]

        assert {(str(r["basis_digest"]), str(r["value"])) for r in rows} == {
            ("basis-a", "possible"), ("basis-b", "likely"),
        }

    def test_factors_are_kept_apart(self, store: Any) -> None:
        _write(store, factor="occurrence", value="possible")
        _write(store, factor="severity", value="major")

        rows = store.read_fmea_assessments([_NODE_IDS["FMD-one"]])[_NODE_IDS["FMD-one"]]

        assert {(str(r["factor"]), str(r["value"])) for r in rows} == {
            ("occurrence", "possible"), ("severity", "major"),
        }
