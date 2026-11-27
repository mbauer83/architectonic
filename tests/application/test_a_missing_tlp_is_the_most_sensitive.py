"""Assurance content that carries no TLP level is treated as TLP:RED wherever it is disclosed.

Regression: an unrecognised level already ranked as the most sensitive, but a record with no `tlp`
key at all was read as TLP:WHITE by the exposure policy (nodes, analyses, direct reads), as TLP:AMBER
for security records, and as TLP:WHITE by the GSN draft's publishability and the promotion preflight.
A record that lost its level therefore passed every ceiling below RED, and an analysis drawn from such
nodes was judged publishable. The level is read through `classification.content_rank`, which ranks
a missing level as it ranks an unknown one.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance.exposure import AssuranceExposurePolicy, NotFound, Visible
from src.application.assurance.gsn import build_gsn_draft
from src.application.assurance.promotion import promotion_preflight
from src.domain.assurance.classification import TLP_RED

_BELOW_RED = ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER")
_UNCLASSIFIED: dict[str, Any] = {"node_id": "N1", "node_type": "hazard", "name": "Unclassified"}


@pytest.mark.parametrize("ceiling", _BELOW_RED)
def test_an_unclassified_node_is_withheld_below_red(ceiling: str) -> None:
    policy = AssuranceExposurePolicy(ceiling, True)

    assert policy.filter_nodes([dict(_UNCLASSIFIED)]) == ([], 1)
    assert isinstance(policy.apply_node(dict(_UNCLASSIFIED)), NotFound)


@pytest.mark.parametrize("ceiling", _BELOW_RED)
def test_an_unclassified_analysis_is_withheld_below_red(ceiling: str) -> None:
    policy = AssuranceExposurePolicy(ceiling, True)
    analysis = {"analysis_id": "A1", "name": "Unclassified"}

    assert policy.filter_analyses([analysis]) == ([], 1)
    assert isinstance(policy.apply_analysis(analysis), NotFound)


@pytest.mark.parametrize("ceiling", _BELOW_RED)
def test_an_unclassified_security_record_is_withheld_below_red(ceiling: str) -> None:
    policy = AssuranceExposurePolicy(ceiling, True)

    assert policy.filter_security_records([{"finding_id": "F1"}]) == ([], 1)


def test_a_red_reader_still_sees_unclassified_content() -> None:
    policy = AssuranceExposurePolicy(TLP_RED, True)

    assert policy.filter_nodes([dict(_UNCLASSIFIED)]) == ([_UNCLASSIFIED], 0)
    assert isinstance(policy.apply_node(dict(_UNCLASSIFIED)), Visible)


class _Store:
    """The two reads the GSN draft and the promotion preflight make, over fixed records."""

    def __init__(self, nodes: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
        self._nodes = nodes
        self._analysis = analysis

    def get_analysis(self, analysis_id: str) -> dict[str, Any]:
        return self._analysis

    def list_nodes(self, **_: object) -> list[dict[str, Any]]:
        return self._nodes

    def list_edges(self, **_: object) -> list[dict[str, Any]]:
        return []


def test_a_gsn_draft_over_an_unclassified_node_is_not_publishable() -> None:
    store = _Store([dict(_UNCLASSIFIED)], {"analysis_id": "A1", "tlp": "TLP:WHITE"})

    draft = build_gsn_draft(store, analysis_id="A1", visible_nodes=store.list_nodes(), visible_edges=[])  # type: ignore[arg-type]

    assert draft is not None
    assert draft["effective_tlp"] == TLP_RED
    assert draft["publishable"] is False


def test_promoting_an_unclassified_constraint_warns() -> None:
    constraint = {"node_id": "C1", "node_type": "assurance-constraint", "name": "Unclassified"}
    store = _Store([constraint], {})

    result = promotion_preflight(store)  # type: ignore[arg-type]

    assert result["warning_count"] == 1
