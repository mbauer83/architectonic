"""The assurance read tools no test named by name, each asked something real about a real store.

Twenty of eighty-nine MCP tools were reachable only through loop-over-every-tool gates — the ones that
check every tool declares its hints, serves an object input schema, and registers. Those gates prove a
tool *exists*; none of them proves it answers correctly, so a read could return the wrong register, or
the same register regardless of its filters, and pass the whole suite.

Driven through ``server.call_tool``, which is the path a client takes: the argument validation the
served ``inputSchema`` describes runs, so a filter that is unreachable over the wire fails here rather
than being asserted past.

Counts are exact on purpose. The store is built by this module, so its content is the test's own and a
count is a statement about the tool rather than about the repository — the rule against exact counts
guards reads of the *real* model, which these are not.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read

STPA = "stpa"


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A small but structurally real STPA store: a loss, a hazard that leads to it, and a UCA."""
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store
    from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

    db_path = tmp_path / "reads.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()

    analysis_id = opened.create_analysis("Braking safety", STPA)
    opened.create_analysis("Filed review", "cast", status="filed")

    loss = opened.create_node("loss", "Occupant injury", analysis_id=analysis_id)
    hazard = opened.create_node("hazard", "Insufficient deceleration", analysis_id=analysis_id)
    orphan = opened.create_node("hazard", "Unlinked hazard", analysis_id=analysis_id)
    opened.add_edge(hazard, loss, "leads-to")

    monkeypatch.setattr(AssuranceContext, "_bundle", lambda _self: SimpleNamespace(store=opened))
    yield SimpleNamespace(store=opened, analysis_id=analysis_id, loss=loss, hazard=hazard, orphan=orphan)
    opened.lock()


def _call(tool: str, **arguments: object) -> dict[str, Any]:
    _unstructured, structured = asyncio.run(mcp_assurance_read.call_tool(tool, arguments))
    return structured


class TestListAnalyses:
    def test_lists_what_the_store_holds(self, store: Any) -> None:
        answer = _call("assurance_list_analyses")
        assert answer["count"] == 2
        assert {str(a["name"]) for a in answer["analyses"]} == {"Braking safety", "Filed review"}

    def test_the_method_filter_selects_rather_than_being_ignored(self, store: Any) -> None:
        answer = _call("assurance_list_analyses", method=STPA)
        assert {str(a["name"]) for a in answer["analyses"]} == {"Braking safety"}

    def test_the_status_filter_selects_rather_than_being_ignored(self, store: Any) -> None:
        answer = _call("assurance_list_analyses", status="filed")
        assert {str(a["name"]) for a in answer["analyses"]} == {"Filed review"}

    def test_one_analysis_is_answered_as_itself_not_as_a_list(self, store: Any) -> None:
        answer = _call("assurance_list_analyses", analysis_id=store.analysis_id)
        assert "analyses" not in answer
        assert str(answer["analysis"]["name"]) == "Braking safety"

    def test_an_absent_analysis_is_refused_rather_than_answered_empty(self, store: Any) -> None:
        answer = _call("assurance_list_analyses", analysis_id="ANL@9999999999.zzzzzz.absent")
        assert "error" in answer


class TestListEdges:
    def test_lists_the_edge_the_store_holds(self, store: Any) -> None:
        answer = _call("assurance_list_edges")
        assert answer["count"] == 1
        assert str(answer["edges"][0]["conn_type"]) == "leads-to"

    def test_the_conn_type_filter_selects(self, store: Any) -> None:
        assert _call("assurance_list_edges", conn_type="leads-to")["count"] == 1
        assert _call("assurance_list_edges", conn_type="derives")["count"] == 0

    def test_the_endpoint_filters_are_not_interchangeable(self, store: Any) -> None:
        """`source_id` and `target_id` filter different ends — swapping them must not both match."""
        assert _call("assurance_list_edges", source_id=store.hazard)["count"] == 1
        assert _call("assurance_list_edges", source_id=store.loss)["count"] == 0
        assert _call("assurance_list_edges", target_id=store.loss)["count"] == 1


class TestCompletenessProfiles:
    def test_stpa_reports_the_hazard_with_no_loss_as_a_gap(self, store: Any) -> None:
        answer = _call("assurance_stpa_complete")
        assert answer["passed"] is False
        # The unlinked hazard is the gap; the linked one is not.
        blob = str(answer)
        assert store.orphan in blob
        assert "checks" in answer

    def test_stpa_scoped_to_an_analysis_still_finds_its_own_gap(self, store: Any) -> None:
        answer = _call("assurance_stpa_complete", analysis_id=store.analysis_id)
        assert answer["passed"] is False
        assert store.orphan in str(answer)

    def test_stpa_scoped_to_an_absent_analysis_has_nothing_to_fault(self, store: Any) -> None:
        answer = _call("assurance_stpa_complete", analysis_id="ANL@9999999999.zzzzzz.absent")
        assert store.orphan not in str(answer)

    def test_grc_answers_a_structured_verdict(self, store: Any) -> None:
        answer = _call("assurance_grc_complete")
        assert "passed" in answer
        assert "checks" in answer

    def test_case_completeness_answers_a_structured_verdict(self, store: Any) -> None:
        answer = _call("assurance_case_completeness")
        assert "passed" in answer
        assert "checks" in answer


class TestDraftGsn:
    def test_scaffolds_an_argument_from_the_store_content(self, store: Any) -> None:
        answer = _call("assurance_draft_gsn")
        # The losses and hazards it was given are what the scaffold argues over.
        assert "top_goal" in answer
        assert "Insufficient deceleration" in str(answer["sub_goals"])

    def test_a_scope_with_no_content_scaffolds_no_sub_goals(self, store: Any) -> None:
        answer = _call("assurance_draft_gsn", analysis_id="ANL@9999999999.zzzzzz.absent")
        assert "Insufficient deceleration" not in str(answer.get("sub_goals"))


def test_a_locked_store_refuses_every_one_of_these_reads(store: Any) -> None:
    """The gate these reads share. A read that answered from a locked store would be the whole point
    of the confidential tier failing quietly, so it is asserted for all of them at once."""
    store.store.lock()
    for tool in (
        "assurance_list_analyses",
        "assurance_list_edges",
        "assurance_stpa_complete",
        "assurance_grc_complete",
        "assurance_case_completeness",
        "assurance_draft_gsn",
    ):
        answer = _call(tool)
        assert "error" in answer, tool
        assert str(answer["error"]["code"]) == "assurance_store_locked", tool
