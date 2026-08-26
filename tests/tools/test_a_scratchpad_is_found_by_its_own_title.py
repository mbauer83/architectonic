"""A scratchpad is findable by its own name.

A scratchpad has a name, a description, a version, a status and a group — everything an artifact has —
and it was **not a searchable record at all**. Measured on the served repository before this existed:
the one pad is named `Q3 platform thinking`, and querying exactly that returned twenty hits, none of
them the pad.

0.7.1 stopped a *note* answering for its pad, which removed the wrong answer without providing the
right one. `score_scratchpad_note`'s docstring records why the note-shaped answer was wrong — asking
for "Q3 platform thinking" and receiving a note called "AI-Assisted and Agentic Development" reads as
a wrong answer however it was reached — and says the remedy in as many words: *"Finding the pad is a
different question, and one a note-shaped result cannot answer."*

**The sharpest case is the pad whose every note has been lifted.** `_still_a_thought` filters a note
out once it has a model counterpart, so a pad whose thinking has all become entities has no searchable
notes at all — and the pad is then the only trace that the thinking happened. A note-only index goes
silent on exactly the pad with the most history behind it.

**What surfaces a pad is not an exemption from subordination.** A pad *is* preliminary, and on
similarity alone it belongs below committed content. What puts it at the top is that the reader typed
its name: the first ranking section is kind-blind, so a pad named for what was asked reaches rank 1
whatever its kind. Both halves are asserted here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index

_PAD_ID = "SCR@1786299627.Dnc28yf.q3-platform-thinking"
_OTHER_PAD_ID = "SCR@1786299628.Kfj20xz.chameleon-onboarding"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _pad(
    *,
    artifact_id: str = _PAD_ID,
    name: str = "Q3 platform thinking",
    description: str = "A worked example of the scratchpad tier, committed so the repository ships one.",
    notes: str = """\
notes:
- id: n1
  title: Contributors stall at the first type picker
  body: A thought about the barrier to a first contribution.
- id: n2
  title: Something else entirely
""",
) -> str:
    return f"""\
