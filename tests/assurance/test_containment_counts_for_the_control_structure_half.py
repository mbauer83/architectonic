"""An element inside an analysed controller has been reached by the analysis.

W511 reports a load-bearing element that *appears in no control structure and has no failure modes*.
It suppressed on a flat set — the elements some assurance node binds to **directly** — so a component
sitting inside an analysed controller reported as an analysis gap.

Measured on the shipped store when this was written: **7 of 24** findings named elements composed
directly by `APP@1777293133.OYEmP1`, which is bound to a control-structure node whose process model,
control algorithm and feedback are written out in full. Each finding's witness printed the
`--archimate-composition-->` edge that said so, so the finding carried the evidence against itself.

**The two halves of that sentence want different rules, which is the whole of this change.**

* *Appears in no control structure* — containment counts. An STPA control structure is deliberately
  coarser than the component decomposition; Leveson models it where control decisions are made. What
  was analysed is the controller's algorithm and process model, and those cover its parts. Drawing all
  24 in would not produce a control structure, it would reproduce the component diagram.
* *Has no failure modes* — containment must **not** count. A failure mode is per-component by
  definition, and the parent having them says nothing about the child. Expanding here would silence
  exactly what FMEA is for.

So W511 suppresses on *directly analysed* ∪ *inside an analysed controller*, and **W510 is untouched**:
it reports an element the control structure *names*, which a part of a named controller is not. Without
that separation this change would have moved seven info findings into seven warnings, which is worse
than the finding it set out to fix.
"""

from __future__ import annotations

from src.application.verification.assurance_two_way_coverage import load_bearing_but_unanalysed
from src.domain.assurance.fmea_structural_signals import TypedEdge, elements_within

CONTAINMENT = frozenset({"archimate-composition", "archimate-aggregation"})


def _dependency(source: str, target: str) -> TypedEdge:
    return TypedEdge(
        connection_id=f"{source}---{target}", source_id=source, target_id=target,
        connection_type="archimate-serving", role="dependency", strength=4,
    )


def _contains(parent: str, child: str) -> TypedEdge:
    return TypedEdge(
        connection_id=f"{parent}---{child}", source_id=parent, target_id=child,
        connection_type="archimate-composition", role="structural", strength=4,
    )


def _load_bearing(target: str) -> list[TypedEdge]:
    """Four typed dependents, which is the threshold the finding requires."""
    return [_dependency(f"APP@1.dep{n}", target) for n in range(4)]


def _subjects(findings) -> list[str]:
    return [f.subject_id for f in findings]


class TestAPartOfAnAnalysedController:
    def test_it_is_not_reported_as_unanalysed(self) -> None:
        edges = [*_load_bearing("APP@1.part"), _contains("APP@1.controller", "APP@1.part")]
        inside = elements_within(
            frozenset({"APP@1.controller"}), edges, containment_types=CONTAINMENT
        )

        findings = load_bearing_but_unanalysed(
            edges=edges,
            analysed_element_ids=frozenset({"APP@1.controller"}),
            within_analysed_control_structure=inside,
        )

        assert _subjects(findings) == []

    def test_it_is_reported_when_the_container_is_not_analysed(self) -> None:
        """Containment only carries the analysis down from something that was analysed."""
        edges = [*_load_bearing("APP@1.part"), _contains("APP@1.controller", "APP@1.part")]
        inside = elements_within(frozenset(), edges, containment_types=CONTAINMENT)

        findings = load_bearing_but_unanalysed(
            edges=edges, analysed_element_ids=frozenset(), within_analysed_control_structure=inside,
        )

        assert _subjects(findings) == ["APP@1.part"]

    def test_it_reaches_a_part_of_a_part(self) -> None:
        """Composition is transitive: a component two levels inside an analysed controller is still
        inside it."""
        edges = [
            *_load_bearing("APP@1.inner"),
            _contains("APP@1.controller", "APP@1.middle"),
            _contains("APP@1.middle", "APP@1.inner"),
        ]
        inside = elements_within(
            frozenset({"APP@1.controller"}), edges, containment_types=CONTAINMENT
        )

        assert "APP@1.inner" in inside


class TestWhatContainmentDoesNotCarry:
    def test_a_dependency_is_not_containment(self) -> None:
        """Serving something analysed does not put you inside it."""
        edges = [*_load_bearing("APP@1.served"), _dependency("APP@1.controller", "APP@1.served")]

        inside = elements_within(
            frozenset({"APP@1.controller"}), edges, containment_types=CONTAINMENT
        )

        assert inside == frozenset({"APP@1.controller"}), "only the root itself, nothing new"

    def test_containment_upward_does_not_carry(self) -> None:
        """A controller that is *part of* something analysed is not thereby analysed itself — the
        walk goes down from the container, never up from the part."""
        edges = [*_load_bearing("APP@1.whole"), _contains("APP@1.whole", "APP@1.controller")]

        inside = elements_within(
            frozenset({"APP@1.controller"}), edges, containment_types=CONTAINMENT
        )

        assert "APP@1.whole" not in inside

    def test_no_containment_types_expands_nothing(self) -> None:
        """A caller that cannot say which relations mean containment gets no expansion, rather than
        a guess — the same restraint the empty analysable set takes."""
        edges = [_contains("APP@1.controller", "APP@1.part")]

        assert elements_within(
            frozenset({"APP@1.controller"}), edges, containment_types=frozenset()
        ) == frozenset()

    def test_a_containment_cycle_terminates(self) -> None:
        edges = [_contains("APP@1.a", "APP@1.b"), _contains("APP@1.b", "APP@1.a")]

        assert elements_within(
            frozenset({"APP@1.a"}), edges, containment_types=CONTAINMENT
        ) == frozenset({"APP@1.b", "APP@1.a"})


class TestTheFailureModeHalfIsUnchanged:
    def test_an_element_inside_an_analysed_one_still_owes_its_own_failure_modes(self) -> None:
        """The suppression is about W511's *combined* sentence. Being inside an analysed controller
        answers "appears in no control structure"; it never answers "has no failure modes", and W510
        — which asks only that — reads direct bindings and is not given this set at all."""
        import inspect

        from src.application.verification import _assurance_rules_failure_modes as failures
        source = inspect.getsource(failures.check_analysed_element_has_failure_modes)

        assert "within" not in source and "contain" not in source, (
            "W510 must keep asking about the element the control structure names directly"
        )
