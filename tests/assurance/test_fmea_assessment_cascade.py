"""Factor rows belong to a failure mode and cannot outlive it.

Both halves matter, and the store enforces them rather than a caller remembering to. A row for a
node that does not exist is a rating of nothing. A row left behind after its node is deleted is
worse: invisible to every navigation surface, and surfacing only as a verifier finding about
dangling data — the exact shape of an incident this store has already had.

SQLCipher-specific, because the foreign key is what does the enforcing. The parameterized
conformance suite covers the contract every backend shares.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()


def _assess(store: Any, node_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "node_id": node_id,
        "factor": "occurrence",
        "basis_digest": "basis-a",
        "value": "possible",
        "justification": "comparable component fails about twice a year",
        "author": "analyst",
    }
    payload.update(overrides)
    return store.write_fmea_assessment(**payload)  # type: ignore[arg-type]


class TestAFactorRowRequiresItsFailureMode:
    def test_a_judgement_about_a_nonexistent_node_is_refused(self, store: Any) -> None:
        with pytest.raises(Exception, match="FOREIGN KEY"):
            _assess(store, "FMD@does-not-exist")

    def test_a_judgement_about_a_real_node_is_accepted(self, store: Any) -> None:
        node_id = str(store.create_node("failure-mode", "Store returns stale rows"))

        assert _assess(store, node_id)["revision"] == 1


class TestDeletingTheFailureModeRemovesItsJudgements:
    def test_the_rows_go_with_the_node(self, store: Any) -> None:
        node_id = str(store.create_node("failure-mode", "Store returns stale rows"))
        _assess(store, node_id)
        assert store.read_fmea_assessments([node_id])

        store.delete_node(node_id)

        assert store.read_fmea_assessments([node_id]) == {}

    def test_another_node_s_judgements_survive(self, store: Any) -> None:
        """A cascade that reached further than its own node would be worse than one that did not
        reach at all, so the boundary is asserted rather than assumed."""
        doomed = str(store.create_node("failure-mode", "Store returns stale rows"))
        kept = str(store.create_node("failure-mode", "Renderer drops a glyph"))
        _assess(store, doomed)
        _assess(store, kept, value="rare")

        store.delete_node(doomed)

        assert store.read_fmea_assessments([kept])[kept][0]["value"] == "rare"
