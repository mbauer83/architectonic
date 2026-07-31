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

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.application import assurance_analysis as uc
from src.application import assurance_mutations as mutations
from tests.support.assurance_backends import ASSURANCE_BACKENDS, BACKEND_NAMES


class _Archive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, operation: str, **_kwargs: object) -> dict[str, object]:
        self.ops.append(operation)
        return {"operation": operation}


@pytest.fixture(params=BACKEND_NAMES, ids=BACKEND_NAMES)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    yield from ASSURANCE_BACKENDS[request.param](tmp_path)


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


class TestDeletingANodeAnotherAnalysisReferences:
    """`entity_in_use`, over each store, and the silent cascade it replaces.

    The rule was specified, the error code was published — `entity_in_use` sits in the closed error
    vocabulary with a details DTO naming the referencing analyses — and nothing implemented it:
    `delete_node` checked unlock and existence, then deleted. So a node one analysis authored and
    another's argument rested on could be removed, taking the borrower's reference with it, with no
    refusal and nothing recorded. A published error code that no code path can produce is also a
    contract lie, in the opposite direction from an undocumented body.

    Over all four backends because the question "who else draws on this?" is answered by each of them
    separately — `_sqlcipher_store.py:186`, `_grouping_records.py:217` for both git stores, and
    `_pocketbase_grouping.py:131` — and a rule enforced against three of four is not enforced.
    """

    def _borrowed(self, store: Any) -> tuple[str, str, str]:
        author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        borrower = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        node = str(store.create_node("hazard", "Load path is unguarded", analysis_id=author))
        store.add_analysis_member(borrower, node)
        return author, borrower, node

    def test_a_referenced_node_is_refused(self, store: Any) -> None:
        archive = _Archive()
        _author, borrower, node = self._borrowed(store)

        result = mutations.delete_node(store, archive, node_id=node)

        assert isinstance(result, mutations.MutationEntityInUse)
        assert result.node_id == node
        assert result.referencing_analysis_ids == (borrower,)

    def test_the_refused_deletion_changes_nothing(self, store: Any) -> None:
        """A refusal that had already deleted something would be worse than the cascade: the caller
        is told to go and remove references to a node that is no longer there."""
        _author, borrower, node = self._borrowed(store)
        archive = _Archive()

        mutations.delete_node(store, archive, node_id=node)

        assert store.get_node(node) is not None
        assert store.list_analysis_members(borrower) == [node]
        assert archive.ops == [], "a refusal must not appear in the audit trail as a deletion"

    def test_the_refusal_names_every_referencing_analysis(self, store: Any) -> None:
        """The details exist so the caller can act. One id when two analyses hold references sends
        them to remove one and try again, twice."""
        _author, borrower, node = self._borrowed(store)
        third = str(store.create_analysis("Third", "GRC", tlp="TLP:WHITE"))
        store.add_analysis_member(third, node)

        result = mutations.delete_node(store, _Archive(), node_id=node)

        assert isinstance(result, mutations.MutationEntityInUse)
        assert sorted(result.referencing_analysis_ids) == sorted([borrower, third])

    def test_a_node_nobody_borrows_is_deletable(self, store: Any) -> None:
        """The rule is about references, not about deletion. Refusing an unreferenced node would make
        authored work undeletable and leave the store append-only by accident."""
        author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        node = str(store.create_node("hazard", "Nobody cites this", analysis_id=author))
        archive = _Archive()

        result = mutations.delete_node(store, archive, node_id=node)

        assert isinstance(result, mutations.MutationOk)
        assert store.get_node(node) is None
        assert "DELETE" in archive.ops

    def test_removing_the_reference_makes_it_deletable(self, store: Any) -> None:
        """"Until references are explicitly removed" — so the refusal has to be a state the caller can
        leave, not a permanent one."""
        _author, borrower, node = self._borrowed(store)
        store.remove_analysis_member(borrower, node)

        result = mutations.delete_node(store, _Archive(), node_id=node)

        assert isinstance(result, mutations.MutationOk)
        assert store.get_node(node) is None

    def test_the_authors_own_provenance_is_not_a_reference(self, store: Any) -> None:
        """Authorship and participation are different relations. Counting the author's provenance as a
        reference would make every node undeletable, which reads as the rule working."""
        author = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        node = str(store.create_node("hazard", "Authored only", analysis_id=author))

        result = mutations.delete_node(store, _Archive(), node_id=node)

        assert isinstance(result, mutations.MutationOk)
