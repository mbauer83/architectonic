"""What a proposal records survives being written down and read back — over the whole vocabulary.

This project writes several of its own syntaxes and reads them back, and the register that exists
because of it says why the pair must be tested rather than each side separately: the renderer emitted
a trailing colour for specialised entities and the reader could not see past it, and no amount of
testing either half alone would have found that.

**Stated over what the encoding permits, not over what a writer emits today.** That caution is paid
for too: the first version of the equivalent gate elsewhere passed against a broken reading, because
the shipped catalogue happened to declare no colours. So the parametrisation below is derived from
`edit_field_catalogue` — every proposable kind, every field that kind admits — and a field added to
the catalogue is covered here the moment it is added, without anyone remembering to extend a list.

The value used is deliberately not field-shaped. What the encoding has to preserve is any value the
model's own serialisation admits — nested mappings, lists, numbers, booleans, `None` — so it is the
same structurally rich value for every field. A field-specific fixture would be a second catalogue,
and it would drift.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from src.application.modeling.edit_field_catalogue import PROPOSABLE, ArtifactKind, editable
from src.application.modeling.proposal_edit import (
    ProposalEdit,
    UnproposableEdit,
    from_mapping,
    to_mapping,
)

#: Every (kind, field) the encoding admits. The subject's own id is excluded: an edit names the
#: artifact it changes, and cannot also set it as a field.
_PERMITTED: list[tuple[ArtifactKind, str]] = [
    (kind, field)
    for kind in PROPOSABLE
    for field in sorted(editable(kind) - {"artifact_id"})
]

#: Rich enough to catch a serialisation that flattens, reorders or drops. Not field-shaped: see the
#: module docstring.
_VALUE: Any = {"a": ["b", 1, None, True], "c": {"d": "e"}, "f": []}


def test_the_permitted_set_is_not_empty() -> None:
    """The precondition: a parametrisation derived from an empty catalogue would assert nothing."""
    assert len(_PERMITTED) > 20, len(_PERMITTED)
    assert {kind for kind, _ in _PERMITTED} == set(PROPOSABLE)


@pytest.mark.parametrize(("kind", "field"), _PERMITTED, ids=[f"{k}.{f}" for k, f in _PERMITTED])
def test_every_permitted_field_survives_the_round_trip(kind: ArtifactKind, field: str) -> None:
    edit = ProposalEdit(kind=kind, artifact_id="ENT@1.aaaaaa.x", fields={field: _VALUE})

    read_back = from_mapping(yaml.safe_load(yaml.safe_dump(to_mapping(edit))))

    assert read_back == edit


def test_a_whole_vocabulary_at_once_survives_it_too() -> None:
    """One field at a time would not catch a writer that drops all but the last."""
    for kind in PROPOSABLE:
        fields = {name: _VALUE for name in editable(kind) - {"artifact_id"}}
        edit = ProposalEdit(kind=kind, artifact_id="ENT@1.aaaaaa.x", fields=fields)
        assert from_mapping(yaml.safe_load(yaml.safe_dump(to_mapping(edit)))) == edit


class TestTheReaderRefusesWhatTheUnionDoesNot:
    """A file is the one place a malformed edit arrives without an author present to correct it."""

    def test_a_field_outside_the_vocabulary_is_refused_on_the_way_in(self) -> None:
        recorded = {"kind": "entity", "artifact-id": "ENT@1.aaaaaa.x", "fields": {"invented": 1}}
        with pytest.raises(UnproposableEdit, match="not editable"):
            from_mapping(recorded)

    def test_a_kind_with_no_global_artifact_reference_is_refused(self) -> None:
        """A connection has no GAR, so a connection edit has nothing to be proposed against."""
        recorded = {"kind": "connection", "artifact-id": "x", "fields": {"description": "y"}}
        with pytest.raises(UnproposableEdit, match="cannot be proposed against"):
            from_mapping(recorded)

    def test_an_edit_that_changes_nothing_is_refused(self) -> None:
        with pytest.raises(UnproposableEdit, match="changes nothing"):
            from_mapping({"kind": "entity", "artifact-id": "ENT@1.aaaaaa.x", "fields": {}})

    def test_a_missing_key_is_named(self) -> None:
        with pytest.raises(UnproposableEdit, match="missing"):
            from_mapping({"kind": "entity"})

    def test_fields_must_be_a_mapping(self) -> None:
        with pytest.raises(UnproposableEdit, match="mapping"):
            from_mapping({"kind": "entity", "artifact-id": "x", "fields": ["name"]})

    def test_the_subject_cannot_be_set_as_a_field(self) -> None:
        recorded = {
            "kind": "entity", "artifact-id": "ENT@1.aaaaaa.x",
            "fields": {"artifact_id": "ENT@1.bbbbbb.y"},
        }
        with pytest.raises(UnproposableEdit, match="not a field it sets"):
            from_mapping(recorded)


def test_the_union_admits_exactly_the_three_referenceable_kinds() -> None:
    """A fourth arm is a decision about what a global artifact reference stands for."""
    from src.application.modeling.proposal_edit import arms

    assert arms() == ("entity", "document", "diagram")
    assert "connection" not in arms()
