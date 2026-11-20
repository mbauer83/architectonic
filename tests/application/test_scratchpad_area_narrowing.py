"""A note decided as something its area does not hold is warned about — on the read and in a lift.

Against the real registry, because what an area's domains resolve to is the ontology's to say. The
assertions are about the invariant — outside warns, inside is silent, the lift proceeds — and name
only types whose domain the shipped ontology is not going to move.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.application.scratchpad.lift import plan_lift
from src.application.scratchpad.response import to_response
from src.application.scratchpad.verification import note_verdict_source, verdict_source
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import (
    Area,
    Layout,
    LinkVerdict,
    Note,
    Point,
    Rect,
    Scratchpad,
    scratchpad_from_parts,
)
from src.infrastructure.app_bootstrap import build_module_registry


@pytest.fixture(scope="module")
def registry() -> ModuleRegistry:
    return build_module_registry(complete_vocabulary=True)


def _pad(*notes: Note) -> Scratchpad:
    """One narrowing area and one open one, every note placed in the narrowing one unless its id
    says otherwise."""
    return scratchpad_from_parts(
        artifact_id="SCR@1.a.pad",
        name="Pad",
        areas=[
            Area(id="strategy", label="Vision & strategy", permitted_domains=("motivation", "strategy")),
            Area(id="project", label="Project"),
        ],
        notes=notes,
        layout=Layout(
            areas={"strategy": Rect(0, 0, 400, 400), "project": Rect(0, 500, 400, 400)},
            notes={
                note.id: Point(40, 540) if note.id.startswith("project") else Point(40, 40)
                for note in notes
            },
        ),
    )


def _element(note_id: str, element_type: str) -> Note:
    return Note(id=note_id, title=note_id, destination="element", element_type=element_type)


def _served_notes(registry: ModuleRegistry, pad: Scratchpad) -> dict[str, dict]:
    served = to_response(pad, group="g", registry=registry)
    return {row["id"]: row for row in served["notes"]}


class TestTheReadCarriesTheWarning:
    def test_a_type_outside_the_area_is_served_a_narrowed_verdict_naming_the_area(
        self, registry: ModuleRegistry
    ) -> None:
        rows = _served_notes(registry, _pad(_element("n1", "application-component")))

        verdict = rows["n1"]["verdict"]
        assert verdict["kind"] == "narrowed"
        assert verdict["narrowed-by"] == "strategy"
        assert "application-component is outside what it permits" in verdict["message"]
        assert "blocks" not in verdict

    def test_a_type_inside_the_area_is_served_no_verdict(self, registry: ModuleRegistry) -> None:
        assert "verdict" not in _served_notes(registry, _pad(_element("n1", "goal")))["n1"]

    def test_the_same_type_in_an_area_that_narrows_nothing_is_served_no_verdict(
        self, registry: ModuleRegistry
    ) -> None:
        rows = _served_notes(registry, _pad(_element("project-n1", "application-component")))

        assert rows["project-n1"]["area"] == "project"
        assert "verdict" not in rows["project-n1"]

    def test_an_undecided_note_is_served_no_verdict(self, registry: ModuleRegistry) -> None:
        assert "verdict" not in _served_notes(registry, _pad(Note(id="n1", title="A")))["n1"]

    def test_the_verdict_is_never_stored(self, registry: ModuleRegistry) -> None:
        from src.application.scratchpad.document import to_document

        pad = _pad(_element("n1", "application-component"))

        assert all("verdict" not in row for row in to_document(pad)["notes"])


class TestALiftCarriesTheWarningAndStillLifts:
    def _sources(
        self, registry: ModuleRegistry, pad: Scratchpad
    ) -> dict[str, Callable[..., LinkVerdict]]:
        return {
            "verdict_of": verdict_source(registry, pad),
            "note_verdict_of": note_verdict_source(registry, pad),
        }

    def test_the_note_is_created_with_the_warning_the_canvas_shows(
        self, registry: ModuleRegistry
    ) -> None:
        pad = _pad(_element("n1", "application-component"), _element("n2", "goal"))

        plan = plan_lift(pad, selection=["n1", "n2"], targets={}, **self._sources(registry, pad))

        by_id = {item.id: item for item in plan.items}
        assert not plan.blocks
        assert by_id["n1"].outcome == "create"
        assert by_id["n1"].warning == _served_notes(registry, pad)["n1"]["verdict"]["message"]
        assert by_id["n2"].warning == ""
        assert [item.id for item in plan.warnings] == ["n1"]

    def test_a_document_note_outside_the_document_types_an_area_names_is_warned_too(
        self, registry: ModuleRegistry
    ) -> None:
        pad = scratchpad_from_parts(
            artifact_id="SCR@1.a.pad", name="Pad",
            areas=[Area(id="a", label="Decisions", permitted_document_types=("adr",))],
            notes=[Note(id="n1", title="A", destination="document", document_type="standard")],
            layout=Layout(areas={"a": Rect(0, 0, 400, 400)}, notes={"n1": Point(40, 40)}),
        )

        plan = plan_lift(pad, selection=["n1"], targets={}, **self._sources(registry, pad))

        assert plan.items[0].outcome == "create"
        assert "standard is outside what it permits" in plan.items[0].warning
