"""Where a candidate's target state stands is recorded on it, read back as written, and holds the candidate.

The recorded form is the pair that matters: what `to_mapping` writes, `from_mapping` reads, and a stored
candidate from before target states existed reads as one with none.
"""

import pytest

from src.application.change_sets.base import BaseValue
from src.application.change_sets.candidate_architecture import (
    CandidateArchitecture,
    MalformedCandidateArchitecture,
    TargetState,
    refused_while_targeted,
)
from src.application.change_sets.candidate_recorded_form import from_mapping, to_mapping
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import EditEntity

_STATE = TargetState(
    "PLT@1.a.baseline", "PLT@1.b.target", "ASS@1.c.gap",
    copies={"APP@1.d.ledger": "APP@1.e.ledger-target"}, added={"new-rule": "REQ@1.f.new-rule"},
)


def _candidate(**changes: object) -> CandidateArchitecture:
    edit = EditEntity("APP@1.d", "name", "Ledger service", BaseValue("Ledger"))
    held = CandidateArchitecture("CAND@1.g", "Ledger", "", "candidate", ChangeSet((edit,), "r1"), target_state=_STATE)
    return CandidateArchitecture(**{**{slot: getattr(held, slot) for slot in held.__slots__}, **changes})


def test_a_target_state_round_trips() -> None:
    candidate = _candidate()
    recorded = to_mapping(candidate)
    assert recorded["target-state"]["copies"] == {"APP@1.d": "APP@1.e.ledger-target"}
    assert from_mapping(recorded) == candidate


def test_a_candidate_recorded_before_target_states_reads_with_none() -> None:
    recorded = to_mapping(_candidate(target_state=None))
    assert "target-state" not in recorded
    assert from_mapping(recorded).target_state is None


@pytest.mark.parametrize("malformed", [
    {"baseline": "PLT@1.a", "target": "PLT@1.b"},
    {"baseline": "PLT@1.a", "target": "PLT@1.b", "gap": "ASS@1.c", "copies": {"APP@1.d": 3}},
    {"baseline": "PLT@1.a", "target": "PLT@1.b", "gap": "ASS@1.c", "extra": {}},
])
def test_a_malformed_target_state_is_refused(malformed: dict[str, object]) -> None:
    with pytest.raises(MalformedCandidateArchitecture, match="target"):
        from_mapping({**to_mapping(_candidate(target_state=None)), "target-state": malformed})


def test_a_target_state_is_recorded_and_cleared_only_by_an_application() -> None:
    held, free = _candidate(), _candidate(target_state=None)
    assert refused_while_targeted(free, held) is not None
    assert refused_while_targeted(held, free) is not None
    assert refused_while_targeted(free, held, applied=True) is None
    assert refused_while_targeted(held, free, applied=True) is None


def test_while_it_stands_the_state_and_the_operations_are_held_but_a_re_base_is_not() -> None:
    held = _candidate()
    rebased = _candidate(changes=ChangeSet((EditEntity("APP@1.d", "name", "Ledger service", BaseValue("Core")),), "r2"))
    emptied = _candidate(changes=ChangeSet((), "r2"))
    assert refused_while_targeted(held, _candidate(state="draft")) is not None
    assert refused_while_targeted(held, emptied) is not None
    assert refused_while_targeted(held, rebased) is None
    assert refused_while_targeted(held, _candidate(name="Renamed")) is None