artifact-id: {artifact_id}
artifact-type: scratchpad
name: {name}
description: {description}
version: 0.1.8
status: draft
meta-ontology: archimate-4
areas:
- id: strategy
  label: Vision & strategy
{notes}links: []
layout:
  areas:
    strategy: [0, 0, 800, 400]
  notes: {{}}
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
A committed outcome about {name}, mentioning platform thinking throughout.
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write(root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml", _pad())
    return root


def _repository(root: Path) -> ArtifactRepository:
    index = shared_artifact_index(root)
    index.refresh()
    return ArtifactRepository(index)


def _hits(root: Path, query: str, **kwargs: object):
    return _repository(root).search_artifacts(query, limit=12, **kwargs).hits


class TestAPadIsAKindOfItsOwn:
    def test_a_pad_is_returned_for_its_own_name(self, repo_root: Path) -> None:
        found = [h for h in _hits(repo_root, "Q3 platform thinking") if h.record_type == "scratchpad"]

        assert [h.record.artifact_id for h in found] == [_PAD_ID]

    def test_a_pad_named_by_the_reader_leads_the_answer(self, repo_root: Path) -> None:
        """The reason cycle 1 comes first: without the kind-blind first section a pad is subordinate
        and lands in the reserved last slot, which is below the fold in a twelve-row dropdown."""
        for index in range(6):
            _write(
                repo_root / "model" / "motivation" / f"OUT@178000000{index}.aaaaaa.platform-{index}.md",
                _entity(f"OUT@178000000{index}.aaaaaa.platform-{index}", f"Platform thinking {index}"),
            )

        hits = _hits(repo_root, "Q3 platform thinking")

        assert hits[0].record_type == "scratchpad"
        assert hits[0].record.artifact_id == _PAD_ID

    def test_a_pad_carries_the_fields_its_listing_publishes(self, repo_root: Path) -> None:
        """The record's fields are the fields `GET /api/scratchpads` already publishes, so the two
        surfaces cannot disagree about what a pad is."""
        record = _repository(repo_root).get_scratchpad(_PAD_ID)

        assert record is not None
        assert record.name == "Q3 platform thinking"
        assert record.description.startswith("A worked example")
        assert record.version == "0.1.8"
        assert record.status == "draft"
        assert record.group == "platform-core"


class TestWhatAPadMatchesOn:
    def test_a_pad_matches_its_own_description(self, repo_root: Path) -> None:
        found = [h for h in _hits(repo_root, "worked example") if h.record_type == "scratchpad"]

        assert [h.record.artifact_id for h in found] == [_PAD_ID]

    def test_a_pad_does_not_match_its_notes_words(self, repo_root: Path) -> None:
        """The decision, and the mirror of one 0.7.1 already took.

        A note is not matched on its scratchpad's name, because a pad is a container and answering
        with its contents returns notes containing none of the query. The mirror holds: answering with
        a *pad* because one of its notes mentions a word is the same wrong answer inverted, and the
        note itself is already returned in that case.
        """
        found = [h for h in _hits(repo_root, "type picker") if h.record_type == "scratchpad"]

        assert found == [], "a pad answered for a word only its notes carry"


class TestThePadIsTheOnlyTraceLeft:
    def test_a_pad_whose_every_note_was_lifted_is_still_found(self, repo_root: Path) -> None:
        """The case a note-only index cannot answer, and the strongest argument for the kind.

        `_still_a_thought` drops a note once it holds a `model_ref` — the model has an artifact
        standing for the same thought, so returning both offers two results for one thing. A pad whose
        thinking has all been lifted therefore has no searchable notes, and is the only record that
        the thinking ever happened.
        """
        _write(
            repo_root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml",
            _pad(notes="""\
notes:
- id: n1
  title: Contributors stall at the first type picker
  body: A thought that became an outcome.
  destination: element
  element-type: outcome
  model-ref:
    artifact-id: OUT@1780000000.aaaaaa.lowered-barrier
    kind: realized
"""),
        )

        hits = _hits(repo_root, "Q3 platform thinking")

        assert all(h.record_type != "scratchpad-note" for h in hits), "the lifted note is not returned"
        assert [h.record.artifact_id for h in hits if h.record_type == "scratchpad"] == [_PAD_ID]

    def test_a_pad_with_no_notes_at_all_is_still_found(self, repo_root: Path) -> None:
        _write(
            repo_root / "scratchpads" / "platform-core" / f"{_PAD_ID}.scratchpad.yaml",
            _pad(notes="notes: []\n"),
        )

        found = [h for h in _hits(repo_root, "Q3 platform thinking") if h.record_type == "scratchpad"]

        assert [h.record.artifact_id for h in found] == [_PAD_ID]


class TestSubordinationIsUnchangedForSimilarity:
    def test_a_pad_matching_only_on_similarity_is_drawn_after_model_content(self, repo_root: Path) -> None:
        """The condition the kind is admitted under. A pad reached because it happens to share a word
        is still preliminary; only naming it lifts it."""
        _write(
            repo_root / "scratchpads" / "platform-core" / f"{_OTHER_PAD_ID}.scratchpad.yaml",
            _pad(artifact_id=_OTHER_PAD_ID, name="Chameleon onboarding",
                 description="Thinking about how new tenants arrive.", notes="notes: []\n"),
        )
        for index in range(4):
            _write(
                repo_root / "model" / "motivation" / f"OUT@178000000{index}.aaaaaa.tenant-{index}.md",
                _entity(f"OUT@178000000{index}.aaaaaa.tenant-{index}", f"Tenant arrival {index}"),
            )

        kinds = [h.record_type for h in _hits(repo_root, "tenants arrive")]

        assert "scratchpad" in kinds
        assert kinds.index("scratchpad") == len(kinds) - 1, "a pad matched on similarity came early"


class TestTheSurfacesThatDoNotOfferPads:
    def test_a_pad_is_not_offered_as_something_to_reference(self, repo_root: Path) -> None:
        """A pad is a container. Offering one where an entity is wanted is an obvious wrong answer,
        and the picker already turns notes off by name for the same reason."""
        hits = _hits(repo_root, "Q3 platform thinking", include_scratchpads=False)

        assert all(h.record_type != "scratchpad" for h in hits)
