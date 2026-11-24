"""A drifted operation is re-based by recording it again: what it asks for kept, what it replaces read anew.

Standing's own advice for drift — make the edit again against the model as it stands now — done as one
act. The re-based operation then stands as `applies`, and an edit the model has come to agree with drops.
"""

import pytest

from src.application.change_sets.base import BaseRevision, BaseValue, record_revision
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    MalformedChangeSet,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.recording import rebased
from src.application.change_sets.standing import standing_of

SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"
ARTIFACTS = "PRC@1712870400.0Rz5Ex.promote-artifacts"
ACCESS = ConnectionAddress(ARTIFACTS, "archimate-access", SERVICE)
#: The model as it stands now: someone renamed the service after the candidate was written.
MOVED = RecordedReading(
    {SERVICE: {"name": "Promotion Desk"}, ARTIFACTS: {"name": "Promote Artifacts"}},
    {ACCESS: {"src_multiplicity": "1..*"}},
)


def draft(*operations) -> CandidateArchitecture:
    return CandidateArchitecture(
        id="CAND@1795000000.Naive01.naive", name="Naive architecture", rationale="", state="draft",
        changes=ChangeSet(tuple(operations), "rev-1"),
    )


def standings(candidate: CandidateArchitecture) -> list[str]:
    return [item.standing for item in standing_of(candidate.changes, MOVED)]


def test_a_drifted_rename_keeps_its_name_and_takes_the_model_s_as_its_base() -> None:
    written = draft(EditEntity(
        target=SERVICE, field="name", value="Promotion Service", base=BaseValue("Repository Promotion Service"),
    ))
    assert standings(written) == ["drifted"]

    now = rebased(written, written.changes.operations, MOVED)

    assert now.changes.operations == (
        EditEntity(target=SERVICE, field="name", value="Promotion Service", base=BaseValue("Promotion Desk")),
    )
    assert standings(now) == ["applies"]


def test_a_drifted_removal_reads_the_revision_of_what_is_there_now() -> None:
    written = draft(RemoveEntity(target=SERVICE, base=BaseRevision(record_revision({"name": "Old"}))))
    assert standings(written) == ["drifted"]

    now = rebased(written, written.changes.operations, MOVED)

    assert now.changes.operations == (
        RemoveEntity(target=SERVICE, base=BaseRevision(record_revision({"name": "Promotion Desk"}))),
    )
    assert standings(now) == ["applies"]


def test_a_drifted_connection_edit_is_rebased_on_its_address() -> None:
    written = draft(EditConnection(address=ACCESS, field="src_multiplicity", value="1", base=BaseValue("0..1")))
    assert standings(written) == ["drifted"]

    now = rebased(written, written.changes.operations, MOVED)

    assert now.changes.operations[0].base == BaseValue("1..*")
    assert standings(now) == ["applies"]


def test_an_edit_the_model_came_to_agree_with_drops() -> None:
    written = draft(EditEntity(target=SERVICE, field="name", value="Promotion Desk", base=BaseValue("Old")))

    assert rebased(written, written.changes.operations, MOVED).changes.operations == ()


def test_what_a_set_creates_has_no_base_to_re_read() -> None:
    create = CreateEntity(ref="queue", fields={"artifact_type": "service", "name": "Queue", "group": "g"})

    with pytest.raises(MalformedChangeSet, match="no base to re-read"):
        rebased(draft(create), (create,), MOVED)
