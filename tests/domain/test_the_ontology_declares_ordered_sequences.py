"""The ontology declares which types are ordered sequences, and which relations compose and order them.

B58 needed two facts the ontology did not state: "this element type denotes an ordered sequence", and
"these relations express order". The first is a new flag on the entity type; the second was nearly
there — `derivation_role: dynamic` — and was to be checked before relying on it. It is checked here:
the dynamic set is exactly triggering and flow, the two relations ArchiMate defines as dynamic.
"""

from __future__ import annotations

import pytest

from src.domain.relationships.ordered_sequences import Relation, SequenceGraph, SequenceVocabulary, unordered_parts


@pytest.fixture(scope="module")
def vocabulary() -> SequenceVocabulary:
    from src.application.verification._ordered_sequence_rule import sequence_vocabulary
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    return sequence_vocabulary(build_runtime_catalogs(build_module_registry()))


def test_a_process_denotes_an_ordered_sequence_and_a_function_does_not(vocabulary: SequenceVocabulary) -> None:
    assert "process" in vocabulary.sequence_types
    assert "function" not in vocabulary.sequence_types
    assert "event" not in vocabulary.sequence_types


def test_a_value_stream_denotes_an_ordered_sequence(vocabulary: SequenceVocabulary) -> None:
    """Its stages run in order: the specification defines it as a sequence of activities (owner 2026-11-27)."""
    assert "value-stream" in vocabulary.sequence_types


def test_the_relations_that_express_order_are_exactly_triggering_and_flow(vocabulary: SequenceVocabulary) -> None:
    """The check B58 asked for before relying on `derivation_role: dynamic`."""
    assert vocabulary.ordering == {"archimate-triggering", "archimate-flow"}


def test_the_junctions_carry_order_on_and_nothing_else_does(vocabulary: SequenceVocabulary) -> None:
    """Read from the RJ3 pass-through rule whose legs are both dynamic, by the junction class."""
    assert {"and-junction", "or-junction"} <= vocabulary.order_carriers
    assert "process" not in vocabulary.order_carriers
    assert "grouping" not in vocabulary.order_carriers, "PDR12 is potential and structural, not a carrier"


def test_composition_composes_and_aggregation_does_not(vocabulary: SequenceVocabulary) -> None:
    assert "archimate-composition" in vocabulary.composing
    assert "archimate-aggregation" not in vocabulary.composing


# ── the core, over relations the test owns ───────────────────────────────────

_VOCAB = SequenceVocabulary(
    sequence_types=frozenset({"seq"}), composing=frozenset({"part-of"}), ordering=frozenset({"then"}),
    order_carriers=frozenset({"hub"}),
)


def _graph(*relations: tuple[str, str, str]) -> SequenceGraph:
    table = [Relation(t, s, d) for s, t, d in relations]
    return SequenceGraph(
        outgoing=lambda source: [r for r in table if r.source == source],
        type_of=lambda node: "hub" if node.startswith("j") else "step",
    )


def test_two_parts_and_no_order_names_both() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"))
    assert unordered_parts("w", outgoing, _VOCAB) == ("a", "b")


def test_one_order_between_the_parts_is_enough() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"), ("w", "part-of", "c"), ("b", "then", "c"))
    assert unordered_parts("w", outgoing, _VOCAB) == ()


def test_one_part_is_never_a_finding() -> None:
    assert unordered_parts("w", _graph(("w", "part-of", "a")), _VOCAB) == ()


def test_order_to_something_outside_the_parts_does_not_order_them() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"), ("a", "then", "elsewhere"), ("a", "then", "a"))
    assert unordered_parts("w", outgoing, _VOCAB) == ("a", "b")


def test_a_relation_that_does_not_compose_is_not_a_part() -> None:
    outgoing = _graph(("w", "groups", "a"), ("w", "groups", "b"))
    assert unordered_parts("w", outgoing, _VOCAB) == ()


def test_order_through_a_carrier_orders_the_parts() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"), ("a", "then", "j1"), ("j1", "then", "b"))
    assert unordered_parts("w", outgoing, _VOCAB) == ()


def test_order_through_chained_carriers_orders_the_parts() -> None:
    outgoing = _graph(
        ("w", "part-of", "a"), ("w", "part-of", "b"),
        ("a", "then", "j1"), ("j1", "then", "j2"), ("j2", "then", "b"),
    )
    assert unordered_parts("w", outgoing, _VOCAB) == ()


def test_order_through_something_that_is_not_a_carrier_does_not_order_them() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"), ("a", "then", "x"), ("x", "then", "b"))
    assert unordered_parts("w", outgoing, _VOCAB) == ("a", "b")


def test_a_cycle_of_carriers_terminates() -> None:
    outgoing = _graph(("w", "part-of", "a"), ("w", "part-of", "b"), ("a", "then", "j1"), ("j1", "then", "j2"),
                      ("j2", "then", "j1"))
    assert unordered_parts("w", outgoing, _VOCAB) == ("a", "b")
