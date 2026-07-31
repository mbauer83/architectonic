"""Analysis deletion, over every assurance backend, and the orphan-membership regression.

Two obligations, and both have to hold in all four stores rather than in whichever one the
application happened to be tested against:

* **the delegation** — ``delete_analysis`` removes the analysis *and* the participation rows naming
  it, and leaves the participating nodes and their provenance alone;
* **the regression** — an analysis that only *borrowed* nodes used to leave one orphan membership
  per borrowed node. Participation has no foreign key to analyses in any backend, so nothing
  collected them, and a later read of "which analyses does this node participate in?" named an
  analysis that no longer existed.

Parameterised over the backends rather than written four times: four copies drift, and the copy that
drifts is the one nobody reads. Each backend supplies a store; every assertion below is the same.

The application-level refusal is here too, because the two rules are one decision: an analysis that
*authored* nodes is not deletable at all, and an analysis that *borrowed* them is — with the
borrowing ended and the nodes untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from src.application import assurance_analysis as uc
from tests.assurance._pocketbase_stub import StubPocketBaseClient


class _Archive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, operation: str, **_kwargs: object) -> dict[str, object]:
        self.ops.append(operation)
        return {"operation": operation}


def _sqlcipher_store(tmp_path: Path) -> Iterator[Any]:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "conformance.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield store
    store.lock()


def _private_git_store(tmp_path: Path) -> Iterator[Any]:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore

    store = PrivateGitAssuranceStore(tmp_path / "assurance-repo")
    store.unlock()
    yield store
    store.lock()


def _encrypted_private_git_store(tmp_path: Path) -> Iterator[Any]:
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance import _credential_store as creds
    from src.infrastructure.assurance._encrypted_private_git_store import (
        EncryptedPrivateGitAssuranceStore,
    )

    creds.set_credential("private-git-encryption-key", Fernet.generate_key().decode())
    store = EncryptedPrivateGitAssuranceStore(tmp_path / ".arch-assurance-git")
    store.unlock()
    yield store
    store.lock()


def _pocketbase_store(_tmp_path: Path) -> Iterator[Any]:
    """PocketBase against the shared stub transport rather than a live server.

    What needs proving is that the adapter sweeps participation when an analysis goes — a running
    PocketBase would test the server instead. The stub is the same one the other conformance runs
    use: two fakes of one server drift apart.
    """
    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore

    store = PocketBaseAssuranceStore("http://localhost:8090", "admin@example.com", "password")
    store._client = StubPocketBaseClient()  # noqa: SLF001 — stands in for the authenticated client
    yield store


#: Backend name → a factory yielding an unlocked store. All four, because the port declares
#: ``delete_analysis`` and a backend that sweeps nothing breaks it for whoever is configured to use
#: that backend — at the moment they delete an analysis, not at startup.
_BACKENDS: dict[str, Callable[[Path], Iterator[Any]]] = {
    "sqlcipher": _sqlcipher_store,
    "private-git": _private_git_store,
    "encrypted-private-git": _encrypted_private_git_store,
    "pocketbase": _pocketbase_store,
}


@pytest.fixture(params=sorted(_BACKENDS), ids=sorted(_BACKENDS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    yield from _BACKENDS[request.param](tmp_path)


class TestDeletingAnAnalysisEndsParticipationOnly:
    """The rule, over each store that implements it."""

    def _borrowed(self, store: Any) -> tuple[str, str, str]:
        """An author analysis with a node, and a second analysis that borrows it."""
        author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        borrower = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        node = str(store.create_node("hazard", "Readable outside the gate", analysis_id=author))
        store.add_analysis_member(borrower, node)
        return author, borrower, node

    def test_the_participation_rows_go_with_the_analysis(self, store: Any) -> None:
        """The regression. These rows have no foreign key to the analysis in any backend, so
        nothing collected them and a later read named an analysis that no longer existed."""
        _author, borrower, node = self._borrowed(store)
        assert store.list_analysis_members(borrower) == [node]

        store.delete_analysis(borrower)

        assert store.list_analysis_members(borrower) == []
        assert borrower not in store.list_participating_analyses(node)

    def test_the_borrowed_node_survives_with_its_provenance(self, store: Any) -> None:
        author, borrower, node = self._borrowed(store)

        store.delete_analysis(borrower)

        surviving = store.get_node(node)
        assert surviving is not None, "a borrowed node is not the borrower's to destroy"
        assert str(surviving["analysis_id"]) == author

    def test_the_authoring_analysis_is_untouched(self, store: Any) -> None:
        author, borrower, _node = self._borrowed(store)

        store.delete_analysis(borrower)

        assert store.get_analysis(author) is not None
        assert store.get_analysis(borrower) is None

    def test_other_analyses_keep_their_participation(self, store: Any) -> None:
        """The sweep is scoped to the deleted analysis, not to the node."""
        author, borrower, node = self._borrowed(store)
        third = str(store.create_analysis("Third", "GRC", tlp="TLP:WHITE"))
        store.add_analysis_member(third, node)

        store.delete_analysis(borrower)

        assert store.list_analysis_members(third) == [node]
        assert sorted(store.list_participating_analyses(node)) == [third]
        assert str(store.get_node(node)["analysis_id"]) == author


class TestTheUseCaseRefusesToDeleteAuthoredWork:
    def test_an_analysis_that_authored_nodes_is_refused(self, store: Any) -> None:
        archive = _Archive()
        analysis = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        store.create_node("hazard", "Readable outside the gate", analysis_id=analysis)

        result = uc.delete_analysis(store, archive, analysis_id=analysis)

        assert isinstance(result, uc.AnalysisInvalid)
        assert result.error == "analysis_not_empty"
        assert store.get_analysis(analysis) is not None
        assert archive.ops == []

    def test_the_refusal_names_a_remedy_the_surface_would_accept(self, store: Any) -> None:
        """The old message told callers to "detach or delete" the nodes first. Detaching is not a
        thing this surface permits — provenance is immutable — so half that advice sent them to look
        for an operation that refuses. The message now says why, and names the two real options."""
        archive = _Archive()
        analysis = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        store.create_node("hazard", "Readable outside the gate", analysis_id=analysis)

        result = uc.delete_analysis(store, archive, analysis_id=analysis)

        assert isinstance(result, uc.AnalysisInvalid)
        message = result.message.lower()
        assert "immutable" in message, "the refusal has to say why reassignment is not on offer"
        assert "delete them" in message, "one remedy: delete the authored nodes explicitly"
        assert "leave the analysis" in message, "the other: leave it in place"
        assert "detach" not in message, "detaching is not an operation this surface has"

    def test_an_analysis_that_only_borrowed_is_deletable(self, store: Any) -> None:
        archive = _Archive()
        author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        borrower = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        node = str(store.create_node("hazard", "Readable", analysis_id=author))
        store.add_analysis_member(borrower, node)

        result = uc.delete_analysis(store, archive, analysis_id=borrower)

        assert isinstance(result, uc.AnalysisOk)
        assert store.get_analysis(borrower) is None
        assert store.get_node(node) is not None
        assert store.list_analysis_members(borrower) == []
        assert "DELETE_ANALYSIS" in archive.ops
