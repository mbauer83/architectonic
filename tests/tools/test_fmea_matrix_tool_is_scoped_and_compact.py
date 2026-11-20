"""`assurance_fmea_matrix` answers for one FMEA analysis, in a size an agent can read.

Two things were wrong at once. The tool took an optional ``analysis_id`` and, without one, placed
every failure mode in the store into one grid — the unscoped matrix the analysis-aggregate decision
removed from the REST surface and the GUI. And its answer could not be read: each recorded cell
carries the drafted occurrence rationale, one line per fact the architecture graph holds about the
element, which for a well-connected component is over a thousand lines repeated on every one of its
cells.

Driven through ``server.call_tool`` because the argument schema is part of what is under test: a
required argument that the served ``inputSchema`` still calls optional would pass a direct call.

The store is this test's own, so its counts are the test's to assert.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError  # type: ignore[import-not-found]

from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.domain.assurance.failure_modes import FAILURE_GUIDEWORDS
from src.domain.assurance.fmea_structural_signals import TypedEdge
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read

TOOL = "assurance_fmea_matrix"
PUMP = "APP@1000000001.pumpaa"
VALVE = "APP@1000000002.valvea"
#: What one summary row may cost on the wire. Five cells of six short fields is about 1 KB; the bound
#: leaves room for a long element name and fails long before a rationale draft could hide in it.
SUMMARY_BYTES_PER_ROW = 2_000
#: Enough dependents that the drafted rationale of one cell alone exceeds the whole summary budget.
DEPENDENT_COUNT = 400


def _well_connected_basis() -> ArchitectureBasis:
    """An architecture graph in which the pump is many dependents' only provider.

    The drafted rationale names each of them, so every recorded pump cell carries the whole list.
    """
    edges = tuple(
        TypedEdge(
            connection_id=f"CON@{index}",
            source_id=f"APP@20000{index:05d}.depend",
            target_id=PUMP,
            connection_type="archimate-serving",
            role="dependency",
            strength=4,
        )
        for index in range(DEPENDENT_COUNT)
    )
    entities = {
        PUMP: {"name": "Coolant Pump", "artifact_type": "application-component"},
        VALVE: {"name": "Relief Valve", "artifact_type": "application-component"},
    }
    return ArchitectureBasis(edges=edges, entities=entities, assembled=True)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Two FMEA analyses over the same two elements, and an STPA analysis that has no matrix."""
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.mcp.assurance_mcp import fmea_read_tools
    from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext
    from tests.support.assurance_store_template import provision_store

    db_path = tmp_path / "matrix.db"
    provision_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()

    stpa = opened.create_analysis("Cooling loop hazards", "STPA")
    first = opened.create_analysis("Cooling loop failure modes", "FMEA")
    second = opened.create_analysis("Second look at the pump", "FMEA")
    for element in (PUMP, VALVE):
        controller = opened.create_node(
            "control-structure-node", f"Controller of {element}", analysis_id=stpa
        )
        opened.register_arch_ref(controller, element, "binds-to")
    for guideword in ("no-function", "partial-function", "intermittent-function"):
        failure = opened.create_node(
            "failure-mode", f"Pump: {guideword}", analysis_id=first, failure_type=guideword
        )
        opened.register_arch_ref(failure, PUMP, "binds-to")
    other = opened.create_node(
        "failure-mode", "Valve: no-function", analysis_id=second, failure_type="no-function"
    )
    opened.register_arch_ref(other, VALVE, "binds-to")

    monkeypatch.setattr(AssuranceContext, "_bundle", lambda _self: SimpleNamespace(store=opened))
    monkeypatch.setattr(fmea_read_tools, "current_architecture_basis", _well_connected_basis)
    yield SimpleNamespace(store=opened, stpa=stpa, first=first, second=second)
    opened.lock()


def _call(**arguments: object) -> dict[str, Any]:
    return asyncio.run(mcp_assurance_read.call_tool(TOOL, arguments)).structured_content


def _recorded(answer: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(row["element_id"]), str(cell["guideword"]))
        for row in answer["rows"]
        for cell in row["cells"]
        if cell["state"] == "recorded"
    }


