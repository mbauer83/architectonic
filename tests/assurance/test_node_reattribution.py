"""A node's authorship can be recorded once, and only once.

Every node is supposed to belong to an analysis. Twenty-six in the live store do not, and the reason
is a gap in the write surface rather than carelessness: `analysis_id` could be set at creation and
never afterwards, so a node authored before the analysis aggregate existed could not be attributed to
anything. The store's `update_node` compounded it — a hand-kept allowlist per backend, four copies,
each silently dropping any field absent from its own set. The write returned success and changed
nothing.

Repairing that is now its own audited use case rather than a field of the general edit. The reason is
in the other direction: a general edit that *could* re-attribute authorship lets an analysis's
recorded output be moved silently, and provenance is a historical fact. So `assign_provenance` fills
a gap and refuses to overwrite anything.

Two halves for each, as `AGENTS.md` requires:

* the delegation — the write reaches the store and the node's author changes;
* the regression — the field is not silently dropped, which is the exact failure that produced the
  orphans, and a store that accepted-and-ignored would pass every other test in this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance import mutations as mutations
from src.application.assurance.provenance_assignment import (
    ProvenanceAssigned,
    ProvenanceImmutable,
    assign_provenance,
)
from src.domain.assurance.assurance_node_types import NODE_UPDATABLE

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


class _Archive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(
        self, operation: str, *, node_id: str | None = None, payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ops.append(operation)
        return {"operation": operation}


@pytest.fixture
def store(tmp_path: Path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()
    yield opened
    opened.lock()


class TestTheStoreWritesAuthorship:
    def test_analysis_id_is_an_updatable_field(self) -> None:
        """Declared once, in the domain, and imported by every backend — it was four copies.

        Still updatable at the *store* level, because that is the mechanism `assign_provenance`
        uses. What changed is who may ask for it, not whether the column can be written.
        """
        assert "analysis_id" in NODE_UPDATABLE

    def test_node_type_stays_out_of_the_updatable_set(self) -> None:
        """The type decides the id prefix, which is already persisted: changing it would leave an
        id that lies about what it names."""
        assert "node_type" not in NODE_UPDATABLE

    def test_update_node_persists_a_new_author(self, store: Any) -> None:
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable")

        store.update_node(node_id, analysis_id=analysis)

        assert str(store.get_node(node_id)["analysis_id"]) == analysis

    def test_an_orphan_node_can_be_attributed(self, store: Any) -> None:
        """The regression. This is the live store's exact state: a node with no author, and a write
        that used to report success while discarding the field."""
        analysis = store.create_analysis("Store access", "STPA")
        node_id = store.create_node("hazard", "Store readable in plaintext")
        assert not store.get_node(node_id)["analysis_id"]

        store.update_node(node_id, analysis_id=analysis)

        assert str(store.get_node(node_id)["analysis_id"]) == analysis


class TestTheRepairUseCase:
    def test_assigning_provenance_attributes_and_audits(self, store: Any) -> None:
        archive = _Archive()
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable")

        result = assign_provenance(store, archive, node_id=node_id, analysis_id=analysis)

        assert isinstance(result, ProvenanceAssigned)
        assert result.recorded is True
        assert str(store.get_node(node_id)["analysis_id"]) == analysis
        assert "ASSIGN_PROVENANCE" in archive.ops

    def test_attributing_to_an_analysis_that_does_not_exist_is_refused(self, store: Any) -> None:
        """An `analysis_id` naming nothing is the state this repairs, not a new one to write —
        and writing one would move a node from visibly orphaned to invisibly so."""
        archive = _Archive()
        node_id = store.create_node("hazard", "Key unavailable")

        result = assign_provenance(
            store, archive, node_id=node_id, analysis_id="STPA@nothing.here.000000"
        )

        assert not isinstance(result, ProvenanceAssigned)
        assert not store.get_node(node_id)["analysis_id"]
        assert archive.ops == []

    def test_re_asserting_the_same_analysis_writes_nothing(self, store: Any) -> None:
        """Idempotent, and audibly so: the outcome is the same, and the archive does not gain a
        second entry claiming the attribution happened twice."""
        archive = _Archive()
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable", analysis_id=analysis)

        result = assign_provenance(store, archive, node_id=node_id, analysis_id=analysis)

        assert isinstance(result, ProvenanceAssigned)
        assert result.recorded is False
        assert archive.ops == []

    def test_moving_a_node_to_another_analysis_is_refused(self, store: Any) -> None:
        archive = _Archive()
        first = store.create_analysis("Key availability", "STPA")
        second = store.create_analysis("Pump failure modes", "FMEA")
        node_id = store.create_node("hazard", "Key unavailable", analysis_id=first)

        result = assign_provenance(store, archive, node_id=node_id, analysis_id=second)

        assert isinstance(result, ProvenanceImmutable)
        assert result.current_analysis_id == first
        assert str(store.get_node(node_id)["analysis_id"]) == first
        assert archive.ops == []


class TestTheGeneralEditCannotTouchAuthorship:
    def test_editing_another_field_leaves_authorship_alone(self, store: Any) -> None:
        archive = _Archive()
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable", analysis_id=analysis)

        mutations.edit_node(store, archive, node_id=node_id, name="Key unavailable at boot")

        assert str(store.get_node(node_id)["analysis_id"]) == analysis

    def test_edit_node_no_longer_accepts_an_analysis(self, store: Any) -> None:
        """The parameter is gone, not ignored. Ignored, a client that kept sending it would believe
        it had re-attributed the node — which is the failure mode the removal exists to prevent."""
        import inspect

        assert "analysis_id" not in inspect.signature(mutations.edit_node).parameters

    def test_an_unattributed_node_cannot_be_edited_at_all(self, store: Any) -> None:
        """Repair-only: until provenance is assigned, an ordinary edit is refused, so new work
        cannot accumulate against a record that cannot say who produced it."""
        archive = _Archive()
        node_id = store.create_node("hazard", "Key unavailable")

        result = mutations.edit_node(store, archive, node_id=node_id, name="Renamed")

        assert isinstance(result, mutations.MutationLegacyInvalid)
        assert store.get_node(node_id)["name"] == "Key unavailable"
        assert archive.ops == []
