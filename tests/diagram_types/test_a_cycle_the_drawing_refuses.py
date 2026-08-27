"""W049: a returning flow the structured forms cannot express, and the silence it used to keep.

`cycles_of` already decides this — it is what lets the renderer draw a retry loop as `repeat` — and it
returns two things: the loops it can draw, and the cycles it refuses with the reason. The renderer
reads the first and discards the second with a literal `[0]`. So a cycle one step too long for a
`backward:` chain is not drawn, nothing says so, and the picture asserts that the flow falls through:
the opposite of what the model declares, with every step still present, so W045's coverage rule sees
nothing wrong.

**The refusal was already computed. Only the reporting was missing**, which is why this contribution
adds no second opinion about what is drawable: a rule of its own here could disagree with the renderer,
and then a diagram would verify clean and draw wrong, or refuse and draw fine.

Fixtures rather than repository content, for the reason W048's tests give: no shipped activity diagram
declares a cycle at all, and the defect is a property of the notation, not of today's model.
"""

from __future__ import annotations

from typing import Any

from src.diagram_types.activity._contributions import CYCLE_REFUSAL_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


class _Result:
    def __init__(self) -> None:
        self.issues: list[Any] = []


def _step(step_id: str, kind: str = "action") -> dict[str, str]:
    return {"id": step_id, "type": kind, "label": step_id}


def _edge(conn_type: str, source: str, target: str) -> dict[str, str]:
    return {"conn_type": conn_type, "source": source, "target": target}


