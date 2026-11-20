"""`to_mapping` and `from_mapping` are a pair, and the pair is what is tested.

Stated over what the form permits: the generated sets cover every operation, every field the
catalogue admits for it, addressed every way the catalogue says it can be, in every state — and they
are pushed through YAML and JSON on the way, because plain data that only survives in memory is not
yet plain data. The refusals cover mappings a file could hold that the writer never emits.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from hypothesis import given

from src.application.change_sets.change_set import FORMAT_VERSION, ChangeSet
from src.application.change_sets.operations import AddConnection, MalformedChangeSet
from src.application.change_sets.recorded_form import (
    from_mapping,
    operation_from_mapping,
    operation_to_mapping,
    to_mapping,
)
from src.application.modeling.edit_field_catalogue import CONTENT, IN_A_CHANGE_SET, KEYED
from tests.support.change_sets import (
    change_set,
    change_sets,
    create,
    edit,
    edit_connection,
    joins,
)

_A = "ENT@1.a"
_B = "ENT@1.b"


@given(change_sets())
def test_every_set_survives_being_written_down_and_read_back(generated: ChangeSet) -> None:
    assert from_mapping(to_mapping(generated)) == generated


@given(change_sets())
def test_it_survives_yaml_and_json_on_the_way(generated: ChangeSet) -> None:
    recorded = to_mapping(generated)
    assert from_mapping(yaml.safe_load(yaml.safe_dump(recorded))) == generated
    assert from_mapping(json.loads(json.dumps(recorded))) == generated


@given(change_sets())
def test_the_recorded_form_does_not_depend_on_assembly_order(generated: ChangeSet) -> None:
    rearranged = ChangeSet(tuple(reversed(generated.operations)), generated.repository_revision)
    assert to_mapping(rearranged) == to_mapping(generated)


_EDITS = [
    (kind, field) for kind in IN_A_CHANGE_SET for field in sorted(CONTENT[kind])
]


@pytest.mark.parametrize(("kind", "field"), _EDITS, ids=[f"{k}.{f}" for k, f in _EDITS])
def test_every_field_an_edit_may_name_survives(kind: str, field: str) -> None:
    """One case per field of the catalogue, so a field added there is covered here unasked."""
    key = "tier" if field in KEYED[kind] else None  # type: ignore[index]
    value: Any = {"a": ["b", 1, None, True], "c": {"d": "e"}}
    operation = (
        edit(_A, field, value, was="old", key=key)
        if kind == "entity"
        else edit_connection(joins(_A, _B), field, value, was="old", key=key)
    )
    assert operation_from_mapping(yaml.safe_load(yaml.safe_dump(operation_to_mapping(operation)))) == operation


def test_the_precondition_the_parametrisation_is_not_empty() -> None:
    assert {kind for kind, _ in _EDITS} == set(IN_A_CHANGE_SET)
    assert len(_EDITS) > 10


def test_a_note_is_recorded_only_where_there_is_one() -> None:
    assert "note" not in to_mapping(change_set(create("queue")))["operations"][0]

    noted = AddConnection(joins(_A, _B), {}, note="because the queue backs up")
    assert to_mapping(change_set(noted))["operations"][0]["note"] == "because the queue backs up"


def test_the_recorded_set_carries_no_header() -> None:
    """Only what any holder of operations has. A name or a state here would be a candidate's."""
    assert set(to_mapping(change_set())) == {"repository-revision", "format-version", "operations"}


def test_a_value_of_none_is_recorded_and_not_mistaken_for_absent() -> None:
    """Removing a key is an edit to `None`; a writer that dropped empty values would lose it."""
    removal = edit(_A, "properties", None, was="eu", key="region")
    recorded = operation_to_mapping(removal)
    assert recorded["value"] is None
    assert operation_from_mapping(recorded) == removal


class TestTheReaderRefusesWhatTheValueDoes:
    def _recorded(self, **changed: Any) -> dict[str, Any]:
        return {**to_mapping(change_set(edit(_A, "name", "x", was="y"))), **changed}

    def _operation(self, **changed: Any) -> dict[str, Any]:
        recorded = {**operation_to_mapping(edit(_A, "name", "x", was="y")), **changed}
        return {key: value for key, value in recorded.items() if value is not ...}

    @pytest.mark.parametrize("key", ["repository-revision", "format-version", "operations"])
    def test_a_missing_header_key_is_named(self, key: str) -> None:
        recorded = self._recorded()
        del recorded[key]
        with pytest.raises(MalformedChangeSet, match=f"missing.*{key}"):
            from_mapping(recorded)

    def test_a_key_the_form_does_not_define_is_refused_not_ignored(self) -> None:
        with pytest.raises(MalformedChangeSet, match="does not define"):
            from_mapping(self._recorded(owner="someone"))

    def test_a_set_written_by_a_later_version_is_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match="written in format"):
            from_mapping(self._recorded(**{"format-version": FORMAT_VERSION + 1}))

    def test_a_recorded_set_is_a_mapping(self) -> None:
        with pytest.raises(MalformedChangeSet, match="is a mapping"):
            from_mapping([self._operation()])

    def test_operations_are_a_list(self) -> None:
        with pytest.raises(MalformedChangeSet, match="is a list"):
            from_mapping(self._recorded(operations={"op": "edit_entity"}))

    def test_what_the_value_refuses_the_reader_refuses(self) -> None:
        twice = [self._operation(), self._operation(value="z")]
        with pytest.raises(MalformedChangeSet, match="one operation per key"):
            from_mapping(self._recorded(operations=twice))

    def test_an_unknown_operation_is_refused_with_the_six(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not an operation") as refusal:
            operation_from_mapping(self._operation(op="create_document"))
        assert "remove_connection" in str(refusal.value)

    def test_an_operation_is_a_mapping(self) -> None:
        with pytest.raises(MalformedChangeSet, match="is a mapping"):
            operation_from_mapping(["edit_entity"])

    @pytest.mark.parametrize("key", ["artifact_id", "field", "value", "base"])
    def test_a_missing_operation_key_is_named(self, key: str) -> None:
        with pytest.raises(MalformedChangeSet, match=f"missing.*{key}"):
            operation_from_mapping(self._operation(**{key: ...}))

    def test_a_misspelt_key_is_refused_rather_than_read_as_absent(self) -> None:
        with pytest.raises(MalformedChangeSet, match="does not define"):
            operation_from_mapping(self._operation(mode="remove"))

    @pytest.mark.parametrize(
        "base",
        [
            pytest.param("y", id="bare-value"),
            pytest.param({}, id="empty"),
            pytest.param({"value": "y", "revision": "abc"}, id="both"),
            pytest.param({"digest": "abc"}, id="another-word"),
        ],
    )
    def test_a_base_is_exactly_a_value_or_a_revision(self, base: Any) -> None:
        with pytest.raises(MalformedChangeSet, match="recorded base is either"):
            operation_from_mapping(self._operation(base=base))

    def test_a_removal_that_recorded_a_value_is_refused(self) -> None:
        recorded = {"op": "remove_entity", "artifact_id": _A, "base": {"value": {"name": "a"}}}
        with pytest.raises(MalformedChangeSet, match="revision of the record"):
            operation_from_mapping(recorded)

    def test_a_creates_fields_are_a_mapping(self) -> None:
        with pytest.raises(MalformedChangeSet, match="is a mapping"):
            operation_from_mapping({"op": "create_entity", "ref": "queue", "fields": ["name"]})

    def test_a_field_outside_the_vocabulary_is_refused_on_the_way_in(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not a field"):
            operation_from_mapping(self._operation(field="colour"))
