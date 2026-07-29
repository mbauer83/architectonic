"""A dismissed cell, written and read back through a real store.

The matrix's third cell state exists so that "someone looked and found nothing" cannot be confused
with "nobody looked". Both halves of that promise are wiring, not logic, and both were broken while
the unit tests passed:

* The store returns a node's declared attributes inside `attributes_json`, not as columns. Read
  flatly, `assessment_state` was always absent, so every dismissal came back as a recorded failure
  mode with no dismissal detail — the state was unreachable through the only path that writes it.
  The unit test passed because it hand-built a node with the attribute at the top level.
* Both coverage rules ran on a dismissal, which has no hazard and no detecting control *because
  that is what dismissing means*. Answering a cell honestly therefore cost two permanent warnings,
  making the cheap answer the expensive one — the exact incentive the third state exists to remove.

So these go through `create_node` / `update_node` / `list_nodes` rather than dict literals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance_fmea_rows import matrix_rows
from src.application.verification.assurance_verifier import verify_store
from src.domain.assurance.failure_modes import NOT_CREDIBLE, RECORDED

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

ELEMENT = "APP@1777293133.OYEmP1"


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    controller = str(built.create_node("control-structure-node", "Controller"))
    built.register_arch_ref(controller, ELEMENT, "binds-to")
    yield built
    built.lock()


def _dismiss(store: Any, guideword: str, *, by: str, reason: str) -> str:
    node_id = str(store.create_node(
        "failure-mode", f"Dismissed: {guideword}", failure_type=guideword,
    ))
    store.update_node(node_id, attributes={
        "assessment_state": NOT_CREDIBLE,
        "dismissed_by": by,
        "dismissal_rationale": reason,
    })
    store.register_arch_ref(node_id, ELEMENT, "binds-to")
    return node_id


def _cell(store: Any, guideword: str) -> dict[str, object]:
    rows = matrix_rows(
        nodes=store.list_nodes(),
        edges=store.list_edges(),
        arch_refs=store.list_arch_refs(),
        assessments={},
    )
    row = next(r for r in rows if r["element_id"] == ELEMENT)
    cells = row["cells"]
    assert isinstance(cells, list)
    return next(c for c in cells if c["guideword"] == guideword)


class TestADismissalReadsBackAsADismissal:
    def test_the_cell_reports_the_dismissed_state(self, store: Any) -> None:
        _dismiss(store, "excessive-function", by="analyst", reason="throughput is caller-bounded")

        assert _cell(store, "excessive-function")["state"] == NOT_CREDIBLE

    def test_who_dismissed_it_and_why_survive_the_round_trip(self, store: Any) -> None:
        """Without these the cell is a bare assertion, and a judgement nobody is accountable for."""
        _dismiss(store, "excessive-function", by="analyst", reason="throughput is caller-bounded")

        assert _cell(store, "excessive-function")["dismissal"] == {
            "by": "analyst",
            "reason": "throughput is caller-bounded",
        }

    def test_a_failure_mode_with_no_state_is_still_recorded(self, store: Any) -> None:
        """The default must not shift: a node written without the attribute is a real finding."""
        node_id = str(store.create_node(
            "failure-mode", "Backend stops serving reads", failure_type="no-function",
        ))
        store.register_arch_ref(node_id, ELEMENT, "binds-to")

        assert _cell(store, "no-function")["state"] == RECORDED


class TestDismissingCostsNothingMore:
    def test_a_dismissal_raises_no_coverage_finding(self, store: Any) -> None:
        _dismiss(store, "excessive-function", by="analyst", reason="throughput is caller-bounded")

        codes = [issue.code for issue in verify_store(store).issues]

        assert "W506" not in codes
        assert "W507" not in codes

    def test_a_recorded_failure_mode_still_raises_both(self, store: Any) -> None:
        """The skip must be the dismissal's, not everyone's — these are the findings that make an
        underivable priority visible."""
        node_id = str(store.create_node(
            "failure-mode", "Backend stops serving reads", failure_type="no-function",
        ))
        store.register_arch_ref(node_id, ELEMENT, "binds-to")

        codes = [issue.code for issue in verify_store(store).issues]

        assert "W506" in codes
        assert "W507" in codes

    def test_dismissing_every_guideword_clears_the_element(self, store: Any) -> None:
        """The whole point: an element answered entirely by dismissal is answered, and the store
        stops asking about it."""
        for guideword in (
            "no-function", "partial-function", "excessive-function",
            "intermittent-function", "unintended-function",
        ):
            _dismiss(store, guideword, by="analyst", reason="outside this analysis's losses")

        codes = [issue.code for issue in verify_store(store).issues]

        assert codes == []
