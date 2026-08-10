"""The three aggregate reads answer about one analysis when asked, and about the store when not.

``assurance_stats``, ``assurance_coverage`` and ``assurance_risk_register`` each assembled their own
exposure-filtered node/edge view and none of them offered the ``analysis_id`` the store has taken all
along — so a store holding several analyses answered a risk register, a coverage gap list and a set of
counts belonging to none of them. The scoping now comes from one place,
``AssuranceContext.exposed_graph``, and these tests hold it there.

Driven through ``server.call_tool`` rather than by calling the closures, because the tools *are*
closures over the registration and the call path is what a client gets: argument validation from the
served ``inputSchema`` included. A test that reached past it could pass while the parameter was
unreachable over the wire.

Exact counts are asserted deliberately: the store here is built by the test, so the content is the
test's own and a count is not a claim about the real repository.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read

ALPHA = "ANL@1000000001.aaaaaa.alpha"
BETA = "ANL@1000000002.bbbbbb.beta"


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """An unlocked store holding one risk per analysis, plus an untreated risk in ALPHA."""
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store
    from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

    db_path = tmp_path / "aggregates.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()

    # ALPHA: a treated risk and an untreated one, so a coverage gap exists inside the scope.
    treated = opened.create_node("risk", "Alpha treated risk", analysis_id=ALPHA)
    opened.create_node("risk", "Alpha untreated risk", analysis_id=ALPHA)
    constraint = opened.create_node("assurance-constraint", "Alpha constraint", analysis_id=ALPHA)
    opened.add_edge(treated, constraint, "treated-by")

    # BETA: one risk, and an edge of its own, so a scoped read that leaked would be visible.
    beta_risk = opened.create_node("risk", "Beta risk", analysis_id=BETA)
    beta_constraint = opened.create_node("assurance-constraint", "Beta constraint", analysis_id=BETA)
    opened.add_edge(beta_risk, beta_constraint, "treated-by")

    monkeypatch.setattr(
        AssuranceContext, "_bundle", lambda _self: SimpleNamespace(store=opened)
    )
    yield opened
    opened.lock()


def _call(tool: str, **arguments: object) -> dict[str, Any]:
    _unstructured, structured = asyncio.run(mcp_assurance_read.call_tool(tool, arguments))
    return structured


def _risk_names(answer: dict[str, Any]) -> set[str]:
    return {str(row["name"]) for row in answer["risks"]}


class TestRiskRegister:
    def test_the_whole_store_is_the_default(self, store: Any) -> None:
        assert _risk_names(_call("assurance_risk_register")) == {
            "Alpha treated risk",
            "Alpha untreated risk",
            "Beta risk",
        }

    def test_one_analysis_excludes_the_other(self, store: Any) -> None:
        assert _risk_names(_call("assurance_risk_register", analysis_id=ALPHA)) == {
            "Alpha treated risk",
            "Alpha untreated risk",
        }
        assert _risk_names(_call("assurance_risk_register", analysis_id=BETA)) == {"Beta risk"}

    def test_an_edge_leaving_the_scope_is_dropped_with_its_node(self, store: Any) -> None:
        """Scoping is by node; the edge filter follows, so no edge points out of the analysis."""
        scoped = _call("assurance_risk_register", analysis_id=BETA)
        treatments = [row for r in scoped["risks"] for row in r.get("treated_by", [])]
        assert treatments, "the Beta risk is treated — a scoped read must keep its own edge"
        assert all("Alpha" not in str(t) for t in treatments)


def _gap_names(answer: dict[str, Any], gap: str) -> set[str]:
    return {str(row["name"]) for row in answer["gaps"][gap]}


class TestCoverage:
    def test_every_analysis_gap_is_reported_when_nothing_is_scoped(self, store: Any) -> None:
        assert _gap_names(_call("assurance_coverage"), "constraints_without_evidence") == {
            "Alpha constraint",
            "Beta constraint",
        }

    def test_a_gap_is_reported_only_in_the_analysis_that_holds_it(self, store: Any) -> None:
        alpha = _call("assurance_coverage", analysis_id=ALPHA)
        beta = _call("assurance_coverage", analysis_id=BETA)

        assert _gap_names(alpha, "constraints_without_evidence") == {"Alpha constraint"}
        assert _gap_names(beta, "constraints_without_evidence") == {"Beta constraint"}


class TestStats:
    def test_counts_narrow_to_the_analysis(self, store: Any) -> None:
        whole = _call("assurance_stats")
        alpha = _call("assurance_stats", analysis_id=ALPHA)
        beta = _call("assurance_stats", analysis_id=BETA)

        assert whole["node_count"] == 5
        assert alpha["node_count"] == 3
        assert beta["node_count"] == 2
        # The parts account for the whole: nothing is double-counted and nothing is lost.
        assert alpha["node_count"] + beta["node_count"] == whole["node_count"]

    def test_edges_narrow_with_their_endpoints(self, store: Any) -> None:
        whole = _call("assurance_stats")
        alpha = _call("assurance_stats", analysis_id=ALPHA)
        assert whole["edge_count"] == 2
        assert alpha["edge_count"] == 1


def test_an_unknown_analysis_answers_empty_rather_than_the_whole_store(store: Any) -> None:
    """The failure that matters: a filter that silently does nothing is worse than one that errors."""
    answer = _call("assurance_stats", analysis_id="ANL@9999999999.zzzzzz.absent")
    assert answer["node_count"] == 0
    assert _risk_names(_call("assurance_risk_register", analysis_id="ANL@9999999999.zzzzzz.absent")) == set()