class TestTheMatrixIsOfOneAnalysis:
    def test_the_analysis_is_required(self, store: Any) -> None:
        """No analysis, no matrix: there is no store-wide reading of a priority ranking."""
        with pytest.raises(ToolError):
            _call()

    def test_only_that_analysis_failure_modes_are_placed(self, store: Any) -> None:
        assert _recorded(_call(analysis_id=store.first)) == {
            (PUMP, "no-function"),
            (PUMP, "partial-function"),
            (PUMP, "intermittent-function"),
        }
        assert _recorded(_call(analysis_id=store.second)) == {(VALVE, "no-function")}

    def test_an_unknown_analysis_is_not_found_rather_than_an_empty_grid(self, store: Any) -> None:
        """An empty grid reads as an analysis with nothing in it, which this is not."""
        answer = _call(analysis_id="FMEA@9999999999.zzzz.absent")

        assert answer["error"]["code"] == "not_found"
        assert answer["error"]["path"] == "analysis_id"
        assert "rows" not in answer

    def test_an_analysis_of_another_method_is_a_typed_mismatch(self, store: Any) -> None:
        answer = _call(analysis_id=store.stpa)

        assert answer["error"]["code"] == "analysis_method_mismatch"
        assert answer["error"]["path"] == "analysis_id"
        assert "rows" not in answer


class TestTheSummaryFitsAToolResult:
    def test_summary_is_the_default(self, store: Any) -> None:
        assert _call(analysis_id=store.first)["mode"] == "summary"

    def test_it_stays_within_the_stated_size_per_row(self, store: Any) -> None:
        answer = _call(analysis_id=store.first)

        assert answer["count"] == 2
        assert len(json.dumps(answer)) <= SUMMARY_BYTES_PER_ROW * answer["count"]

    def test_it_is_the_drafted_rationale_that_the_summary_leaves_out(self, store: Any) -> None:
        """The premise of the bound: the full answer for the same analysis does not fit it."""
        full = _call(analysis_id=store.first, mode="full")

        assert len(json.dumps(full)) > SUMMARY_BYTES_PER_ROW * full["count"]

    def test_every_cell_still_says_what_is_left_to_do(self, store: Any) -> None:
        """Finding the unexamined cells is what the summary is for, so none may be dropped."""
        for row in _call(analysis_id=store.first)["rows"]:
            assert [cell["guideword"] for cell in row["cells"]] == [
                guideword.slug for guideword in FAILURE_GUIDEWORDS
            ]
            assert row["answered_cells"] + row["unanswered_cells"] == len(FAILURE_GUIDEWORDS)
            for cell in row["cells"]:
                assert set(cell) == {
                    "guideword", "state", "node_id", "action_priority",
                    "occurrence_is_requested", "next_action",
                }

    def test_a_recorded_cell_names_the_node_to_read_for_its_factors(self, store: Any) -> None:
        cells = [
            cell
            for row in _call(analysis_id=store.first)["rows"]
            for cell in row["cells"]
            if cell["state"] == "recorded"
        ]

        assert cells
        assert all(cell["node_id"] for cell in cells)


class TestTheFullMatrix:
    def test_it_carries_the_factors_and_the_digest_to_record_against(self, store: Any) -> None:
        full = _call(analysis_id=store.first, mode="full")
        recorded = [
            cell for row in full["rows"] for cell in row["cells"] if cell["state"] == "recorded"
        ]

        assert recorded
        assert all(cell["factors"]["occurrence"]["basis_digest"] for cell in recorded)
        assert all(cell["occurrence_rationale_draft"] for cell in recorded)

    def test_one_element_narrows_it_to_that_row(self, store: Any) -> None:
        full = _call(analysis_id=store.first, mode="full", element_id=VALVE)

        assert [row["element_id"] for row in full["rows"]] == [VALVE]
        assert full["count"] == 1

    def test_an_element_that_is_not_a_candidate_has_no_row(self, store: Any) -> None:
        answer = _call(analysis_id=store.first, element_id="APP@1000000009.absent")

        assert answer["rows"] == []
        assert answer["count"] == 0

    def test_an_unknown_mode_is_refused_by_the_schema(self, store: Any) -> None:
        with pytest.raises(ToolError):
            _call(analysis_id=store.first, mode="everything")
