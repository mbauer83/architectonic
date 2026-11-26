"""A caller names what a candidate's stack creates by the id its create chose, at every level, and is answered so.

Inside a set the entity is named by its create's alias; that is `created_names`' to translate, both ways, from
one mapping. Regression: an adaptation could edit an element its parent created only by the `$ref:` handle, a
drop by the handle was refused, and the composed view and every read over it spoke the handle.
"""

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.candidate_view import view_of
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import compose
from src.application.change_sets.created_names import (
    chosen_ids,
    named_by_alias,
    named_by_id,
    named_in_sentence,
    reference_for,
    spoken,
)
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditEntity,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.recording import recorded
from src.domain.provisional_reference import named_in_text

READER = "APP@1712870400.v9LvfK"
EXTRACTOR = "APP@1795687000.aTx0001"
TEXT = "DOB@1795687000.dMp0007"
_EXTRACTOR = CreateEntity("1795687000-aTx0001", {
    "artifact_type": "application-component", "name": "Text Extractor", "group": "g"}, f"{EXTRACTOR}.text-extractor")
_TEXT = CreateEntity("1795687000-dMp0007", {"artifact_type": "data-object", "name": "Extracted Text", "group": "g"},
                     TEXT)
_SERVES = AddConnection(ConnectionAddress(_EXTRACTOR.reference, "archimate-serving", READER), {})
MODEL = RecordedReading({READER: {"artifact_type": "application-component", "name": "Reader"}}, {})


def _naive() -> CandidateArchitecture:
    return CandidateArchitecture("CAND@1795687000.Naive01", "Naive", "", "draft",
                                 ChangeSet((_EXTRACTOR, _TEXT, _SERVES), "r1"), scope=(READER,))


def _adaptation(*operations) -> CandidateArchitecture:
    return CandidateArchitecture("CAND@1795687000.Adapt01", "Adapt", "", "draft", ChangeSet(tuple(operations), "r1"),
                                 parent_id="CAND@1795687000.Naive01")


def _record(adaptation: CandidateArchitecture, **intent) -> CandidateArchitecture:
    naive = _naive()
    beneath = compose(ChangeSet((), "r1"), MODEL, beneath=(naive.changes,))
    return recorded(adaptation, intent, beneath, chosen_ids((naive.changes,)))


def test_one_mapping_reads_a_callers_id_as_the_alias_and_answers_the_alias_as_the_id() -> None:
    chosen = chosen_ids((_naive().changes,))
    assert chosen == {_EXTRACTOR.ref: _EXTRACTOR.artifact_id, _TEXT.ref: TEXT}
    for spelled in (EXTRACTOR, f"{EXTRACTOR}.text-extractor", _EXTRACTOR.reference):
        assert reference_for(spelled, chosen) == _EXTRACTOR.reference
    assert reference_for(READER, chosen) == READER
    assert spoken(_EXTRACTOR.reference, chosen) == EXTRACTOR
    assert spoken(READER, chosen) == READER
    assert named_by_alias(named_by_id(_SERVES, chosen), chosen) == _SERVES
    assert named_in_sentence(f"name of {_TEXT.reference} is as expected.", chosen) == f"name of {TEXT} is as expected."


def test_a_sentence_rewrites_a_reference_only_where_it_ends() -> None:
    names = {"queue": "A@1.q", "queue-2": "B@1.r"}
    assert named_in_text("$ref:queue-2, then $ref:queue. $ref:queue-3", names) == "B@1.r, then A@1.q. $ref:queue-3"


def test_an_adaptation_edits_a_parent_created_element_by_its_id_in_either_spelling() -> None:
    for spelled in (TEXT, f"{TEXT}.extracted-text", _TEXT.reference):
        edited = _record(_adaptation(), op="edit_entity", artifact_id=spelled, field="name", value="Recognised Text")
        (edit,) = edited.changes.operations
        assert isinstance(edit, EditEntity) and edit.target == _TEXT.reference, spelled


def test_an_adaptation_connects_removes_and_drops_a_parent_created_element_by_its_id() -> None:
    connected = _record(_adaptation(), op="add_connection", source_entity=READER,
                        connection_type="archimate-serving", target_entity=EXTRACTOR)
    assert connected.changes.operations[0].address == ConnectionAddress(
        READER, "archimate-serving", _EXTRACTOR.reference)

    removed = _record(_adaptation(), op="remove_entity", artifact_id=TEXT)
    assert isinstance(removed.changes.operations[0], RemoveEntity)
    assert removed.changes.operations[0].target == _TEXT.reference

    edited = _record(_adaptation(), op="edit_entity", artifact_id=TEXT, field="name", value="Recognised Text")
    for spelled in (TEXT, _TEXT.reference):
        assert _record(edited, op="drop", artifact_id=spelled).changes.operations == (), spelled


def test_a_candidate_drops_what_it_creates_by_its_handle_as_by_its_id() -> None:
    for spelled in (EXTRACTOR, _EXTRACTOR.reference):
        assert _record(_naive(), op="drop", artifact_id=spelled).changes.operations == (_TEXT,), spelled


def test_the_view_of_a_stack_names_every_created_element_by_its_id_and_reads_a_kept_handle() -> None:
    adapted = _record(_adaptation(), op="add_connection", source_entity=TEXT,
                      connection_type="archimate-association", target_entity=READER)
    view = view_of((_naive(), adapted), MODEL)

    assert set(view.entities) == {READER, EXTRACTOR, TEXT}
    assert {(a.source_entity, a.target_entity) for a in view.connections} == {(EXTRACTOR, READER), (TEXT, READER)}
    assert view.chosen == {EXTRACTOR: _EXTRACTOR.artifact_id, TEXT: TEXT}
    assert view.spelling()[_TEXT.reference] == TEXT  # a row written with the handle still reads
    assert "$ref:" not in str(view.wire())
