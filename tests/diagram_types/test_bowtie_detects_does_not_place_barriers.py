"""A detecting control must not change where a bowtie draws its barrier.

`detects` and the consequence-side barrier are worryingly close in wording: a bowtie's right-hand
barriers are described as "detection, recovery, containment", and `detects` says a control reveals
a failure mode. Reading the one as the other would silently move barriers across the top event —
silently, because the diagram would still render and still look plausible.

Bowtie sides are decided by `mitigates` and by `derives` provenance alone. `detects` answers a
different question about a different subject: whether *this failure mode* gets noticed, where
`mitigates` says a control limits a *loss* the hazard has already caused. These tests pin that
separation, because the renderer is where a well-meaning change would land.
"""

from __future__ import annotations

from src.diagram_types.bowtie.notation import (
    BARRIER_LEFT,
    BARRIER_RIGHT,
    MITIGATES,
    mitigating_barrier_ids,
    role_of,
)

_CONSTRAINT = {"node_id": "ACN@1", "node_type": "assurance-constraint"}


def _edge(conn_type: str, source: str = "ACN@1", target: str = "FMD@1") -> dict[str, object]:
    return {"conn_type": conn_type, "source_id": source, "target_id": target}


class TestDetectsDoesNotReachTheConsequenceSide:
    def test_a_detecting_constraint_stays_on_the_threat_side(self) -> None:
        edges = [_edge("detects")]

        role = role_of(_CONSTRAINT, mitigating_ids=mitigating_barrier_ids(edges))

        assert role == BARRIER_LEFT, "only mitigating a loss moves a barrier right of the top event"

    def test_detects_contributes_no_mitigating_barrier(self) -> None:
        assert mitigating_barrier_ids([_edge("detects")]) == frozenset()

    def test_a_mitigating_constraint_still_moves_right(self) -> None:
        """The control case: the mechanism works, so the test above is not passing vacuously."""
        edges = [_edge(MITIGATES, target="LSS@1")]

        role = role_of(_CONSTRAINT, mitigating_ids=mitigating_barrier_ids(edges))

        assert role == BARRIER_RIGHT

    def test_a_constraint_that_both_detects_and_mitigates_is_placed_by_mitigates(self) -> None:
        """Detection adds nothing to the placement decision either way."""
        edges = [_edge("detects"), _edge(MITIGATES, target="LSS@1")]

        assert role_of(_CONSTRAINT, mitigating_ids=mitigating_barrier_ids(edges)) == BARRIER_RIGHT

    def test_a_failure_mode_takes_no_bowtie_role(self) -> None:
        """Failure modes are not bowtie content: the diagram's vocabulary is threats, the top event
        and consequences. An unplaced node is a visible gap, never a silent inclusion."""
        assert role_of({"node_id": "FMD@1", "node_type": "failure-mode"}) == ""


class TestTheRendererDoesNotKnowAboutDetects:
    def test_the_bowtie_module_never_mentions_detects(self) -> None:
        """Structural, not behavioural: if the string is absent, no branch can key on it."""
        import inspect

        from src.diagram_types.bowtie import notation

        assert "detects" not in inspect.getsource(notation)