def _run(entities: dict[str, Any], connections: list[dict[str, str]]) -> list[Any]:
    result = _Result()
    CYCLE_REFUSAL_CONTRIBUTION.run(
        None,
        BaseDiagramVerificationContext(
            fm={"diagram-entities": entities, "connections": connections},
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


#: A retry loop: attempt, ask whether it worked, and go back through a wait if it did not.
_RETRY_ENTITIES = {
    "action": [_step("start"), _step("attempt"), _step("wait"), _step("done")],
    "decision": [_step("ok", "decision")],
}
_RETRY_EDGES = [
    _edge("step-flow", "start", "attempt"),
    _edge("step-flow", "attempt", "ok"),
    _edge("step-then", "ok", "done"),
    _edge("step-else", "ok", "wait"),
    _edge("step-flow", "wait", "attempt"),
]


class TestWhatIsReported:
    def test_a_loop_the_renderer_draws_is_not_reported(self) -> None:
        """One step on the way back is a `backward:` line, which draws. A diagnostic that fired here
        would refuse the feature this release shipped."""
        assert _run(_RETRY_ENTITIES, _RETRY_EDGES) == []

    def test_a_second_step_on_the_way_back_is_reported(self) -> None:
        """Two `backward:` lines draw only the last — measured, with a clean render and no warning."""
        entities = {**_RETRY_ENTITIES, "action": [*_RETRY_ENTITIES["action"], _step("log")]}
        edges = [
            *[e for e in _RETRY_EDGES if e != _edge("step-else", "ok", "wait")],
            _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"),
        ]

        issues = _run(entities, edges)

        assert [issue.code for issue in issues] == ["W049"]

    def test_the_reason_travels_with_the_report(self) -> None:
        """An author cannot act on "this cannot be drawn". The reason is the deliverable, and it is
        the renderer's own words rather than a second wording that could drift from it."""
        entities = {**_RETRY_ENTITIES, "action": [*_RETRY_ENTITIES["action"], _step("log")]}
        edges = [
            *[e for e in _RETRY_EDGES if e != _edge("step-else", "ok", "wait")],
            _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"),
        ]

        message = _run(entities, edges)[0].message

        assert "log" in message and "wait" in message
        assert "attempt" in message

    def test_a_diagram_with_no_cycle_reports_nothing(self) -> None:
        entities = {"action": [_step("a1"), _step("a2")]}

        assert _run(entities, [_edge("step-flow", "a1", "a2")]) == []

    def test_a_diagram_declaring_no_steps_reports_nothing(self) -> None:
        """A malformed or empty `diagram-entities` is not this rule's business."""
        assert _run({}, []) == []
        assert _run({"action": "not a list"}, []) == []


class TestItIsTheRenderersOwnDecision:
    def test_every_refusal_the_renderer_makes_is_reported(self) -> None:
        """The contribution reports exactly what `cycles_of` refuses — no rule of its own.

        Stated by asking both and comparing, because the failure this guards is silent in both
        directions: a private rule that refused less would restore the silence, and one that refused
        more would reject diagrams the renderer draws correctly.
        """
        from src.diagram_types.activity._step_cycles import cycles_of  # noqa: PLC0415
        from src.diagram_types.activity._step_graph import entry_step, graph_from_declarations  # noqa: PLC0415

        entities = {**_RETRY_ENTITIES, "action": [*_RETRY_ENTITIES["action"], _step("log")]}
        edges = [
            *[e for e in _RETRY_EDGES if e != _edge("step-else", "ok", "wait")],
            _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"),
        ]
        graph = graph_from_declarations(entities, edges)
        _loops, refused = cycles_of(graph, start=entry_step(graph))

        issues = _run(entities, edges)

        assert len(issues) == len(refused) == 1
        assert refused[0].reason in issues[0].message

    def test_it_is_a_warning_rather_than_an_error(self) -> None:
        """A repository holding one of these verifies clean today and the diagram still renders. The
        remedy is an authoring decision — shorten the way back, or express the repetition another
        way — so refusing the write would strand content authored in good faith."""
        entities = {**_RETRY_ENTITIES, "action": [*_RETRY_ENTITIES["action"], _step("log")]}
        edges = [
            *[e for e in _RETRY_EDGES if e != _edge("step-else", "ok", "wait")],
            _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"),
        ]

        assert _run(entities, edges)[0].severity == "warning"


class TestItReachesTheProductsOwnPath:
    def test_the_runner_carries_it_with_the_other_activity_contributions(self) -> None:
        """Through `run_diagram_contributions`, not by calling `.run` directly.

        A contribution that answers correctly and is never invoked reports nothing, and the two look
        identical from a unit test — a false negative of exactly that shape was nearly reported
        earlier in this release, from a verifier built without a registry, which silently runs no
        diagram contributions at all.
        """
        from pathlib import Path  # noqa: PLC0415

        from src.application.verification._verifier_contribution_runner import (  # noqa: PLC0415
            run_diagram_contributions,
        )
        from src.application.verification.artifact_verifier_types import VerificationResult  # noqa: PLC0415
        from src.diagram_types.activity import module as activity_module  # noqa: PLC0415

        entities = {**_RETRY_ENTITIES, "action": [*_RETRY_ENTITIES["action"], _step("log")]}
        edges = [
            *[e for e in _RETRY_EDGES if e != _edge("step-else", "ok", "wait")],
            _edge("step-else", "ok", "log"),
            _edge("step-flow", "log", "wait"),
        ]

        class _Registry:
            def connection_ids(self) -> list[str]:
                return []

            def entity_ids(self) -> list[str]:
                return []

        result = VerificationResult(path=Path("d.puml"), file_type="diagram")
        run_diagram_contributions(
            module=activity_module,
            candidate=object(),
            fm={"artifact-id": "ACT@1.a.d", "diagram-entities": entities, "connections": edges},
            content="---\nartifact-id: ACT@1.a.d\n---\n@startuml d\n@enduml\n",
            registry=_Registry(),
            scope="engagement",
            runtime_catalogs=None,
            result=result,
            loc="d.puml",
        )

        assert "W049" in [issue.code for issue in result.issues]

    def test_the_module_declares_the_code_it_can_emit(self) -> None:
        """A code a module emits but does not declare is one no surface can offer to filter on."""
        from src.diagram_types.activity import module as activity_module  # noqa: PLC0415

        declared = {
            code
            for contribution in activity_module.diagram_verification_contributions()
            for code in contribution.diagnostic_codes
        }

        assert "W049" in declared


class TestEveryDeclaredCycleIsSeen:
    """A cycle the model declares is either drawn as a loop or refused with a reason — never neither.

    Three shapes were neither, and all three drew a confidently wrong picture:

    * a returning flow declared as the decision's **merge** edge: the return absent and the arm that
      *was* declared rendered empty, so the picture said the flow stops there;
    * a loop whose **body holds a decision**: the loop absent entirely, the process drawn straight
      through to `stop`. This is the ordinary retry shape, and PlantUML draws it correctly — the
      renderer simply never emitted it;
    * **two decisions returning to one header**: reported as drawable, and emitted with an empty arm
      and one return silently relocated into the body.

    **One root cause for the first two.** `successors_of` excludes a decision's `step-flow` merge edge,
    correctly — counting it would offer the walk a path around both arms, which is what makes
    convergence work. But the cycle finder used the same traversal, so any cycle whose path runs through
    a decision was invisible: in the second shape the successors are literally `fix: (), skip: ()`.

    Stated as "seen at all" rather than "drawn" on purpose. Whether a shape *can* be drawn is a separate
    question with its own answer; being silently dropped is the defect.
    """

    def _seen(self, entities: dict[str, Any], connections: list[dict[str, str]]) -> tuple[int, int]:
        from src.diagram_types.activity._step_cycles import cycles_of  # noqa: PLC0415
        from src.diagram_types.activity._step_graph import (  # noqa: PLC0415
            entry_step,
            graph_from_declarations,
        )

        graph = graph_from_declarations(entities, connections)
        loops, refused = cycles_of(graph, start=entry_step(graph))
        return len(loops), len(refused)

    def test_a_return_declared_as_the_merge_edge_is_seen(self) -> None:
        entities = {
            "action": [_step("start"), _step("a1"), _step("a2"), _step("done")],
            "decision": [_step("d1", "decision")],
        }
        connections = [
            _edge("step-flow", "start", "a1"), _edge("step-flow", "a1", "d1"),
            _edge("step-then", "d1", "a2"), _edge("step-flow", "d1", "a1"),
            _edge("step-flow", "a2", "done"),
        ]

        drawn, refused = self._seen(entities, connections)

        assert drawn + refused == 1, "the cycle a1 → d1 → a1 must be seen"

    def test_a_loop_whose_body_holds_a_decision_is_seen(self) -> None:
        entities = {
            "action": [_step(i) for i in ("start", "attempt", "fix", "skip", "wait", "done")],
            "decision": [_step("inner", "decision"), _step("ok", "decision")],
        }
        connections = [
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "inner"),
            _edge("step-then", "inner", "fix"), _edge("step-else", "inner", "skip"),
            _edge("step-flow", "inner", "ok"),
            _edge("step-then", "ok", "done"), _edge("step-else", "ok", "wait"),
            _edge("step-flow", "wait", "attempt"),
        ]

        drawn, refused = self._seen(entities, connections)

        assert drawn + refused == 1, "the retry loop through `inner` must be seen"

    def test_two_decisions_returning_to_one_header_are_not_claimed_drawable(self) -> None:
        """A `repeat` has one condition and one return path. Two returns cannot both be drawn, so
        claiming the shape and emitting one of them is worse than refusing it."""
        entities = {
            "action": [_step(i) for i in ("start", "attempt", "w1", "w2", "done")],
            "decision": [_step("d1", "decision"), _step("d2", "decision")],
        }
        connections = [
            _edge("step-flow", "start", "attempt"), _edge("step-flow", "attempt", "d1"),
            _edge("step-then", "d1", "d2"), _edge("step-else", "d1", "w1"),
            _edge("step-flow", "w1", "attempt"),
            _edge("step-then", "d2", "done"), _edge("step-else", "d2", "w2"),
            _edge("step-flow", "w2", "attempt"),
        ]

        drawn, refused = self._seen(entities, connections)

        assert (drawn, refused) == (0, 1), "two returns into one header must be refused"

    def test_the_ordinary_retry_loop_is_still_drawn(self) -> None:
        """The guard on the guard: tightening what a loop may claim must not refuse the shape the
        feature exists for. Asserted as *drawn*, not merely as "nothing reported" — an assertion of
        that form is what let the holes above survive a release."""
        drawn, refused = self._seen(_RETRY_ENTITIES, _RETRY_EDGES)

        assert (drawn, refused) == (1, 0)
