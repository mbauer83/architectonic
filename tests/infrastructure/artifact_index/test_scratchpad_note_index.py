"""Scratchpad notes are indexed, findable, and never above what someone committed to.

The condition Phase C §8.4 admitted them under: *indexed and findable, ranked below model content,
documents and diagrams*, because a note is a half-formed thought and an entity is a commitment. The
last clause is the one worth a test — it cannot be delivered by scoring weights, since bm25 and the
token-match supplement are on scales that say nothing about each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.domain.ontology_representation.artifact_types import ScratchpadNoteRecord
from src.infrastructure.artifact_index import shared_artifact_index

_PAD_ID = "SCR@1786299627.Dnc28yf.q3-thinking"
_QUERY = "chameleon"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scratchpad(*, name: str = "Q3 thinking") -> str:
    return f"""\
artifact-id: {_PAD_ID}
artifact-type: scratchpad
name: {name}
version: 0.1.3
status: draft
meta-ontology: archimate-4
areas:
- id: strategy
  label: Vision & strategy
notes:
- id: n1
  title: Chameleon onboarding
  body: A thought about how new tenants arrive.
  destination: element
  element-type: outcome
- id: n2
  title: Something else entirely
links: []
layout:
  areas:
    strategy: [0, 0, 800, 400]
  notes:
    n1: [40, 60]
    n2: [900, 900]
"""


def _entity(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: outcome
name: "{name}"
version: 0.1.0
status: draft
domain: motivation
---

## Content
A committed outcome about {name}.
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write(root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml", _scratchpad())
    return root


def _repository(root: Path) -> ArtifactRepository:
    index = shared_artifact_index(root)
    index.refresh()
    return ArtifactRepository(index)


def test_a_note_is_indexed_at_an_address_composed_from_its_scratchpad(repo_root: Path) -> None:
    notes = _repository(repo_root).list_scratchpad_notes()

    addresses = {note.artifact_id for note in notes}
    assert f"{_PAD_ID}#note/n1" in addresses
    assert f"{_PAD_ID}#note/n2" in addresses


def test_a_note_carries_its_container_and_its_derived_area(repo_root: Path) -> None:
    repo = _repository(repo_root)

    inside = repo.get_scratchpad_note(f"{_PAD_ID}#note/n1")
    outside = repo.get_scratchpad_note(f"{_PAD_ID}#note/n2")

    assert inside is not None and outside is not None
    assert inside.scratchpad_id == _PAD_ID
    assert inside.scratchpad_name == "Q3 thinking"
    assert inside.group == "platform-core"
    # Area membership is spatial and derived by the aggregate, never re-computed here.
    assert inside.area == "strategy"
    assert outside.area == "unfiled"
    # A note that has decided nothing wears nothing, and that is a legitimate state.
    assert inside.element_type == "outcome"
    assert outside.element_type == ""


def test_a_note_is_findable_by_its_own_words(repo_root: Path) -> None:
    result = _repository(repo_root).search_artifacts(_QUERY, limit=10)

    found = [hit for hit in result.hits if hit.record_type == "scratchpad-note"]
    assert [hit.record.artifact_id for hit in found] == [f"{_PAD_ID}#note/n1"]


def test_a_note_never_appears_above_model_content(repo_root: Path) -> None:
    # Enough entities matching the same word that a fair round-robin would interleave the note.
    for index in range(4):
        _write(
            repo_root / "model" / "motivation" / f"OUT@178000000{index}.aaaaaa.chameleon-{index}.md",
            _entity(f"OUT@178000000{index}.aaaaaa.chameleon-{index}", f"Chameleon {index}"),
        )

    result = _repository(repo_root).search_artifacts(_QUERY, limit=10)

    kinds = [hit.record_type for hit in result.hits]
    assert "scratchpad-note" in kinds, "the note is still findable"
    assert kinds.index("scratchpad-note") == len(kinds) - 1
    assert all(kind != "scratchpad-note" for kind in kinds[:-1])


def test_a_note_is_not_offered_as_something_to_reference(repo_root: Path) -> None:
    """The picker's opt-out, asserted at the level that owns it: a search that excludes the kind
    returns nothing from it, however well it matched."""
    result = _repository(repo_root).search_artifacts(_QUERY, limit=10, include_scratchpad_notes=False)

    assert all(hit.record_type != "scratchpad-note" for hit in result.hits)


def test_editing_a_scratchpad_reindexes_only_that_scratchpad(repo_root: Path) -> None:
    index = shared_artifact_index(repo_root)
    index.refresh()
    path = repo_root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml"

    # The note the first pass found, gone; and one the first pass did not have, added.
    path.write_text(
        _scratchpad().replace("title: Chameleon onboarding", "title: Renamed entirely"),
        encoding="utf-8",
    )
    index.apply_file_changes([path])

    repo = ArtifactRepository(index)
    assert repo.search_artifacts(_QUERY, limit=10).hits == []
    renamed = repo.get_scratchpad_note(f"{_PAD_ID}#note/n1")
    assert isinstance(renamed, ScratchpadNoteRecord)
    assert renamed.title == "Renamed entirely"


def test_deleting_a_scratchpad_takes_its_notes_with_it(repo_root: Path) -> None:
    index = shared_artifact_index(repo_root)
    index.refresh()
    path = repo_root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml"

    path.unlink()
    index.apply_file_changes([path])

    repo = ArtifactRepository(index)
    assert repo.list_scratchpad_notes() == []
    # And nothing is left behind in the full-text half either, which has no foreign key to cascade.
    assert repo.search_artifacts(_QUERY, limit=10).hits == []
