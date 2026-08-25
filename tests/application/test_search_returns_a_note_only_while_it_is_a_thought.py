"""What a note is searchable by, and until when.

Two decisions, both corrections of something this release had built the other way round.

**By its own words only.** A pad is a container and its notes are what search can return, so matching
the container's name answers with notes containing none of the query — asking for "Q3 platform
thinking" and receiving a note called "AI-Assisted and Agentic Development". Finding the *pad* is a
different question and needs a pad-shaped result, which a note cannot be.

**Until it has a model counterpart.** Once a note holds a `model_ref` the aggregate calls it an
element — `invariants.py` refuses the reference unless the note's destination is `element` — so a model
artifact stands for the same thought and returning both answers twice. Both kinds go: the flag tells a
lift this pad performed from content a user attached, which decides whether untyping is free, not
whether the thought is still the best answer to a query.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.scoring import score_scratchpad_note, tokenize
from src.application.scratchpad.indexing import parse_scratchpad_notes
from src.domain.ontology_representation.artifact_types import ScratchpadNoteRecord

_PAD = "SCR@1786299627.Dnc28yf.q3-platform-thinking"


def _note_record(*, title: str, body: str = "", pad_name: str = "Q3 platform thinking") -> ScratchpadNoteRecord:
    return ScratchpadNoteRecord(
        artifact_id=f"{_PAD}#note/n1", scratchpad_id=_PAD, scratchpad_name=pad_name,
        note_id="n1", title=title, body=body, element_type="", domain="",
        status="draft", path=Path("pad.scratchpad.yaml"), area="unfiled",
    )


def _score(record: ScratchpadNoteRecord, query: str) -> float:
    return score_scratchpad_note(record, query.lower(), tokenize(query.lower()))


class TestANoteIsFoundByItsOwnWords:
    def test_its_own_title_matches(self) -> None:
        assert _score(_note_record(title="Contributors stall at the type picker"), "contributors") > 0

    def test_its_body_matches(self) -> None:
        assert _score(_note_record(title="Untitled", body="contributors stall here"), "contributors") > 0

    def test_its_pads_name_does_not(self) -> None:
        """The correction. Asking for the container must not hand back its contents."""
        record = _note_record(title="AI-Assisted and Agentic Development")

        assert _score(record, "platform thinking") == 0.0

    def test_a_word_shared_by_pad_and_note_still_matches_through_the_note(self) -> None:
        """Withdrawing the pad's name must not cost a note a match it made on its own."""
        record = _note_record(title="Platform adoption blockers")

        assert _score(record, "platform") > 0


def _pad_document(*, notes: list[dict[str, object]]) -> str:
    import yaml

    return yaml.safe_dump({
        "artifact-id": _PAD, "artifact-type": "scratchpad", "name": "Q3 platform thinking",
        "version": "0.1.0", "status": "draft", "meta-ontology": "archimate-4",
        "areas": [{"id": "strategy", "label": "Vision"}],
        "notes": notes,
        "links": [], "layout": {"areas": {"strategy": [0, 0, 800, 400]}, "notes": {}},
    })


class TestALiftedNoteLeavesTheIndex:
    def _records(self, tmp_path: Path, notes: list[dict[str, object]]) -> list[ScratchpadNoteRecord]:
        path = tmp_path / f"{_PAD}.scratchpad.yaml"
        path.write_text(_pad_document(notes=notes), encoding="utf-8")
        return parse_scratchpad_notes(path, group="platform-core")

    def test_an_unlifted_note_is_indexed(self, tmp_path: Path) -> None:
        records = self._records(tmp_path, [{"id": "n1", "title": "Still thinking"}])

        assert [r.title for r in records] == ["Still thinking"]

    def test_a_realized_note_is_not(self, tmp_path: Path) -> None:
        """It became an entity, and the entity is now the answer."""
        records = self._records(tmp_path, [
            {"id": "n1", "title": "Became a requirement",
             "destination": "element", "element-type": "requirement",
             "model-ref": {"artifact-id": "REQ@1.aa.thing", "kind": "realized"}},
        ])

        assert records == []

    def test_a_bound_note_leaves_too(self, tmp_path: Path) -> None:
        """Bound points at content that already existed, but the note is still represented in the
        model — the aggregate calls it an element either way, and one thought should answer once."""
        records = self._records(tmp_path, [
            {"id": "n1", "title": "A thought about an existing thing",
             "destination": "element", "element-type": "requirement",
             "model-ref": {"artifact-id": "REQ@1.aa.thing", "kind": "bound"}},
        ])

        assert records == []

    def test_only_the_lifted_one_leaves(self, tmp_path: Path) -> None:
        records = self._records(tmp_path, [
            {"id": "n1", "title": "Still thinking"},
            {"id": "n2", "title": "Became a requirement",
             "destination": "element", "element-type": "requirement",
             "model-ref": {"artifact-id": "REQ@1.aa.thing", "kind": "realized"}},
            {"id": "n3", "title": "Also still thinking"},
        ])

        assert [r.title for r in records] == ["Still thinking", "Also still thinking"]


@pytest.mark.parametrize("kind", ["realized", "bound"])
def test_a_lifted_note_is_still_readable_on_its_pad(tmp_path: Path, kind: str) -> None:
    """Leaving the index is not deletion. The canvas reads the pad itself, so a lifted note is still
    there to be seen, edited and un-lifted — it has only stopped being a search result."""
    from src.application.scratchpad.document import from_document
    from src.domain.yaml_documents import parse_yaml

    path = tmp_path / f"{_PAD}.scratchpad.yaml"
    path.write_text(_pad_document(notes=[
        {"id": "n1", "title": "Became a requirement", "destination": "element",
         "element-type": "requirement",
         "model-ref": {"artifact-id": "REQ@1.aa.thing", "kind": kind}},
    ]), encoding="utf-8")

    pad = from_document(parse_yaml(path.read_text(encoding="utf-8")))

    assert [note.title for note in pad.notes] == ["Became a requirement"]
