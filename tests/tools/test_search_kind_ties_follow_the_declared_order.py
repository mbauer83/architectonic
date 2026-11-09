"""Kinds whose strongest hits tie are ranked in the declared kind order, whatever order they arrived in.

`search` collects hits by walking a set of kind names, and a set of strings iterates in an order that
follows string hashing — so it differs from one process to the next. `rank_balanced` ordered kinds by
their top score alone, and `sorted` keeps arrival order on a tie, so when two kinds tied the ranking
inherited the hash order: an empty query, which scores everything equally, put a document ahead of an
entity under some hash seeds and behind it under others (2 of 151 measured). It surfaced as a test that
passed alone and failed in one full run. A reader would have seen the same query rank differently after
a backend restart.
"""

from __future__ import annotations

import pytest

from src.application.artifacts._ranking import rank_balanced
from src.domain.ontology_representation.artifact_types import SearchHit
from src.domain.search_records import RECORD_TYPE_ORDER
from tests.tools.test_search_reserves_room_for_subordinate_kinds import _diagram, _entity


def _tied() -> list[SearchHit]:
    return [SearchHit(1.0, "entity", _entity(0)), SearchHit(1.0, "diagram", _diagram(0))]


@pytest.mark.parametrize("arrival", ["as declared", "reversed"])
def test_tied_kinds_are_met_in_the_declared_order(arrival: str) -> None:
    hits = _tied() if arrival == "as declared" else list(reversed(_tied()))

    kinds = [hit.record_type for hit in rank_balanced(hits, 10, None)]

    assert kinds == sorted(kinds, key=RECORD_TYPE_ORDER.index)


def test_a_higher_score_still_outranks_the_declared_order() -> None:
    """The declared order breaks ties; it does not override the scores it sits behind."""
    hits = [SearchHit(1.0, "entity", _entity(0)), SearchHit(2.0, "diagram", _diagram(0))]

    assert [hit.record_type for hit in rank_balanced(hits, 10, None)] == ["diagram", "entity"]
