"""An activity diagram stays readable as lanes and labels grow, and says how to author one.

Both properties were missing and both were found the same way — by authoring a diagram and looking
at what came out. A three-lane, thirteen-step activity rendered as a 4548-px landscape strip, because
a swimlane is exactly as wide as its widest unwrapped label and nothing bounded that. And the
authoring guidance described the *schema* of `diagram_entities` while saying nothing about how the
steps are wired together, so the connection shape had to be reverse-engineered from an existing file.

Neither is a formatting nicety. A diagram nobody can read fails at the only thing a diagram does, and
guidance that omits the wiring protocol makes every author rediscover it.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.diagram_types.activity import module as activity_module


def _render_minimal(labels: list[str]) -> str:
    entities = {
        "swimlane": [{"id": "l1", "label": "One"}, {"id": "l2", "label": "Two"}],
        "action": [{"id": f"a{i}", "label": text} for i, text in enumerate(labels)],
    }
    connections = [
        {"id": f"il{i}", "conn_type": "step-in-lane", "source": f"a{i}", "target": "l1"}
        for i in range(len(labels))
    ] + [
        {"id": f"f{i}", "conn_type": "step-flow", "source": f"a{i}", "target": f"a{i + 1}"}
        for i in range(len(labels) - 1)
    ]
    return activity_module.renderer.render_body(
        name="Rendered",
        entities=[],
        connections=[],
        diagram_type="activity",
        repo_root=Path("/nonexistent"),
        diagram_entities=entities,
        diagram_connections=connections,
    )


class TestLabelsDoNotWidenTheCanvasWithoutBound:
    def test_a_wrap_width_is_emitted(self) -> None:
        """Without this, one sentence-long step sets the width of its whole lane."""
        body = _render_minimal(["Short", "A considerably longer step label than the first"])

        assert re.search(r"^skinparam wrapWidth \d+$", body, flags=re.M), body[:400]

    def test_the_bound_is_configurable_and_zero_disables_it(self) -> None:
        from src.infrastructure.rendering.puml_label_wrapping import configured_label_wrap_width

        assert configured_label_wrap_width({}) == 240
        assert configured_label_wrap_width({"layout": {"wrap_width": 180}}) == 180
        assert configured_label_wrap_width({"layout": {"wrap_width": 0}}) == 0
        # Nonsense falls back rather than emitting a negative skinparam.
        assert configured_label_wrap_width({"layout": {"wrap_width": -5}}) == 240
        assert configured_label_wrap_width({"layout": {"wrap_width": "wide"}}) == 240

    def test_activity_keeps_its_own_narrower_bound(self) -> None:
        """A lane's width is paid for by every lane beside it, so activity wraps sooner."""
        assert "skinparam wrapWidth 180" in _render_minimal(["Short"])


class TestTheGuidanceSaysHowToWireAFlow:
    """`puml_notes` exists on the guidance contract; activity shipped without using it."""

    def _notes(self) -> str:
        return "\n".join(activity_module.write_guidance().puml_notes)

    def test_it_names_the_connection_shape(self) -> None:
        notes = self._notes()
        assert "diagram_connections" in notes
        for field in ("conn_type", "source", "target"):
            assert field in notes, f"the connection shape omits {field!r}"

    def test_it_states_the_mandatory_lane_connection(self) -> None:
        """Discovered previously only from a WARNING comment inside the generated PUML."""
        assert "step-in-lane" in self._notes()

    def test_it_states_that_a_decision_needs_three_edges(self) -> None:
        notes = self._notes()
        assert "step-then" in notes and "step-else" in notes and "step-flow" in notes

    def test_it_carries_a_worked_example(self) -> None:
        """A schema tells an author what is legal; an example tells them where to start."""
        notes = self._notes()
        assert "diagram_entities" in notes and "swimlane" in notes
