"""Authorship and participation are two different facts about one node.

The HTTP contract test covers the exposure consequences over a real store. What is left to pin
down here is the shaping itself: which fields a summary repeats, and what happens to the odd
membership rows a wizard can plausibly write — the author listed among the borrowers, or the same
analysis listed twice.
"""

from __future__ import annotations

from src.application.assurance.provenance import analysis_summary, provenance

_STPA = {
    "analysis_id": "STPA@1.aaaa.000001",
    "name": "Key availability",
    "method": "STPA",
    "status": "draft",
    "group_id": "GRP@1.bbbb.000002",
    "tlp": "TLP:WHITE",
}
_FMEA = {
    "analysis_id": "FMEA@1.cccc.000003",
    "name": "Credential backend",
    "method": "FMEA",
    "status": "draft",
    "group_id": None,
    "tlp": "TLP:WHITE",
}
_NODE = {"node_id": "CSN@1.dddd.000004", "analysis_id": _STPA["analysis_id"]}


class TestAnalysisSummary:
    def test_a_summary_carries_enough_to_label_and_link(self) -> None:
        summary = analysis_summary(_STPA)

        assert summary["analysis_id"] == _STPA["analysis_id"]
        assert summary["name"] == "Key availability"
        assert summary["method"] == "STPA"

    def test_a_summary_is_not_the_analysis(self) -> None:
        """A node's detail needs a label and a link, not the analysis — which has its own
        endpoint, and its own exposure decision to make."""
        assert "tlp" not in analysis_summary(_STPA)


class TestProvenance:
    def test_the_author_is_named_and_the_borrower_is_separate(self) -> None:
        result = provenance(
            _NODE,
            participating_analysis_ids=[str(_FMEA["analysis_id"])],
            visible_analyses=[_STPA, _FMEA],
        )

        assert result["authored_by"]["analysis_id"] == _STPA["analysis_id"]
        assert [a["analysis_id"] for a in result["participates_in"]] == [_FMEA["analysis_id"]]

    def test_the_author_is_never_listed_among_the_borrowers(self) -> None:
        """Listing the author among them would report the node as borrowed from itself."""
        result = provenance(
            _NODE,
            participating_analysis_ids=[str(_STPA["analysis_id"]), str(_FMEA["analysis_id"])],
            visible_analyses=[_STPA, _FMEA],
        )

        assert [a["analysis_id"] for a in result["participates_in"]] == [_FMEA["analysis_id"]]

    def test_a_repeated_membership_is_reported_once(self) -> None:
        result = provenance(
            _NODE,
            participating_analysis_ids=[str(_FMEA["analysis_id"])] * 3,
            visible_analyses=[_STPA, _FMEA],
        )

        assert len(result["participates_in"]) == 1

    def test_an_unseen_analysis_is_dropped_rather_than_named(self) -> None:
        """An id alone still discloses that a classified analysis exists and touches this node."""
        result = provenance(
            _NODE,
            participating_analysis_ids=["GRC@1.eeee.000005"],
            visible_analyses=[_STPA],
        )

        assert result["participates_in"] == []

    def test_an_unseen_author_reads_as_no_author(self) -> None:
        result = provenance(
            _NODE, participating_analysis_ids=[], visible_analyses=[_FMEA]
        )

        assert result["authored_by"] is None

    def test_a_node_belonging_to_no_analysis_has_no_author(self) -> None:
        result = provenance(
            {"node_id": "HAZ@1.ffff.000006", "analysis_id": None},
            participating_analysis_ids=[],
            visible_analyses=[_STPA],
        )

        assert result["authored_by"] is None
