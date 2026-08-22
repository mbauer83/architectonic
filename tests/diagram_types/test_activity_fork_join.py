"""A fork's branches end at the join, and what follows the join is drawn once.

The model spells a fork and a join the same way — both are entries in `diagram_entities.fork[]` —
and what tells them apart is that a fork has outgoing `step-fork-branch` connections while a join
has only incoming `step-flow`. A join therefore opened no branches, emitted nothing, and the walk
carried straight on: every branch ran to the end of the graph, so the whole continuation appeared
once per branch. Two nested forks produced six copies of the tail.

**Stated over the shapes the notation permits**, not over a fixture: one fork, a fork nested inside
a branch, and a branch that never reaches the join. A single-fork fixture with a short tail hides
the multiplication that makes this unusable — the reported case was a 9691 x 3387 px image.

`artifact_verify` reported `valid: true` throughout, and it was right to: the model is well-formed.
Only the picture was wrong, which is why the assertion has to be about the emitted body.

The shapes themselves live in `_activity_shapes`, which every activity test shares.
"""

from __future__ import annotations

from tests.diagram_types._activity_shapes import (
    A_BRANCH_THAT_NEVER_REACHES_THE_JOIN,
    NESTED_FORKS,
    ONE_FORK,
    step_count,
)


class TestTheContinuationIsDrawnOnce:
    def test_one_fork_does_not_repeat_the_tail_per_branch(self) -> None:
        body = ONE_FORK.render()

        assert step_count(body, "after join") == 1, body
        assert step_count(body, "and then") == 1, body

    def test_every_branch_is_still_drawn(self) -> None:
        """The stop must end a branch, not swallow it."""
        body = ONE_FORK.render()

        for label in ("branch a", "branch b", "branch c"):
            assert step_count(body, label) == 1, body

    def test_the_fork_is_opened_and_closed_around_its_branches(self) -> None:
        body = ONE_FORK.render()
        lines = [line.strip() for line in body.splitlines()]

        assert lines.count("fork") == 1
        assert lines.count("fork again") == 2  # three branches
        assert lines.count("end fork") == 1

    def test_nested_forks_do_not_multiply_the_tail(self) -> None:
        """Two forks used to give six copies of everything after the outer join."""
        body = NESTED_FORKS.render()

        assert step_count(body, "after join") == 1, body
        assert step_count(body, "and then") == 1, body
        assert step_count(body, "meta two") == 1, body

    def test_a_nested_fork_still_nests(self) -> None:
        body = NESTED_FORKS.render()
        lines = [line.strip() for line in body.splitlines()]

        assert lines.count("fork") == 2
        assert lines.count("end fork") == 2
        for label in ("inner x", "inner y", "inner z", "meta one"):
            assert step_count(body, label) == 1, body


class TestABranchThatNeverReachesTheJoin:
    def test_it_is_drawn_and_the_others_still_close_on_the_join(self) -> None:
        """A branch may end on its own — the fork still closes, and the continuation is drawn once."""
        body = A_BRANCH_THAT_NEVER_REACHES_THE_JOIN.render()

        assert step_count(body, "branch c") == 1, body
        assert step_count(body, "after join") == 1, body
        assert [line.strip() for line in body.splitlines()].count("end fork") == 1
