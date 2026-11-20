"""A note's attributes are checked as the entity's properties would be, and carried into a lift.

They used to round-trip and nothing else: no check, and a lift dropped them, so what a person wrote
on a note was gone from the entity it became. These hold three things — where checking starts (the
level the meta-ontology says carries attributes), what blocks and what warns (what the entity write
itself would refuse, and everything else), and that a lift carries them.

The schema is the test's own, so the assertions may be exact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from src.application.scratchpad.lift import plan_lift
from src.application.scratchpad.note_attributes import attribute_findings
from src.application.scratchpad.response import to_response
from src.application.scratchpad.verification import note_verdict_source, verdict_source
from src.application.verification._verifier_rules_schema import stated_property_issues
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.ontology_representation.classification_levels import (
    DERIVED_DEFAULT_LEVELS,
    classification_levels_from_config,
)
from src.domain.scratchpad import ModelRef, Note, Scratchpad, scratchpad_from_parts
from src.infrastructure.app_bootstrap import build_module_registry

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "Priority": {"type": "string", "enum": ["high", "low"]},
        "Count": {"type": "integer", "minimum": 0},
    },
}
_NARROWER: dict[str, Any] = {
    "type": "object",
    "properties": {**_SCHEMA["properties"], "Regulation": {"type": "string"}},
}


def _schema_of(element_type: str, specializations: Sequence[str]) -> Mapping[str, Any] | None:
    """`requirement` declares a schema, its `regulatory` specialization a wider one, nothing else
    declares any."""
    if element_type != "requirement":
        return None
    return _NARROWER if "regulatory" in specializations else _SCHEMA


def _note(**fields: object) -> Note:
    defaults: dict[str, object] = {
        "id": "n1", "title": "A", "destination": "element", "element_type": "requirement",
    }
    return Note(**{**defaults, **fields})  # type: ignore[arg-type]


def _findings(note: Note, levels=DERIVED_DEFAULT_LEVELS):  # noqa: ANN001, ANN202
    return attribute_findings(note, levels, _schema_of)


class TestWhereCheckingStarts:
    def test_a_note_below_the_level_that_carries_attributes_keeps_them_free(self) -> None:
        narrowed = Note(
            id="n1", title="A", destination="element", domain="motivation",
            attributes={"Count": "not a number", "Anything": {"at": "all"}},
        )

        assert _findings(narrowed) == ()

    def test_an_undecided_note_keeps_them_free(self) -> None:
        assert _findings(Note(id="n1", title="A", attributes={"Count": "abc"})) == ()

    def test_a_note_at_the_type_is_checked_against_the_type_s_schema(self) -> None:
        assert "E042" in [finding.code for finding in _findings(_note(attributes={"Count": "abc"}))]

    def test_the_level_is_the_one_the_declaration_says_carries_attributes(self) -> None:
        """Declared so that only the level below the type carries them: a typed note is then still
        free, and a specialized one is checked."""
        levels = classification_levels_from_config({"classification_levels": [
            {"id": "kind", "from": "type", "required": True, "keys_relationships": True},
            {"id": "variant", "from": "specializations", "carries_attributes": True},
        ]})

        assert _findings(_note(attributes={"Count": "abc"}), levels) == ()
        assert _findings(
            _note(specialization="regulatory", attributes={"Count": "abc"}), levels
        ) != ()

    def test_a_specialized_note_is_checked_against_the_schema_its_specialization_merges_into(
        self
    ) -> None:
        plain = _findings(_note(attributes={"Regulation": "GDPR"}))
        specialized = _findings(_note(specialization="regulatory", attributes={"Regulation": "GDPR"}))

        assert ["not declared" in finding.message for finding in plain] == [True]
        assert specialized == ()

    def test_a_type_with_no_schema_is_a_free_schema(self) -> None:
        assert _findings(_note(element_type="goal", attributes={"Count": "abc"})) == ()

    def test_a_note_tied_to_the_model_is_not_checked(self) -> None:
        bound = _note(attributes={"Count": "abc"}, model_ref=ModelRef("REQ@1.a.x", "bound"))

        assert _findings(bound) == ()

    def test_a_note_with_no_attributes_is_told_nothing(self) -> None:
        assert _findings(_note()) == ()


class TestWhatBlocksAndWhatWarns:
    def test_a_value_the_write_cannot_read_as_its_declared_type_blocks_with_its_code(self) -> None:
        blocking = [finding for finding in _findings(_note(attributes={"Count": "abc"})) if finding.blocks]

        assert [finding.code for finding in blocking] == ["E042"]
        assert "type error on 'Count'" in blocking[0].message

    @pytest.mark.parametrize("value", [3, "3"])
    def test_a_value_of_the_declared_type_is_accepted_typed_or_as_its_cell(self, value: object) -> None:
        assert _findings(_note(attributes={"Count": value})) == ()

    def test_a_value_outside_what_the_schema_allows_warns_as_the_entity_write_does(self) -> None:
        (finding,) = _findings(_note(attributes={"Priority": "medium"}))

        assert (finding.blocks, finding.code) == (False, "W042")

    def test_an_attribute_the_schema_does_not_declare_warns(self) -> None:
        (finding,) = _findings(_note(attributes={"Colour": "blue"}))

        assert not finding.blocks
        assert "Attribute 'Colour' is not declared for requirement" in finding.message

    def test_a_value_no_property_can_hold_blocks(self) -> None:
        (finding,) = _findings(_note(attributes={"Priority": {"nested": "object"}}))

        assert (finding.blocks, finding.code) == (True, "E042")
        assert "Attribute 'Priority' holds a dict" in finding.message

    def test_each_finding_is_the_one_the_verifier_s_rule_gives_for_the_written_cell(self) -> None:
        """The same rule, asked the same question — so the canvas cannot disagree with the write."""
        attributes = {"Count": "abc", "Priority": "medium"}

        from_the_rule = stated_property_issues(
            attributes, _SCHEMA, artifact_type="requirement", attribute_types={}, loc=""
        )

        assert [(finding.code, finding.message) for finding in _findings(_note(attributes=attributes))] == [
            (issue.code, issue.message) for issue in from_the_rule
        ]


@pytest.fixture(scope="module")
def registry() -> ModuleRegistry:
    return build_module_registry(complete_vocabulary=True)


def _pad(note: Note) -> Scratchpad:
    return scratchpad_from_parts(artifact_id="SCR@1.a.pad", name="Pad", notes=[note])


class TestTheReadAndTheLiftAgree:
    def _plan(self, registry: ModuleRegistry, pad: Scratchpad):  # noqa: ANN202 — the plan's own type
        return plan_lift(
            pad, selection=["n1"], targets={},
            verdict_of=verdict_source(registry, pad),
            note_verdict_of=note_verdict_source(registry, pad, _schema_of),
        )

    def _served_note(self, registry: ModuleRegistry, pad: Scratchpad) -> dict[str, Any]:
        served = to_response(pad, group="g", registry=registry, attribute_schema=_schema_of)
        return served["notes"][0]

    def test_a_forbidden_value_is_served_as_a_refusal_and_blocks_the_lift_with_the_same_words(
        self, registry: ModuleRegistry
    ) -> None:
        pad = _pad(_note(attributes={"Count": "abc"}))

        verdict = self._served_note(registry, pad)["verdict"]
        plan = self._plan(registry, pad)

        assert (verdict["kind"], verdict["code"], verdict["blocks"]) == ("refused", "E042", True)
        assert plan.blocks
        (refused,) = plan.of("refuse")
        assert (refused.code, refused.reason) == ("E042", verdict["message"])

    def test_an_undeclared_attribute_is_served_as_a_warning_and_the_note_is_still_lifted(
        self, registry: ModuleRegistry
    ) -> None:
        pad = _pad(_note(attributes={"Colour": "blue"}))

        verdict = self._served_note(registry, pad)["verdict"]
        plan = self._plan(registry, pad)

        assert verdict["kind"] == "narrowed"
        assert not plan.blocks
        (created,) = plan.of("create")
        assert created.warning == verdict["message"]

    def test_a_lift_carries_the_attributes_as_the_entity_s_properties(
        self, registry: ModuleRegistry
    ) -> None:
        pad = _pad(_note(attributes={"Priority": "high", "Count": 3}))

        (created,) = self._plan(registry, pad).of("create")

        assert created.properties == {"Priority": "high", "Count": 3}
        assert created.warning == ""

    def test_a_note_below_the_attribute_level_is_served_no_verdict_and_keeps_its_attributes(
        self, registry: ModuleRegistry
    ) -> None:
        free = Note(
            id="n1", title="A", destination="element", domain="motivation",
            attributes={"Count": "not a number"},
        )

        served = self._served_note(registry, _pad(free))

        assert "verdict" not in served
        assert served["attributes"] == {"Count": "not a number"}
