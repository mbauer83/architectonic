"""A node's authorship can be corrected.

Every node is supposed to belong to an analysis. Twenty-six in the live store do not, and the reason
is a gap in the write surface rather than carelessness: `analysis_id` could be set at creation and
never afterwards, so a node authored before the analysis aggregate existed could not be attributed to
anything. The store's `update_node` compounded it — a hand-kept allowlist per backend, four copies,
each silently dropping any field absent from its own set. The write returned success and changed
nothing.

So there are two tests here for each half:

* the delegation — `edit_node(analysis_id=...)` reaches the store and the node's author changes;
* the regression — the field is not silently dropped, which is the exact failure that produced the
  orphans, and a store that accepted-and-ignored would pass every other test in this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application import assurance_mutations as mutations
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
        """Declared once, in the domain, and imported by every backend — it was four copies."""
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


class TestTheUseCaseGuardsReattribution:
    def test_edit_node_reattributes_and_audits(self, store: Any) -> None:
        archive = _Archive()
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable")

        result = mutations.edit_node(
            store, archive, node_id=node_id, analysis_id=analysis,
        )

        assert isinstance(result, mutations.MutationOk)
        assert "analysis_id" in result.payload["updated"]
        assert str(store.get_node(node_id)["analysis_id"]) == analysis
        assert "UPDATE" in archive.ops

    def test_reattributing_to_an_analysis_that_does_not_exist_is_refused(self, store: Any) -> None:
        """An `analysis_id` naming nothing is the state this field repairs, not a new one to write —
        and writing one would move a node from visibly orphaned to invisibly so."""
        archive = _Archive()
        node_id = store.create_node("hazard", "Key unavailable")

        result = mutations.edit_node(
            store, archive, node_id=node_id, analysis_id="STPA@nothing.here.000000",
        )

        assert isinstance(result, mutations.MutationRejected)
        assert result.field == "analysis_id"
        assert not store.get_node(node_id)["analysis_id"]
        assert archive.ops == []

    def test_editing_another_field_leaves_authorship_alone(self, store: Any) -> None:
        archive = _Archive()
        analysis = store.create_analysis("Key availability", "STPA")
        node_id = store.create_node("hazard", "Key unavailable", analysis_id=analysis)

        mutations.edit_node(store, archive, node_id=node_id, name="Key unavailable at boot")

        assert str(store.get_node(node_id)["analysis_id"]) == analysis
