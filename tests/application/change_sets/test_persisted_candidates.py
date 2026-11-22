from dataclasses import replace
from pathlib import Path

import pytest

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.candidate_recorded_form import dump_candidate, load_candidate
from src.application.change_sets.change_set import ChangeSet
from src.infrastructure.candidates.repository import CandidateConflict, CandidateRepository


def test_record_round_trip_and_concurrent_replacement(tmp_path: Path) -> None:
    repo = CandidateRepository(tmp_path)
    draft = CandidateArchitecture("CAND@1790000000.AbCdef.queue", "Queue", "", "draft", ChangeSet((), "base"))
    assert load_candidate(dump_candidate(draft)) == draft
    version = repo.save(draft, None)
    assert repo.require(draft.id) == draft
    edited = replace(draft, name="Promotion queue")
    assert repo.save(edited, version) != version
    with pytest.raises(CandidateConflict):
        repo.save(replace(draft, name="Another queue"), version)
    assert repo.list() == [edited]
