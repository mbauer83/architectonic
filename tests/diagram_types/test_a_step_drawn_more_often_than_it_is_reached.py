"""W050 — a step the picture draws more often than the model gives it ways in.

The walk draws a step in each arm that reaches it where no single structured placement covers all the
arrivals, and that is deliberate: it is how a reader sees that both paths reach it, and the connector
alternative was rejected because an unlabelled circle resolves to no artifact. So repetition is not by
itself wrong.

**What is wrong is repetition beyond the arrivals.** A *partition* reached from three decision arms is
inlined three times, and inlining a block multiplies its contents: each contained step has one arrival
— the chain inside the block — and gets drawn once per arm. Measured on a three-step block reached from
three arms: 21 steps drawn for 13 declared, and every rule passed. Scale it to a five-step block
reached five times and a fourteen-step process becomes a fifty-step picture.

**The rule already existed and could not see this.** `test_activity_step_coverage` states exactly this
bound — "a step is drawn no more often than the model gives it ways in" — over a fixed catalogue of
shapes. The catalogue holds no shape that converges on a partition, so the bound was true of everything
it was asked about and blind to everything else. As a diagnostic it runs over any diagram.

A step with no arrival at all is still drawn once legitimately: it heads an orphan chain, which W045's
own contract permits. So the bound is `max(arrivals, 1)`.
"""

from __future__ import annotations

from typing import Any

from src.diagram_types.activity._contributions import OVER_DRAWN_STEP_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


class _Result:
    def __init__(self) -> None:
        self.issues: list[Any] = []


def _step(step_id: str, kind: str = "action") -> dict[str, Any]:
    step: dict[str, Any] = {"id": step_id, "type": kind, "label": step_id}
    if kind == "decision":
        step |= {"condition": f"{step_id}?", "then_label": "y", "else_label": "n"}
    return step


def _edge(conn_type: str, source: str, target: str) -> dict[str, str]:
    return {"id": f"{source}|{target}|{conn_type}", "conn_type": conn_type,
            "source": source, "target": target}


def _run(entities: dict[str, Any], connections: list[dict[str, str]], body: str) -> list[Any]:
    result = _Result()
    OVER_DRAWN_STEP_CONTRIBUTION.run(
        None,
        BaseDiagramVerificationContext(
            fm={"diagram-entities": entities, "connections": connections},
            loc="ACT@1.probe.puml",
            scope="engagement",
            diagram_id="ACT@1.probe",
            allowed_connections=frozenset(),
            allowed_entities=frozenset(),
            catalogs=None,
            body=body,
        ),
        result,
    )
    return result.issues


def _drawn(*step_ids: str) -> str:
    """A body drawing each id once per appearance, in the sentinel form the renderer emits."""
    return "@startuml d\n" + "".join(f":[[arch://{i} {i}]];\n" for i in step_ids) + "@enduml\n"


_ONE_ARRIVAL = ({"action": [_step("a1"), _step("a2")]}, [_edge("step-flow", "a1", "a2")])


class TestWhatIsReported:
    def test_a_step_drawn_more_often_than_it_is_reached_is_reported(self) -> None:
        entities, connections = _ONE_ARRIVAL

        issues = _run(entities, connections, _drawn("a1", "a2", "a2", "a2"))

        assert [issue.code for issue in issues] == ["W050"]

    def test_the_report_names_the_step_and_both_numbers(self) -> None:
        """An author cannot act on "something is drawn too often": which step, how often, and how
        often the model says it is reached."""
        entities, connections = _ONE_ARRIVAL

        message = _run(entities, connections, _drawn("a1", "a2", "a2", "a2"))[0].message

        assert "a2" in message
        assert "3" in message and "1" in message

    def test_every_over_drawn_step_gets_its_own_finding(self) -> None:
        """A block inlined N times over-draws each of its contents, and an author fixing it needs to
        see the extent rather than one example."""
        entities = {"action": [_step("p1"), _step("p2"), _step("p3")]}
        connections = [_edge("step-flow", "p1", "p2"), _edge("step-flow", "p2", "p3")]

        issues = _run(entities, connections, _drawn(*(["p1", "p2", "p3"] * 3)))

        # All three: `p1` heads the chain so the model gives it no arrival, which allows one drawing,
        # and it is drawn three times like the rest.
        assert [i.code for i in issues] == ["W050"] * 3
        assert {i.message.split("'")[1] for i in issues} == {"p1", "p2", "p3"}


