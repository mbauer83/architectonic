"""A diagram may label an instance its own way, and the model's name is not touched.

The label an ArchiMate element carries on a picture used to be decided entirely by the element:
its display block's ``label``, else its name. A name that is right for the model is often too long
for a box on one crowded view, and shortening it meant renaming the element on every view at once.
``diagram-entities.display_labels`` — ``{instance id: label}`` — is the diagram's own say, keyed the
way every other per-instance statement is: the entity's artifact id for its base instance, the
occurrence id for a further one.

The round trip is asserted over what the syntax permits, not over the labels the GUI happens to
produce today: a label is spelled inside a quoted PlantUML string, and the alias reader must still
find the alias behind a label carrying quotes, an ``as`` token, a colour-looking ``#`` or guillemets.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.puml_alias_declarations import declared_aliases
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering.archimate_occurrences import display_label_overrides
from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer


def _goal(artifact_id: str, alias: str, name: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="goal",
        name=name,
        version="0.1.0",
        status="active",
        domain="motivation",
        subdomain="",
        path=Path(f"/fake/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=alias,
        host_diagram_id=None,
    )


_LONG = _goal("GOL@1000000000.AaAaAa.a-long-goal", "GOL_AaAaAa", "Provide Governed Self-Service Read Access")
_OTHER = _goal("GOL@1000000001.BbBbBb.another-goal", "GOL_BbBbBb", "Another Goal")


def _render(diagram_entities: dict[str, object]) -> str:
    return GenericPumlRenderer({"name": "archimate-motivation"}).render_body(
        "labels", [_LONG, _OTHER], [], "archimate-motivation", Path("/fake"), diagram_entities=diagram_entities,
    )


def _declaration_of(body: str, alias: str) -> str:
    # `as GOL_AaAaAa` is a prefix of `as GOL_AaAaAa__2`, so the alias is matched as a whole token.
    pattern = re.compile(rf"^\s*rectangle .* as {re.escape(alias)}(?:\s|$)")
    lines = [line for line in body.splitlines() if pattern.match(line)]
    assert len(lines) == 1, (alias, lines)
    return lines[0]


def _label_of(body: str, alias: str) -> str:
    """The text inside the declaration's quotes, after the type's sprite."""
    match = re.search(r'"(?:<\$[^>]+> )?(?P<label>[^"]*)"', _declaration_of(body, alias))
    assert match is not None
    return match.group("label")


class TestReadingTheOverrides:
    def test_absent_means_no_overrides(self) -> None:
        assert display_label_overrides(None) == {}
        assert display_label_overrides({"occurrence": []}) == {}

    def test_only_string_labels_of_string_keys_count(self) -> None:
        overrides = display_label_overrides({
            "display_labels": {"A@1.a.x": " Short ", "B@1.b.y": "", "C@1.c.z": 3, 4: "num"},
        })
        assert overrides == {"A@1.a.x": "Short"}

    def test_a_list_where_a_mapping_belongs_is_ignored_rather_than_fatal(self) -> None:
        assert display_label_overrides({"display_labels": ["A@1.a.x"]}) == {}


class TestLabellingABaseDrawing:
    def test_without_an_override_the_element_speaks_for_itself(self) -> None:
        assert _label_of(_render({}), "GOL_AaAaAa") == "Provide Governed Self-Service Read Access"

    def test_the_override_replaces_the_label_on_this_diagram_only(self) -> None:
        body = _render({"display_labels": {_LONG.artifact_id: "Self-Service Read Access"}})
        assert _label_of(body, "GOL_AaAaAa") == "Self-Service Read Access"
        # The model record is untouched: the override is a statement of the diagram, not a rename.
        assert _LONG.name == "Provide Governed Self-Service Read Access"

    def test_another_instance_keeps_its_own_label(self) -> None:
        body = _render({"display_labels": {_LONG.artifact_id: "Short"}})
        assert _label_of(body, "GOL_BbBbBb") == "Another Goal"

    def test_an_override_for_an_instance_the_diagram_does_not_hold_changes_nothing(self) -> None:
        assert _render({"display_labels": {"GOL@1.zz.gone": "Ghost"}}) == _render({})


class TestLabellingAnOccurrence:
    _DE: dict[str, object] = {
        "occurrence": [{"id": "occ-long-2", "backing_entity_id": _LONG.artifact_id}],
    }

    def test_the_occurrence_is_labelled_by_its_occurrence_id(self) -> None:
        body = _render({**self._DE, "display_labels": {"occ-long-2": "Read Access (again)"}})
        assert _label_of(body, "GOL_AaAaAa__2") == "Read Access (again)"
        assert _label_of(body, "GOL_AaAaAa") == "Provide Governed Self-Service Read Access"

    def test_the_base_instance_and_an_occurrence_are_labelled_independently(self) -> None:
        body = _render({
            **self._DE,
            "display_labels": {_LONG.artifact_id: "First", "occ-long-2": "Second"},
        })
        assert _label_of(body, "GOL_AaAaAa") == "First"
        assert _label_of(body, "GOL_AaAaAa__2") == "Second"


@pytest.mark.parametrize(
    "label",
    [
        'He said "as GOL_ZZ"',
        "Cost #red herring",
        "A <<not a stereotype>> B",
        "Two\nlines\tand   spacing",
        "Trailing colour-looking token #FFAA00",
    ],
)
def test_the_alias_reader_still_finds_every_alias_behind_any_permitted_label(label: str) -> None:
    body = _render({
        "occurrence": [{"id": "occ-long-2", "backing_entity_id": _LONG.artifact_id}],
        "display_labels": {_LONG.artifact_id: label, "occ-long-2": label},
    })
    found = {declaration.alias for declaration in declared_aliases(body)}
    assert {"GOL_AaAaAa", "GOL_AaAaAa__2", "GOL_BbBbBb"} <= found, found
    # One line per declaration: a newline inside the quoted string would end it early.
    assert _declaration_of(body, "GOL_AaAaAa").count('"') == 2


class TestABodyThatIsKeptVerbatim:
    """A hand-laid body never goes through the renderer, so the statement is applied to its lines."""

    _BODY = "\n".join([
        "@startuml kept",
        '  rectangle "<$archimate_goal{scale=1.2}> Provide Governed Self-Service Read Access" <<goal>> as GOL_AaAaAa',
        '  rectangle "<$archimate_goal{scale=1.2}> Another Goal" <<goal>> as GOL_BbBbBb',
        '  rectangle "<$archimate_goal{scale=1.2}> Read Access, again" <<goal>> as GOL_AaAaAa__2',
        "GOL_AaAaAa --> GOL_BbBbBb",
        "@enduml",
    ])
    _DE: dict[str, object] = {"occurrence": [{"id": "occ-long-2", "backing_entity_id": _LONG.artifact_id}]}
    _BY_ID = {_LONG.artifact_id: _LONG, _OTHER.artifact_id: _OTHER}

    def test_the_body_reports_what_it_calls_each_instance(self) -> None:
        from src.infrastructure.rendering.archimate_occurrences import drawn_labels_by_instance

        assert drawn_labels_by_instance(self._BODY, self._DE, self._BY_ID) == {
            _LONG.artifact_id: "Provide Governed Self-Service Read Access",
            _OTHER.artifact_id: "Another Goal",
            "occ-long-2": "Read Access, again",
        }

    def test_a_stated_label_is_written_into_the_declaration_and_nothing_else_moves(self) -> None:
        from src.infrastructure.rendering.archimate_occurrences import relabel_instances_in_body

        stated = {**self._DE, "display_labels": {_LONG.artifact_id: "Short", "occ-long-2": "Again"}}
        relabelled = relabel_instances_in_body(self._BODY, stated, self._BY_ID)

        sprite = "<$archimate_goal{scale=1.2}>"
        assert relabelled.splitlines()[1] == f'  rectangle "{sprite} Short" <<goal>> as GOL_AaAaAa'
        assert relabelled.splitlines()[3] == f'  rectangle "{sprite} Again" <<goal>> as GOL_AaAaAa__2'
        unchanged = [0, 2, 4, 5]
        assert [relabelled.splitlines()[i] for i in unchanged] == [self._BODY.splitlines()[i] for i in unchanged]

    def test_no_statement_means_the_body_is_returned_as_it_came(self) -> None:
        from src.infrastructure.rendering.archimate_occurrences import relabel_instances_in_body

        assert relabel_instances_in_body(self._BODY, self._DE, self._BY_ID) is self._BODY

    def test_writing_then_reading_agree_on_every_instance(self) -> None:
        from src.infrastructure.rendering.archimate_occurrences import (
            drawn_labels_by_instance,
            relabel_instances_in_body,
        )

        stated = {_LONG.artifact_id: 'Say "hi"', "occ-long-2": "Two\nlines", _OTHER.artifact_id: "Kept #red"}
        relabelled = relabel_instances_in_body(self._BODY, {**self._DE, "display_labels": stated}, self._BY_ID)

        assert drawn_labels_by_instance(relabelled, self._DE, self._BY_ID) == {
            _LONG.artifact_id: "Say 'hi'", "occ-long-2": "Two lines", _OTHER.artifact_id: "Kept #red",
        }
