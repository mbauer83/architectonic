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
from src.domain.scratchpad import Note
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


def test_saving_through_the_repository_makes_a_note_findable_without_a_refresh(repo_root: Path) -> None:
    """The wiring, not the mechanism — and the distinction is the whole point of this test.

    Every other case here calls `apply_file_changes` itself, so they assert that the applier works
    and say nothing about whether anything *calls* it. Nothing did: the loader and the incremental
    applier both shipped, no write path notified the index, and a note written on the canvas was
    searchable only after the next full refresh. Which is to say the feature's headline claim —
    notes are findable — was false through the only door a person uses.
    """
    from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository

    index = shared_artifact_index(repo_root)
    index.refresh()
    repository = YamlScratchpadRepository(repo_root)

    stored = repository.load(_PAD_ID)
    repository.save(
        stored.with_note(Note(id="n3", title="Iguanodon arrived late")),
        group=repository.group_of(_PAD_ID),
        expected_version=stored.version,
    )

    found = ArtifactRepository(index).search_artifacts("Iguanodon", limit=10).hits
    assert [hit.record.artifact_id for hit in found] == [f"{_PAD_ID}#note/n3"]


def test_a_scratchpad_write_does_not_move_the_model_read_model_version(repo_root: Path) -> None:
    """A canvas saves about once a second while someone is thinking, and a note is not model
    content — it is not listed by `list_artifacts` and it ranks below everything in search. Bumping
    the generation would invalidate every model ETag in the product at that rate, for a change no
    model reader can observe."""
    index = shared_artifact_index(repo_root)
    index.refresh()
    before = index.read_model_version()
    path = repo_root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml"

    index.apply_file_changes([path])

    assert index.read_model_version().generation == before.generation


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


def test_a_note_is_not_findable_by_its_scratchpads_name(tmp_path: Path) -> None:
    """A pad is a container; its notes are what search can return. Matching the container's name
    therefore answers with notes holding none of the query — ask for "Marsupial migration" and get a
    note called "Something else entirely", which reads as a wrong answer however it was reached.

    This file asserted the opposite earlier in the same release, on the reading that a pad's title is
    how a reader asks for the pad. It is — but a note cannot be that answer, and returning its
    contents is not a lesser version of finding the pad, it is a different and wrong result.

    Over a combined store, because that is the shape the backend serves.
    """
    from src.infrastructure.artifact_index import combined_artifact_index

    engagement = tmp_path / "engagement"
    enterprise = tmp_path / "enterprise"
    _write(
        engagement / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml",
        _scratchpad(name="Marsupial migration"),
    )
    _write(
        enterprise / "model" / "motivation" / "OUT@1780000009.aaaaaa.unrelated.md",
        _entity("OUT@1780000009.aaaaaa.unrelated", "Unrelated outcome"),
    )
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    found = ArtifactRepository(combined).search_artifacts("marsupial", limit=10).hits

    assert [hit.record.artifact_id for hit in found] == [], (
        "a note answered a query only its pad's title matched"
    )


def test_a_note_is_still_findable_by_its_own_words_in_a_combined_store(tmp_path: Path) -> None:
    """Withdrawing the pad's name must not cost a note a match it made on its own."""
    from src.infrastructure.artifact_index import combined_artifact_index

    engagement = tmp_path / "engagement"
    (tmp_path / "enterprise" / "model").mkdir(parents=True, exist_ok=True)
    _write(
        engagement / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml",
        _scratchpad(name="Marsupial migration"),
    )
    combined = combined_artifact_index(engagement, tmp_path / "enterprise")
    combined.refresh()

    found = ArtifactRepository(combined).search_artifacts(_QUERY, limit=10).hits

    assert [hit.record.artifact_id for hit in found] == [f"{_PAD_ID}#note/n1"]


def test_the_pad_name_contributes_nothing_to_a_notes_score() -> None:
    """Stated on the scorer as well as on the index, because a note reaches a caller by two paths —
    the FTS row, and the scored supplement that runs for a kind with no FTS hits. A rule honoured by
    one of them is a rule a reader cannot rely on."""
    from src.application.artifacts.scoring import score_scratchpad_note

    def _note(*, title: str, scratchpad_name: str) -> ScratchpadNoteRecord:
        return ScratchpadNoteRecord(
            artifact_id=f"{_PAD_ID}#note/n1",
            scratchpad_id=_PAD_ID,
            scratchpad_name=scratchpad_name,
            note_id="n1",
            title=title,
            body="",
            element_type="",
            domain="",
            group="platform-core",
            area="unfiled",
            status="draft",
            path=Path("x.scratchpad.yaml"),
        )

    by_pad = score_scratchpad_note(_note(title="Unrelated", scratchpad_name="Marsupial"), "marsupial", ["marsupial"])
    by_title = score_scratchpad_note(_note(title="Marsupial", scratchpad_name="Unrelated"), "marsupial", ["marsupial"])

    assert by_pad == 0.0, "a note scored for a word only its pad's title holds"
    assert by_title > 0.0, "a note still scores for its own title"