class TestWhatIsNotReported:
    def test_a_step_drawn_once_per_arrival_is_not_reported(self) -> None:
        """The documented residue: two arms reach it at different depths, so it is drawn in each. That
        is how a reader sees both paths reach it, and reporting it would refuse a correct picture."""
        entities = {"action": [_step("shared")], "decision": [_step("d1", "decision"),
                                                              _step("d2", "decision")]}
        connections = [_edge("step-else", "d1", "shared"), _edge("step-else", "d2", "shared")]

        assert _run(entities, connections, _drawn("shared", "shared")) == []

    def test_a_step_drawn_once_with_no_arrival_is_not_reported(self) -> None:
        """It heads an orphan chain, which the coverage contract permits and the walk draws."""
        entities = {"action": [_step("lonely")]}

        assert _run(entities, [], _drawn("lonely")) == []

    def test_a_step_drawn_fewer_times_than_it_is_reached_is_not_reported(self) -> None:
        """Three arms converging on one structured placement is the *good* outcome — drawn once after
        the construct closes. This rule bounds repetition from above only."""
        entities = {"action": [_step("after")], "decision": [_step("d1", "decision")]}
        connections = [_edge("step-then", "d1", "after"), _edge("step-else", "d1", "after"),
                       _edge("step-flow", "d1", "after")]

        assert _run(entities, [], _drawn("after")) == []
        assert _run(entities, connections, _drawn("after")) == []

    def test_a_lane_header_repeated_per_switch_is_not_a_step(self) -> None:
        """A lane's header is emitted once per switch into it, so a diagram returning to a lane repeats
        it. Counting a lane as a step would report every multi-lane diagram."""
        entities = {"swimlane": [{"id": "L1", "label": "You"}], "action": [_step("a1")]}
        body = ("@startuml d\n|[[arch://L1 You]]|\n:[[arch://a1 a1]];\n"
                "|[[arch://L1 You]]|\n@enduml\n")

        assert _run(entities, [], body) == []

    def test_a_diagram_with_no_body_reports_nothing(self) -> None:
        """The contribution reads the *stored* body; there is nothing to count without one."""
        entities, connections = _ONE_ARRIVAL

        assert _run(entities, connections, "") == []


class TestItIsTheSameBoundTheGoldenShapesAssert:
    def test_it_is_a_warning(self) -> None:
        """A repository holding one verifies clean today and the diagram still renders — over-drawn,
        but it renders. The remedy is an authoring or layout decision, so refusing the write would
        strand content authored in good faith."""
        entities, connections = _ONE_ARRIVAL

        assert _run(entities, connections, _drawn("a1", "a2", "a2"))[0].severity == "warning"

    def test_the_shape_that_prompted_it_is_caught_end_to_end(self) -> None:
        """The real shape, rendered by the real renderer: three decision arms converging on a
        three-step partition. Each contained step has one arrival and is drawn three times."""
        from pathlib import Path  # noqa: PLC0415

        from src.diagram_types.activity.renderer import ActivityPumlRenderer  # noqa: PLC0415

        entities = {
            "swimlane": [{"id": "L1", "label": "You"}, {"id": "L2", "label": "Sys"}],
            "action": [_step(i) for i in ("start", "a1", "a2", "a3", "p1", "p2", "p3", "done")],
            "decision": [_step(d, "decision") for d in ("d1", "d2", "d3")],
            "partition": [_step("blk", "partition")],
        }
        connections = [
            _edge("step-flow", "start", "a1"),
            _edge("step-flow", "a1", "d1"), _edge("step-then", "d1", "a2"),
            _edge("step-else", "d1", "blk"),
            _edge("step-flow", "a2", "d2"), _edge("step-then", "d2", "a3"),
            _edge("step-else", "d2", "blk"),
            _edge("step-flow", "a3", "d3"), _edge("step-then", "d3", "done"),
            _edge("step-else", "d3", "blk"),
            _edge("step-contains", "blk", "p1"),
            _edge("step-flow", "p1", "p2"), _edge("step-flow", "p2", "p3"),
            *[_edge("step-in-lane", s, "L1") for s in
              ("start", "a1", "a2", "a3", "done", "blk", "p1", "p2", "p3", "d1", "d2", "d3")],
        ]
        body = ActivityPumlRenderer({}).render_body(
            "d", [], [], "activity", Path("."),
            diagram_entities=entities, diagram_connections=connections,
        )

        reported = {issue.message.split("'")[1] for issue in _run(entities, connections, body)}

        assert {"p1", "p2", "p3"} <= reported, reported
