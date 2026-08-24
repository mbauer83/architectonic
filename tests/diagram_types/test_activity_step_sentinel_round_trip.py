"""The sentinel this project writes onto an activity step, and reads back off one, agree.

CLAUDE.md's rule: where the project both writes a syntax and reads it back, test the *pair*, not
the writer against a fixture and the reader against another. And state it over what the syntax
**permits** rather than over what the writer emits today — the caution is paid for, because the
first version of the PUML round-trip gate passed against a broken reading only because the shipped
content happened not to exercise the case that broke.

So the permitted cases are here explicitly: both emission forms, an id carrying the one character
the writer escapes, a user link alongside the sentinel, and an id that is a full artifact id. Then
every shape in the catalogue, which is the writer's real output.
"""

from __future__ import annotations

import pytest

from src.diagram_types.activity._step_links import (
    LABELLED_STEP_KINDS,
    drawn_lane_ids,
    drawn_step_ids,
    link_suffix,
    sentinel_of,
    sentinel_target,
    sentinel_wrapped,
)
from tests.diagram_types._activity_shapes import CATALOGUE, ActivityShape, bundled_shapes


def _all_shapes() -> list[ActivityShape]:
    return [*CATALOGUE, *bundled_shapes()]


@pytest.mark.parametrize(
    "step",
    [
        pytest.param({"id": "a_select"}, id="plain-local-id"),
        pytest.param({"id": "FNC@1786225282.foobGD2.write-lifted-model-content"}, id="artifact-shaped-id"),
        pytest.param({"id": "odd]id"}, id="id-carrying-the-escaped-bracket"),
        pytest.param({"id": "a_draw", "entity_id": "FNC@1.a.draw-a-link"}, id="bound-to-an-entity"),
        pytest.param({"id": "a_draw", "link": "https://example.test/spec"}, id="alongside-a-user-link"),
        pytest.param({"id": "a_draw", "entity_id": "E@1.a.b", "link": "https://e.test/x"}, id="bound-and-linked"),
    ],
)
class TestBothEmissionFormsReadBack:
    def test_the_wrapped_label_form(self, step: dict[str, object]) -> None:
        """`:[[arch://id label]];` — the id ends at the space before the label."""
        line = f":{sentinel_wrapped(step, 'some label')};"

        assert sentinel_of(line) == sentinel_target(step)

    def test_the_standalone_clause_form(self, step: dict[str, object]) -> None:
        """`partition "label" [[arch://id]] {` — the id ends at the closing bracket."""
        line = f'partition "some label"{link_suffix(step)} {{'

        assert sentinel_of(line) == sentinel_target(step)


class TestALineWithNoSentinelReadsAsNone:
    @pytest.mark.parametrize(
        "line",
        ["fork", "end fork", "endif", "detach", "(A)", "|Architectonic|", "note right: prose",
         ":a step with no sentinel;", 'partition "unbound" {', ":[[https://example.test/x]];"],
    )
    def test_it(self, line: str) -> None:
        assert sentinel_of(line) is None


class TestWhatTheWriterEmitsIsWhatTheReaderFinds:
    @pytest.mark.parametrize("shape", _all_shapes(), ids=lambda s: s.name)
    def test_every_labelled_step_of_every_shape_round_trips(self, shape: ActivityShape) -> None:
        """The pair over the writer's real output, not over a hand-written line."""
        declared = {
            sentinel_target(item)
            for kind in LABELLED_STEP_KINDS
            for item in (shape.entities.get(kind) or [])  # type: ignore[union-attr]
            if isinstance(item, dict) and item.get("id")
        }

        assert drawn_step_ids(shape.render()) == declared

    @pytest.mark.parametrize("shape", _all_shapes(), ids=lambda s: s.name)
    def test_every_lane_of_every_shape_round_trips(self, shape: ActivityShape) -> None:
        """The other half of the syntax, since a bound lane became selectable. Read apart from the
        steps, because W045 asks about steps and a lane counted as one makes that unanswerable."""
        declared = {
            sentinel_target(item)
            for item in (shape.entities.get("swimlane") or [])  # type: ignore[union-attr]
            if isinstance(item, dict) and item.get("id")
        }

        assert drawn_lane_ids(shape.render()) <= declared, "a lane header names something undeclared"
