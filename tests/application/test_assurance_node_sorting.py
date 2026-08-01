"""Assurance node ordering: what the non-SQL stores must reproduce, and what a bad request does.

The file- and REST-backed stores have no query engine, so the ordering they produce has to
match the SQL backend's `ORDER BY <column> <dir>, node_id ASC` — including the tie-break, or
two backends would page differently over equal timestamps.
"""

from __future__ import annotations

from src.application.assurance.node_sorting import (
    MOST_RECENTLY_UPDATED_FIRST,
    NATURAL_NODE_ORDERING,
    resolve_node_sort,
    sorted_node_dicts,
)

_NODES: list[dict[str, object]] = [
    {"node_id": "HAZ@2", "name": "beta", "node_type": "hazard",
     "created_at": "2026-01-02T00:00:00Z", "updated_at": "2026-07-01T00:00:00Z"},
    {"node_id": "LSS@1", "name": "Alpha", "node_type": "loss",
     "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-07-20T00:00:00Z"},
    {"node_id": "HAZ@3", "name": "gamma", "node_type": "hazard",
     "created_at": "2026-01-03T00:00:00Z", "updated_at": "2026-07-01T00:00:00Z"},
]


def _ids(nodes) -> list[str]:
    return [n["node_id"] for n in nodes]


class TestResolve:
    def test_unspecified_means_the_natural_creation_order(self) -> None:
        assert resolve_node_sort(None, None) == NATURAL_NODE_ORDERING

    def test_unknown_field_falls_back_rather_than_erroring(self) -> None:
        assert resolve_node_sort("severity", "desc") == NATURAL_NODE_ORDERING

    def test_a_supported_field_is_honoured_in_both_directions(self) -> None:
        assert resolve_node_sort("name", "desc") == ("name", "desc")
        assert resolve_node_sort("name", "asc") == ("name", "asc")

    def test_reader_facing_default_is_most_recently_updated_first(self) -> None:
        assert resolve_node_sort(*MOST_RECENTLY_UPDATED_FIRST) == MOST_RECENTLY_UPDATED_FIRST


class TestSortNodeDicts:
    def test_most_recently_updated_first(self) -> None:
        assert _ids(sorted_node_dicts(_NODES, "updated_at", "desc"))[0] == "LSS@1"

    def test_equal_timestamps_tie_break_on_node_id_ascending_in_both_directions(self) -> None:
        descending = _ids(sorted_node_dicts(_NODES, "updated_at", "desc"))
        assert descending == ["LSS@1", "HAZ@2", "HAZ@3"]
        ascending = _ids(sorted_node_dicts(_NODES, "updated_at", "asc"))
        assert ascending == ["HAZ@2", "HAZ@3", "LSS@1"]

    def test_name_sort_is_case_insensitive(self) -> None:
        assert _ids(sorted_node_dicts(_NODES, "name", "asc")) == ["LSS@1", "HAZ@2", "HAZ@3"]

    def test_unknown_field_yields_the_natural_creation_order(self) -> None:
        assert _ids(sorted_node_dicts(_NODES, "severity", "desc")) == ["LSS@1", "HAZ@2", "HAZ@3"]

    def test_ordering_is_a_permutation_never_a_filter(self) -> None:
        for field in ("updated_at", "created_at", "name", "node_type", "unknown"):
            for order in ("asc", "desc"):
                assert sorted(_ids(sorted_node_dicts(_NODES, field, order))) == sorted(_ids(_NODES))
