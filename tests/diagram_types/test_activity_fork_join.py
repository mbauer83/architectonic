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
"""

from __future__ import annotations

from pathlib import Path

from src.diagram_types.activity.renderer import ActivityPumlRenderer

_REPO = Path(__file__).resolve().parents[2] / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"


def _flow(source: str, target: str) -> dict[str, object]:
    return {"conn_type": "step-flow", "source": source, "target": target}


def _branch(fork: str, first: str) -> dict[str, object]:
    return {"conn_type": "step-fork-branch", "source": fork, "target": first}


def _render(entities: dict[str, object]) -> str:
    """The activity renderer takes its connections as their own argument, not inside the entities."""
    connections = [c for c in entities["_connections"] if isinstance(c, dict)]  # type: ignore[union-attr]
    return ActivityPumlRenderer({}).render_body(
        "fork join", [], [], "activity", _REPO,
        diagram_entities={k: v for k, v in entities.items() if k != "_connections"},
        diagram_connections=connections,
    )


def _step_count(body: str, label: str) -> int:
    """How many times the body draws a step with this label.

    Counted over emitted step lines rather than raw text: a label is wrapped in the selection
    sentinel (`:[[arch://id label]];`), so a bare substring search would also match a note or a
    link elsewhere in the body.
    """
    return sum(1 for line in body.splitlines() if line.startswith(":") and label in line)


def _one_fork() -> dict[str, object]:
    """start -> fork -> (a | b | c) -> join -> tail1 -> tail2."""
    return {
        "action": [
            {"id": "start", "label": "start"},
            {"id": "a", "label": "branch a"}, {"id": "b", "label": "branch b"},
            {"id": "c", "label": "branch c"},
            {"id": "tail1", "label": "after join"}, {"id": "tail2", "label": "and then"},
        ],
        "fork": [{"id": "fk"}, {"id": "jn"}],
        "_connections": [
            _flow("start", "fk"),
            _branch("fk", "a"), _branch("fk", "b"), _branch("fk", "c"),
            _flow("a", "jn"), _flow("b", "jn"), _flow("c", "jn"),
            _flow("jn", "tail1"), _flow("tail1", "tail2"),
        ],
    }


def _nested_forks() -> dict[str, object]:
    """The shape that multiplied: an outer fork of two, one branch holding a fork of three."""
    return {
        "action": [
            {"id": "start", "label": "start"},
            {"id": "m1", "label": "meta one"}, {"id": "m2", "label": "meta two"},
            {"id": "x", "label": "inner x"}, {"id": "y", "label": "inner y"},
            {"id": "z", "label": "inner z"},
            {"id": "tail1", "label": "after join"}, {"id": "tail2", "label": "and then"},
        ],
        "fork": [{"id": "outer"}, {"id": "outer_join"}, {"id": "inner"}, {"id": "inner_join"}],
        "_connections": [
            _flow("start", "outer"),
            _branch("outer", "m1"), _branch("outer", "inner"),
            _flow("m1", "outer_join"),
            _branch("inner", "x"), _branch("inner", "y"), _branch("inner", "z"),
            _flow("x", "inner_join"), _flow("y", "inner_join"), _flow("z", "inner_join"),
            _flow("inner_join", "m2"), _flow("m2", "outer_join"),
            _flow("outer_join", "tail1"), _flow("tail1", "tail2"),
        ],
    }


class TestTheContinuationIsDrawnOnce:
    def test_one_fork_does_not_repeat_the_tail_per_branch(self) -> None:
        body = _render(_one_fork())

        assert _step_count(body, "after join") == 1, body
        assert _step_count(body, "and then") == 1, body

    def test_every_branch_is_still_drawn(self) -> None:
        """The stop must end a branch, not swallow it."""
        body = _render(_one_fork())

        for label in ("branch a", "branch b", "branch c"):
            assert _step_count(body, label) == 1, body

    def test_the_fork_is_opened_and_closed_around_its_branches(self) -> None:
        body = _render(_one_fork())
        lines = [line.strip() for line in body.splitlines()]

        assert lines.count("fork") == 1
        assert lines.count("fork again") == 2  # three branches
        assert lines.count("end fork") == 1

    def test_nested_forks_do_not_multiply_the_tail(self) -> None:
        """Two forks used to give six copies of everything after the outer join."""
        body = _render(_nested_forks())

        assert _step_count(body, "after join") == 1, body
        assert _step_count(body, "and then") == 1, body
        assert _step_count(body, "meta two") == 1, body

    def test_a_nested_fork_still_nests(self) -> None:
        body = _render(_nested_forks())
        lines = [line.strip() for line in body.splitlines()]

        assert lines.count("fork") == 2
        assert lines.count("end fork") == 2
        for label in ("inner x", "inner y", "inner z", "meta one"):
            assert _step_count(body, label) == 1, body


class TestABranchThatNeverReachesTheJoin:
    def test_it_is_drawn_and_the_others_still_close_on_the_join(self) -> None:
        """A branch may end on its own — the fork still closes, and the continuation is drawn once."""
        entities = _one_fork()
        connections = [
            c for c in entities["_connections"]  # type: ignore[index]
            if not (c["conn_type"] == "step-flow" and c["source"] == "c")
        ]
        entities["_connections"] = [*connections, ]

        body = _render(entities)

        assert _step_count(body, "branch c") == 1, body
        assert _step_count(body, "after join") == 1, body
        assert [line.strip() for line in body.splitlines()].count("end fork") == 1
