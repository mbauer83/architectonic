"""Every activity body this repository can produce, recorded, so a change to the walk is visible.

The emission walk changed behaviour deliberately in several ways at once — branches stop where they
converge, a join is carried back to the fork that opened it, a convergence no branch can hold is
reached by `goto`, a looping graph and a second chain are drawn at all. Four assertions over the
shape catalogue say those things are *true*; this file says what the bodies *are*, which is the only
cheap way to see that nothing else moved with them. It is also the proof that extracting the walk
into its own module changed nothing.

Regenerate deliberately, never to make a red test green:

    uv run python -m tests.diagram_types.test_activity_golden_bodies

Then read the diff. A line moving between an `if`/`else` region is the whole class of defect here.
"""

from __future__ import annotations

from pathlib import Path

from tests.diagram_types._activity_shapes import CATALOGUE, bundled_shapes

_GOLDEN = Path(__file__).with_name("activity_golden_bodies.txt")


def render_all() -> str:
    sections = []
    for shape in (*CATALOGUE, *bundled_shapes()):
        sections.append(f"### {shape.name}\n# {shape.exercises}\n{shape.render()}")
    return "\n\n".join(sections) + "\n"


def test_the_recorded_bodies_are_what_the_walk_emits() -> None:
    assert _GOLDEN.exists(), f"missing golden file — regenerate with `python -m {__spec__.name}`"
    assert render_all() == _GOLDEN.read_text(encoding="utf-8"), (
        "the emitted activity bodies differ from the recorded ones. Read the diff: if the change is "
        "intended, regenerate with `uv run python -m tests.diagram_types.test_activity_golden_bodies`."
    )


if __name__ == "__main__":
    _GOLDEN.write_text(render_all(), encoding="utf-8")
    print(f"wrote {_GOLDEN}")
