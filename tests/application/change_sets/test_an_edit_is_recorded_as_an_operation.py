"""An edit made to a candidate on the canvas is recorded as one of its operations, merged per claim.

The editor states what it wants; the base is read from what the stack beneath the candidate says. An
edit replaces the one before it on the same claim, an edit back to the base drops it, and what the
candidate itself creates is edited and removed in place.
"""

import pytest

from src.application.change_sets.base import BaseRevision, BaseValue, prose_revision, record_revision
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditEntity,
    MalformedChangeSet,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.recording import recorded

SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"
ARTIFACTS = "PRC@1712870400.0Rz5Ex.promote-artifacts"
QUEUE = "DOB@1795000000.Queue01.promotion-queue"
ACCESS = ConnectionAddress(ARTIFACTS, "archimate-access", SERVICE)
SERVICE_FIELDS = {"name": "Repository Promotion Service", "summary": "Reviews promotions.", "status": "active"}
MODEL = RecordedReading(
    {SERVICE: SERVICE_FIELDS, ARTIFACTS: {"name": "Promote Artifacts"}},
    {ACCESS: {"description": "reads"}},
)


def draft(*operations, state="draft") -> CandidateArchitecture:
    return CandidateArchitecture(
        id="CAND@1795000000.Naive01.naive", name="Naive architecture", rationale="", state=state,
        changes=ChangeSet(tuple(operations), "rev-1"),
    )


def record(candidate: CandidateArchitecture, **intent) -> CandidateArchitecture:
    return recorded(candidate, intent, MODEL)


def test_a_rename_records_the_name_it_replaces_and_a_second_rename_replaces_the_first() -> None:
    once = record(draft(), op="edit_entity", artifact_id=SERVICE, field="name", value="Promotion Service")
    twice = record(once, op="edit_entity", artifact_id=SERVICE, field="name", value="Review Service")

    assert twice.changes.operations == (
        EditEntity(
            target=SERVICE, field="name", value="Review Service", base=BaseValue("Repository Promotion Service"),
        ),
    )


def test_an_edit_back_to_its_base_drops_the_operation() -> None:
    renamed = record(draft(), op="edit_entity", artifact_id=SERVICE, field="name", value="Promotion Service")

    back = record(renamed, op="edit_entity", artifact_id=SERVICE, field="name", value="Repository Promotion Service")

    assert back.changes.operations == ()


def test_an_edit_of_prose_records_the_revision_of_the_text_it_replaces() -> None:
    edited = record(draft(), op="edit_entity", artifact_id=SERVICE, field="summary", value="One queue each.")

    assert edited.changes.operations[0].base == BaseRevision(prose_revision("Reviews promotions."))


def test_what_the_candidate_creates_is_renamed_in_its_create_and_named_by_its_alias() -> None:
    created = record(draft(), op="create_entity", artifact_id=QUEUE,
                     fields={"artifact_type": "data-object", "name": "Queue", "group": "platform-core"})
    renamed = record(created, op="edit_entity", artifact_id=QUEUE, field="name", value="Promotion Queue")
    linked = record(renamed, op="add_connection", source_entity=ARTIFACTS, connection_type="archimate-access",
                    target_entity=QUEUE, fields={})

    create, link = sorted(linked.changes.operations, key=lambda op: type(op).__name__, reverse=True)
    assert isinstance(create, CreateEntity) and create.fields["name"] == "Promotion Queue"
    assert create.artifact_id == QUEUE
    assert link == AddConnection(ConnectionAddress(ARTIFACTS, "archimate-access", create.reference), {})


def test_removing_what_the_candidate_created_takes_back_the_create_and_what_names_it() -> None:
    created = record(draft(), op="create_entity", artifact_id=QUEUE,
                     fields={"artifact_type": "data-object", "name": "Queue", "group": "platform-core"})
    linked = record(created, op="add_connection", source_entity=ARTIFACTS, connection_type="archimate-access",
                    target_entity=QUEUE, fields={})

    assert record(linked, op="remove_entity", artifact_id=QUEUE).changes.operations == ()


def test_removing_a_model_entity_records_its_revision_and_drops_its_edits() -> None:
    renamed = record(draft(), op="edit_entity", artifact_id=SERVICE, field="name", value="Promotion Service")

    removed = record(renamed, op="remove_entity", artifact_id=SERVICE)

    revision = BaseRevision(record_revision(SERVICE_FIELDS))
    assert removed.changes.operations == (RemoveEntity(target=SERVICE, base=revision),)


def test_removing_a_model_connection_records_its_revision() -> None:
    removed = record(draft(), op="remove_connection", source_entity=ARTIFACTS, connection_type="archimate-access",
                     target_entity=SERVICE)

    revision = BaseRevision(record_revision({"description": "reads"}))
    assert removed.changes.operations == (RemoveConnection(ACCESS, revision),)


@pytest.mark.parametrize(
    ("candidate", "intent", "says"),
    [
        (draft(state="candidate"), {"op": "remove_entity", "artifact_id": SERVICE}, "only a draft"),
        (draft(), {"op": "rename", "artifact_id": SERVICE}, "not an edit a candidate records"),
        (draft(), {"op": "edit_entity", "artifact_id": SERVICE, "value": "x"}, "states its field"),
        (draft(), {"op": "remove_entity", "artifact_id": QUEUE}, "not an entity this candidate can see"),
    ],
)
def test_an_edit_that_cannot_be_recorded_is_refused_saying_why(candidate, intent, says) -> None:
    with pytest.raises(MalformedChangeSet, match=says):
        recorded(candidate, intent, MODEL)
