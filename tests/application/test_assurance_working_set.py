"""The graph one analysis reasons over is authored ∪ participating.

Not `list_nodes(analysis_id=…)`, which is authored only. Getting it wrong in either direction
breaks something specific, and each is asserted here:

* authored only — an FMEA's matrix has no components to put rows against, and the analyst's only
  remaining move is to copy the STPA's nodes, which then drift;
* everything in the store — one analysis' diagram shows another's findings, and the scoping is gone.

Also asserted: the set is exposure-filtered on the way out, edges included, so nothing downstream
has to remember to do it.
"""

from __future__ import annotations

from typing import Any

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_working_set import analysis_working_set

_STPA = "STPA@1.aaaa.000001"
_FMEA = "FMEA@1.bbbb.000002"


class _FakeStore:
    """Nodes keyed by author, memberships keyed by analysis — the two relations kept apart, as the
    real store keeps them."""

    def __init__(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        members: dict[str, list[str]],
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._members = members

    def is_unlocked(self) -> bool:
        return True

    def list_nodes(self, *, analysis_id: str | None = None, **_kw: Any) -> list[dict[str, Any]]:
        if analysis_id is None:
            return list(self._nodes)
        return [n for n in self._nodes if n.get("analysis_id") == analysis_id]

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return next((n for n in self._nodes if n["node_id"] == node_id), None)

    def list_edges(self, **_kw: Any) -> list[dict[str, Any]]:
        return list(self._edges)

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        return list(self._members.get(analysis_id, []))


def _node(node_id: str, analysis_id: str | None, tlp: str = "TLP:WHITE") -> dict[str, Any]:
    return {"node_id": node_id, "node_type": "hazard", "name": node_id, "analysis_id": analysis_id,
            "tlp": tlp}


def _edge(edge_id: str, source: str, target: str) -> dict[str, Any]:
    return {"edge_id": edge_id, "source_id": source, "target_id": target, "conn_type": "leads-to"}


def _policy(ceiling: str = "TLP:RED") -> AssuranceExposurePolicy:
    return AssuranceExposurePolicy(ceiling, True)


class TestTheWorkingSetIsAuthoredPlusBorrowed:
    def test_authored_nodes_are_included(self) -> None:
        store = _FakeStore([_node("H1", _STPA)], [], {})

        result = analysis_working_set(store, _policy(), _STPA)

        assert [n["node_id"] for n in result.nodes] == ["H1"]
        assert result.authored_node_ids == frozenset({"H1"})

    def test_borrowed_nodes_are_included_but_not_reported_as_authored(self) -> None:
        store = _FakeStore(
            [_node("H1", _STPA), _node("FMD1", _FMEA)], [], {_FMEA: ["H1"]}
        )

        result = analysis_working_set(store, _policy(), _FMEA)

        assert {n["node_id"] for n in result.nodes} == {"FMD1", "H1"}
        assert result.authored_node_ids == frozenset({"FMD1"})

    def test_another_analysis_work_is_not_included(self) -> None:
        store = _FakeStore([_node("H1", _STPA), _node("FMD1", _FMEA)], [], {})

        result = analysis_working_set(store, _policy(), _FMEA)

        assert {n["node_id"] for n in result.nodes} == {"FMD1"}

    def test_a_node_both_authored_and_recorded_as_a_member_appears_once(self) -> None:
        """Some wizard will write the redundant membership; the set must not double the node."""
        store = _FakeStore([_node("FMD1", _FMEA)], [], {_FMEA: ["FMD1"]})

        result = analysis_working_set(store, _policy(), _FMEA)

        assert [n["node_id"] for n in result.nodes] == ["FMD1"]

    def test_a_membership_naming_a_deleted_node_is_skipped(self) -> None:
        store = _FakeStore([_node("FMD1", _FMEA)], [], {_FMEA: ["GONE"]})

        result = analysis_working_set(store, _policy(), _FMEA)

        assert [n["node_id"] for n in result.nodes] == ["FMD1"]


class TestEdgesSpanTheWholeWorkingSet:
    def test_an_edge_between_an_authored_and_a_borrowed_node_survives(self) -> None:
        """This is the edge the synergy is made of: a failure mode leading to a borrowed hazard."""
        store = _FakeStore(
            [_node("H1", _STPA), _node("FMD1", _FMEA)],
            [_edge("E1", "FMD1", "H1")],
            {_FMEA: ["H1"]},
        )

        result = analysis_working_set(store, _policy(), _FMEA)

        assert [e["edge_id"] for e in result.edges] == ["E1"]

    def test_an_edge_reaching_outside_the_working_set_is_dropped(self) -> None:
        store = _FakeStore(
            [_node("H1", _STPA), _node("FMD1", _FMEA)], [_edge("E1", "FMD1", "H1")], {}
        )

        result = analysis_working_set(store, _policy(), _FMEA)

        assert result.edges == []


class TestExposureIsAppliedOnTheWayOut:
    def test_an_above_ceiling_authored_node_is_withheld(self) -> None:
        store = _FakeStore(
            [_node("H1", _FMEA), _node("SECRET", _FMEA, tlp="TLP:RED")], [], {}
        )

        result = analysis_working_set(store, _policy("TLP:GREEN"), _FMEA)

        assert [n["node_id"] for n in result.nodes] == ["H1"]
        assert result.authored_node_ids == frozenset({"H1"})

    def test_an_above_ceiling_borrowed_node_is_withheld(self) -> None:
        store = _FakeStore(
            [_node("SECRET", _STPA, tlp="TLP:RED"), _node("FMD1", _FMEA)],
            [_edge("E1", "FMD1", "SECRET")],
            {_FMEA: ["SECRET"]},
        )

        result = analysis_working_set(store, _policy("TLP:GREEN"), _FMEA)

        assert [n["node_id"] for n in result.nodes] == ["FMD1"]
        # And the edge to it goes with it: an edge with a hidden endpoint discloses that node.
        assert result.edges == []
