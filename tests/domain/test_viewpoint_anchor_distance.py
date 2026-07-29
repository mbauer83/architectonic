"""Unit tests for anchor-relative modeled distance."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.viewpoints.viewpoint_anchor_distance import anchor_modeled_distances


@dataclass(frozen=True)
class _Edge:
    source: str
    target: str
    hops: int | None = None


class TestAnchorModeledDistances:
    def test_anchor_ranks_zero(self) -> None:
        assert anchor_modeled_distances(["a"], []) == {"a": 0}

    def test_direct_modeled_edge_ranks_one(self) -> None:
        distances = anchor_modeled_distances(["a"], [_Edge("a", "x")])
        assert distances == {"a": 0, "x": 1}

    def test_derived_edge_ranks_by_witness_chain_length(self) -> None:
        distances = anchor_modeled_distances(["a"], [_Edge("x", "a", hops=2)])
        assert distances == {"a": 0, "x": 2}

    def test_minimum_wins_across_multiple_witnesses(self) -> None:
        """An entity reachable by both a 2-hop and a 4-hop witness ranks as 2."""
        distances = anchor_modeled_distances(["a"], [_Edge("a", "x", hops=4), _Edge("x", "a", hops=2)])
        assert distances["x"] == 2

    def test_direct_edge_beats_derived_witnesses(self) -> None:
        distances = anchor_modeled_distances(["a"], [_Edge("a", "x", hops=3), _Edge("a", "x")])
        assert distances["x"] == 1

    def test_entity_without_anchor_edge_is_absent_not_defaulted(self) -> None:
        """No witness means UNRANKED: the entity is absent from the map, never 0 or 1."""
        distances = anchor_modeled_distances(["a"], [_Edge("a", "x"), _Edge("x", "y")])
        assert "y" not in distances

    def test_multiple_anchors_take_the_nearest(self) -> None:
        distances = anchor_modeled_distances(["a", "b"], [_Edge("a", "x", hops=4), _Edge("b", "x", hops=2)])
        assert distances == {"a": 0, "b": 0, "x": 2}

    def test_anchor_to_anchor_edge_keeps_both_at_zero(self) -> None:
        distances = anchor_modeled_distances(["a", "b"], [_Edge("a", "b")])
        assert distances == {"a": 0, "b": 0}

    def test_unanchored_execution_yields_no_distances(self) -> None:
        assert anchor_modeled_distances([], [_Edge("a", "x")]) == {}
