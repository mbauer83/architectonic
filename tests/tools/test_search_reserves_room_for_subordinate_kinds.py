"""A scratchpad note is drawn last, and is not starved out of the window entirely.

`_rank_balanced` round-robins across record kinds "so every matching kind stays visible", and then
excludes the subordinate kinds from that round-robin: they are appended only if the other kinds left
room. With a window of twenty and any query that model content matches, there is none — so searching a
scratchpad's own title returned twenty entities, documents and diagrams and not one of its notes.

The condition notes were admitted under is that **a note never outranks model content**. That is a
statement about order, and starvation is a different thing: a note kept below everything is not a note
kept out. So the subordinate kinds keep their place at the end and gain a floor.

The floor only exists where the window can afford it. A window of four belongs to committed content —
reserving a slot there would push out a quarter of it for a half-formed thought, which is the trade the
subordination exists to refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts._search import _rank_balanced
from src.domain.ontology_representation.artifact_types import EntityRecord, ScratchpadNoteRecord


def _entity(n: int) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}", artifact_type="application-component", name=f"entity {n}",
        version="0.1.0", status="active", domain="application", subdomain="", path=Path("e.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label=f"entity {n}",
        display_alias=f"APP{n}",
    )


def _note(n: int) -> ScratchpadNoteRecord:
    return ScratchpadNoteRecord(
        artifact_id=f"SCR@1.pad#note/n{n}", scratchpad_id="SCR@1.pad", scratchpad_name="Q3 thinking",
        note_id=f"n{n}", title=f"note {n}", body="", element_type="", domain="",
        status="draft", path=Path("pad.yaml"), area="",
    )


def _hits(entities: int, notes: int) -> list:
    from src.domain.ontology_representation.artifact_types import SearchHit

    return [SearchHit(100.0 - i, "entity", _entity(i)) for i in range(entities)] + [
        SearchHit(1.0, "scratchpad-note", _note(i)) for i in range(notes)
    ]


def _kinds(ranked) -> list[str]:
    return [h.record_type for h in ranked]


class TestTheFloor:
    def test_a_full_window_still_shows_a_note(self) -> None:
        ranked = _rank_balanced(_hits(entities=60, notes=4), 20, None)

        assert "scratchpad-note" in _kinds(ranked), "notes starved out of a full window"

    def test_the_window_is_still_full(self) -> None:
        ranked = _rank_balanced(_hits(entities=60, notes=4), 20, None)

        assert len(ranked) == 20

    def test_notes_come_last(self) -> None:
        """The condition they were admitted under: never above model content."""
        kinds = _kinds(_rank_balanced(_hits(entities=60, notes=4), 20, None))

        first_note = kinds.index("scratchpad-note")
        assert set(kinds[:first_note]) == {"entity"}
        assert set(kinds[first_note:]) == {"scratchpad-note"}

    def test_most_of_the_window_is_still_committed_content(self) -> None:
        kinds = _kinds(_rank_balanced(_hits(entities=60, notes=8), 20, None))

        assert kinds.count("entity") >= 18


class TestWhereTheFloorDoesNotApply:
    @pytest.mark.parametrize("limit", [1, 3, 5, 9])
    def test_a_small_window_belongs_to_committed_content(self, limit: int) -> None:
        """Reserving a slot in a window of four would spend a quarter of it on a half-formed
        thought, which is the trade the subordination exists to refuse."""
        ranked = _rank_balanced(_hits(entities=60, notes=4), limit, None)

        assert _kinds(ranked) == ["entity"] * limit

    def test_a_window_the_other_kinds_do_not_fill_is_unchanged(self) -> None:
        """Nothing is reserved when there is already room — the notes simply follow."""
        ranked = _rank_balanced(_hits(entities=3, notes=2), 20, None)

        assert _kinds(ranked) == ["entity"] * 3 + ["scratchpad-note"] * 2

    def test_no_notes_means_no_reservation(self) -> None:
        ranked = _rank_balanced(_hits(entities=60, notes=0), 20, None)

        assert len(ranked) == 20
        assert set(_kinds(ranked)) == {"entity"}
