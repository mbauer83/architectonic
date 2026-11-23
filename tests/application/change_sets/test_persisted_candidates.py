from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

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


def test_two_writers_replacing_one_version_preserve_the_winner(tmp_path: Path) -> None:

    draft = CandidateArchitecture("CAND@1790000000.AbCdef.queue", "Queue", "", "draft", ChangeSet((), "base"))
    version = CandidateRepository(tmp_path).save(draft, None)
    ready = Barrier(2)

    def save(name: str) -> str | None:
        store = CandidateRepository(tmp_path)
        ready.wait()
        try:
            store.save(replace(draft, name=name), version)
        except CandidateConflict:
            return None
        return name

    with ThreadPoolExecutor(2) as writers:
        winners = list(writers.map(save, ("One", "Two")))
    assert [name for name in winners if name] == [CandidateRepository(tmp_path).require(draft.id).name]
