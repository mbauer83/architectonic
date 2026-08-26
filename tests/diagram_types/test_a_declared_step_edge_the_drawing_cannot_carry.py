"""W048: declared step edges the renderer's index can hold only one of.

W045 asks whether every declared *step* is drawn. Nothing asked it of a declared *edge*, and the loss
starts earlier than any walk — before a walk exists. `_build_single_target` is a dict comprehension
keyed by `source`, so a second `step-flow`, `step-then`, `step-else`, `step-contains` or `step-in-lane`
out of one step is discarded when the index is built. `_build_notes_index` is keyed by **target**, so
two notes on one step lose one: the same accident with the opposite key.

Verified before this was written, not assumed. Two `step-flow` out of `a1` index to `{'a1': 'a3'}` —
`a1 → a2` is gone. Two notes on `a1` index to the second note alone.

**The plan's own measurement no longer reproduces, and that is recorded here rather than quietly
dropped.** It said three of 24 declared edges were drawn nowhere on one shipped diagram, all three back
edges into one step. Both shipped activity diagrams were re-measured while writing this: 31 and 13
declared edges, no index collisions, no dangling targets, and no back edges at all. The content moved
on. The defect is a property of the indexing, which is why the cases below are fixtures this test owns
— exact assertions are legitimate there — and why the diagnostic is still worth having.

A declaration-side answer with no traversal, which is what makes it complete: an edge of a
single-target type is either alone under its key or not, and there is no third case for an enumeration
to miss. Two earlier designs asked the walk and then the emission; neither could be complete, and the
second was not even observable from a contribution.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.diagram_types.activity._contributions import EDGE_COLLISION_CONTRIBUTION
from src.diagram_types.activity._step_graph import colliding_declarations
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


class _Result:
    def __init__(self) -> None:
        self.issues: list[Any] = []


def _edge(conn_type: str, source: str, target: str) -> dict[str, str]:
    return {"conn_type": conn_type, "source": source, "target": target}


def _run(connections: list[dict[str, str]]) -> list[Any]:
    result = _Result()
    EDGE_COLLISION_CONTRIBUTION.run(
        None,
        BaseDiagramVerificationContext(
            fm={"connections": connections},
            loc="ACT@1.probe.puml",
            scope="engagement",
            diagram_id="ACT@1.probe",
            allowed_connections=frozenset(),
            allowed_entities=frozenset(),
            catalogs=None,
        ),
        result,
    )
    return result.issues


class TestWhatIsReported:
    @pytest.mark.parametrize(
        "conn_type", ["step-flow", "step-then", "step-else", "step-contains", "step-in-lane"]
    )
    def test_a_second_edge_of_one_type_out_of_one_step_is_reported(self, conn_type: str) -> None:
        """Every type the renderer indexes single-target by source. Parametrised rather than tested
        once, because the list is the diagnostic's claim about the index and a type that quietly left
        it would take its edges' silence with it."""
        issues = _run([_edge(conn_type, "a1", "a2"), _edge(conn_type, "a1", "a3")])

        assert [issue.code for issue in issues] == ["W048"]

    def test_two_notes_on_one_step_are_reported(self) -> None:
        """The opposite key. `_build_notes_index` is keyed by target, so it is the *step* that
        collides, not the note — and keying this by source would have found nothing."""
        issues = _run([_edge("step-note-of", "n1", "a1"), _edge("step-note-of", "n2", "a1")])

        assert [issue.code for issue in issues] == ["W048"]

    def test_the_message_names_the_survivor_and_the_loss(self) -> None:
        """An author cannot tell from "several edges collided" whether the one the picture kept is the
        one they meant — and the survivor is the *last* declared, which is not a rule anybody guesses."""
        (issue,) = _run([_edge("step-flow", "a1", "a2"), _edge("step-flow", "a1", "a3")])

        assert "a1 → a3" in issue.message
        assert "a1 → a2 is not drawn anywhere" in issue.message

    def test_three_edges_are_one_finding_naming_both_losses(self) -> None:
        (issue,) = _run([
            _edge("step-flow", "a1", "a2"), _edge("step-flow", "a1", "a3"), _edge("step-flow", "a1", "a4"),
        ])

        assert "a1 → a4" in issue.message
        assert "a1 → a2" in issue.message and "a1 → a3" in issue.message


class TestWhatIsNotReported:
    def test_one_edge_per_key_is_silent(self) -> None:
        assert _run([_edge("step-flow", "a1", "a2"), _edge("step-flow", "a2", "a3")]) == []

    def test_two_types_out_of_one_step_do_not_collide_with_each_other(self) -> None:
        """A decision legitimately declares `step-then`, `step-else` and a merge `step-flow` from the
        same step. The key is the *pair*, not the step."""
        issues = _run([
            _edge("step-then", "d1", "a1"), _edge("step-else", "d1", "a2"), _edge("step-flow", "d1", "a3"),
        ])

        assert issues == []

    def test_a_fork_may_declare_as_many_branches_as_it_likes(self) -> None:
        """`step-fork-branch` is the one type built with `_build_multi_target`, so none is lost. Naming
        the safe type by its absence from the list is what keeps the list honest."""
        issues = _run([
            _edge("step-fork-branch", "f1", "a1"),
            _edge("step-fork-branch", "f1", "a2"),
            _edge("step-fork-branch", "f1", "a3"),
        ])

        assert issues == []

    def test_an_edge_missing_an_end_is_not_a_collision(self) -> None:
        """It cannot be indexed under any key, so it is not this diagnostic's business — a declaration
        with no target is a different complaint and has its own."""
        assert _run([_edge("step-flow", "a1", ""), _edge("step-flow", "a1", "a2")]) == []

    def test_a_diagram_declaring_no_connections_is_silent(self) -> None:
        assert _run([]) == []


class TestTheAnswerIsStable:
    def test_collisions_come_back_in_a_fixed_order(self) -> None:
        """A diagram whose findings reorder between runs is one a reader cannot diff."""
        declared = [
            _edge("step-then", "d1", "x"), _edge("step-then", "d1", "y"),
            _edge("step-flow", "a1", "p"), _edge("step-flow", "a1", "q"),
        ]

        first = colliding_declarations(declared)
        second = colliding_declarations(list(reversed(declared)))

        assert [(c.conn_type, c.keyed_on) for c in first] == [("step-flow", "a1"), ("step-then", "d1")]
        assert [(c.conn_type, c.keyed_on) for c in second] == [(c.conn_type, c.keyed_on) for c in first]

    def test_the_survivor_follows_declaration_order_not_the_report_order(self) -> None:
        """Which is the whole reason `kept` exists: the index keeps the last assignment, so reversing
        the declarations changes the picture, and the diagnostic has to say so."""
        forward = colliding_declarations([_edge("step-flow", "a1", "a2"), _edge("step-flow", "a1", "a3")])
        reversed_ = colliding_declarations([_edge("step-flow", "a1", "a3"), _edge("step-flow", "a1", "a2")])

        assert forward[0].kept == ("a1", "a3")
        assert reversed_[0].kept == ("a1", "a2")
