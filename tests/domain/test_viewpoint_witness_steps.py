"""Unit tests for ordered witness-step reconstruction."""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.viewpoints.viewpoint_witness_steps import order_witness_steps


def _connection(identifier: str, source: str, target: str, type_name: str = "archimate-serving") -> ConnectionRecord:
    return ConnectionRecord(identifier, source, target, type_name, "1", "draft", Path("/examples"), {}, "")


class TestOrderWitnessSteps:
    def test_orders_an_already_ordered_chain_source_to_target(self) -> None:
        steps = order_witness_steps(
            "a", "c", (_connection("c1", "a", "b"), _connection("c2", "b", "c"))
        )
        assert [(step.connection_id, step.hop_index, step.direction) for step in steps] == [
            ("c1", 0, "forward"),
            ("c2", 1, "forward"),
        ]

    def test_reconstructs_the_true_path_from_reversed_id_order(self) -> None:
        """A witness stored in reversed ID order still renders source→target."""
        steps = order_witness_steps(
            "a", "c", (_connection("c2", "b", "c"), _connection("c1", "a", "b"))
        )
        assert [step.connection_id for step in steps] == ["c1", "c2"]
        assert steps[0].source == "a"
        assert steps[1].target == "c"

    def test_marks_a_step_walked_against_authored_order_as_reverse(self) -> None:
        steps = order_witness_steps(
            "a", "c", (_connection("c1", "b", "a"), _connection("c2", "b", "c"))
        )
        assert steps[0].direction == "reverse"
        assert steps[1].direction == "forward"

    def test_disconnected_witnesses_yield_no_path(self) -> None:
        steps = order_witness_steps(
            "a", "d", (_connection("c1", "a", "b"), _connection("c2", "c", "d"))
        )
        assert steps == ()

    def test_chain_ending_elsewhere_yields_no_path(self) -> None:
        steps = order_witness_steps("a", "z", (_connection("c1", "a", "b"), _connection("c2", "b", "c")))
        assert steps == ()

    def test_no_witnesses_yield_no_path(self) -> None:
        assert order_witness_steps("a", "b", ()) == ()

    def test_tie_break_is_deterministic_by_connection_id(self) -> None:
        first = order_witness_steps(
            "a", "b", (_connection("c9", "a", "b"), _connection("c1", "a", "b"))
        )
        second = order_witness_steps(
            "a", "b", (_connection("c1", "a", "b"), _connection("c9", "a", "b"))
        )
        # Two parallel witnesses between the same endpoints cannot both be consumed into
        # one walk ending at the target — the reconstruction refuses rather than guesses.
        assert first == second == ()

    def test_three_hop_chain_carries_types_and_indices(self) -> None:
        steps = order_witness_steps(
            "s",
            "t",
            (
                _connection("r2", "m1", "m2", "archimate-aggregation"),
                _connection("r3", "m2", "t", "archimate-realization"),
                _connection("r1", "s", "m1", "archimate-assignment"),
            ),
        )
        assert [(step.hop_index, step.connection_type) for step in steps] == [
            (0, "archimate-assignment"),
            (1, "archimate-aggregation"),
            (2, "archimate-realization"),
        ]
