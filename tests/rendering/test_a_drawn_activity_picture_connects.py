"""Every activity shape this project can draw produces a picture whose arrows connect.

**The gate nobody had.** Three times in one release an activity shape was declared drawable, emitted,
rendered, and *looked at* — and shipped with the flow broken. Each time the body was valid, the layout
raised no warning, and the picture held the right boxes. What it did not hold was connections: an arrow
stopping in mid-air, an arm merging into another arm, and a return edge routed straight through the box
it returned to. A glance confirms shapes; it does not follow arrowheads.

So this asserts over the rendered geometry, through `src.infrastructure.rendering.drawn_connections`.
It is stated over the whole catalogue of shapes the notation permits, not over the shapes that broke,
because the same class of defect arrived three times from three different shapes.

**Scoped to activity, and not because the reader is.** `drawn_connections` is generic. Activity is
where the layout engine's routing has actually been wrong, and where every picture is drawn from
straight segments — which is what the reader can reason about. Extending it to another type means
first establishing what "crossing" legitimately means there.

Skipped without plantuml.jar, like every other rendered-SVG assertion here.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.infrastructure.rendering.drawn_connections import drawn_picture
from tests.diagram_types._activity_shapes import CATALOGUE, ActivityShape, bundled_shapes


def _plantuml_available() -> bool:
    try:
        from src.application.verification.artifact_verifier_syntax import find_plantuml_jar
        return find_plantuml_jar() is not None
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _plantuml_available(),
    reason="plantuml.jar not found — skipping rendered-picture assertions",
)

#: Below this, a picture is too small to have exercised routing at all, and a pass would say nothing.
#: The plainest shape in the catalogue draws a start, two steps and a stop.
_ENOUGH_ARROWHEADS = 3


def _render_svg(shape: ActivityShape) -> str:
    from src.infrastructure.rendering.puml_runtime import render_puml_svg

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
        svg, warnings = render_puml_svg(shape.render(), root, "activity")
        assert svg is not None, f"{shape.name}: render produced nothing — {warnings}"
        return svg


def _shapes() -> list[ActivityShape]:
    return [*CATALOGUE, *bundled_shapes()]


@pytest.mark.parametrize("shape", _shapes(), ids=lambda s: s.name.replace(" ", "-"))
def test_a_drawn_activity_shape_connects(shape: ActivityShape) -> None:
    """No arrow reaching nothing, no arrow reaching another arrow, no line over a shape."""
    picture = drawn_picture(_render_svg(shape))
    assert not picture.defects, "\n".join(
        [f"{shape.name} ({shape.exercises}) draws {len(picture.defects)} disconnected place(s):"]
        + [f"  {d.disconnection.value} at ({d.at[0]:.0f},{d.at[1]:.0f}): {d.detail}"
           for d in picture.defects]
    )


@pytest.mark.parametrize("shape", _shapes(), ids=lambda s: s.name.replace(" ", "-"))
def test_a_drawn_activity_shape_was_actually_examined(shape: ActivityShape) -> None:
    """A picture the reader cannot see into passes the check above vacuously. Nothing has silently
    stopped being examined: every shape draws arrowheads, and they were counted."""
    picture = drawn_picture(_render_svg(shape))
    assert picture.arrowheads_examined >= _ENOUGH_ARROWHEADS, (
        f"{shape.name}: only {picture.arrowheads_examined} arrowhead(s) examined, so a clean result "
        f"says nothing about whether its flow connects"
    )
    assert picture.shapes_found > 0, f"{shape.name}: no shapes found in the rendered picture"


#: Bodies using the constructs this project deliberately refuses to emit, kept as a *positive control*
#: on the instrument. Each renders without a warning and lays out; each draws a broken flow. If the
#: emitter ever learns to produce one of these shapes, the gate above fires instead of shipping it.
#:
#: These are the measured cases: the first routes a multi-step return path through the boxes it
#: returns to, and the second merges a `break` arm into another arm's line.
_KNOWN_BROKEN_BODIES = {
    "a multi-step return path": "\n".join([
        "@startuml broken_return",
        "|You|", "start", "repeat :Attempt;", "  |Architectonic|",
        "  if (succeeded?) then (yes)", "    :Record the baseline;", "    break",
        "  else (no)", "  endif", "  |You|", "  :Log the reason;", "  :Back off;",
        "repeat while (retry?) is (yes) not (no)", ":Give up;", "stop", "@enduml",
    ]),
    "a loop body split across lanes": "\n".join([
        "@startuml broken_lanes",
        "|Architectonic|", "start", ":Receive the request;", "|You|", "repeat :Attempt;",
        "  |Architectonic|", "  if (transient?) then (yes)", "    :Log the reason;",
        "  else (no)", "    :Record the outcome;", "  endif", "  |You|",
        "repeat while (retry?) is (yes) not (no)", ":Give up;", "stop", "@enduml",
    ]),
}


@pytest.mark.parametrize("description", sorted(_KNOWN_BROKEN_BODIES))
def test_the_gate_sees_a_broken_flow_the_renderer_still_lays_out(description: str) -> None:
    """The instrument has teeth on real renderer output, not only on hand-authored geometry.

    Both bodies are valid PUML, render without a warning, and draw the right boxes. That is exactly
    the situation in which reading the body and looking at the picture both passed.
    """
    from src.infrastructure.rendering.puml_runtime import render_puml_svg

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
        svg, warnings = render_puml_svg(_KNOWN_BROKEN_BODIES[description], root, "activity")
    assert svg is not None, f"{description}: expected a rendered picture, got {warnings}"
    picture = drawn_picture(svg)
    assert picture.defects, (
        f"{description}: the reader found nothing wrong in a picture measured to be broken — "
        f"the gate has gone blind ({picture.arrowheads_examined} arrowheads examined)"
    )
