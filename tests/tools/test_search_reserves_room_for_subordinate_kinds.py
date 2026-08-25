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

from src.application.artifacts._ranking import rank_balanced as _rank_balanced
from src.domain.ontology_representation.artifact_types import (
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
)


def _entity(n: int) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}", artifact_type="application-component", name=f"entity {n}",
        version="0.1.0", status="active", domain="application", subdomain="", path=Path("e.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label=f"entity {n}",
        display_alias=f"APP{n}",
    )


def _diagram(n: int) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=f"ARC@{n}", artifact_type="diagram", name=f"diagram {n}",
        diagram_type="archimate-layered", version="0.1.0", status="draft", path=Path("d.puml"),
        extra={},
    )


def _document(n: int) -> DocumentRecord:
    return DocumentRecord(
        artifact_id=f"ADR@{n}", doc_type="adr", title=f"document {n}", status="draft",
        path=Path("c.md"), keywords=(), sections=(), content_text="", extra={},
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


def _three_kinds_and_notes(each: int, notes: int, *, note_score: float = 1e-6) -> list:
    """A corpus whose non-subordinate kinds divide some windows exactly and not others — which is
    what decided whether the reservation survived."""
    from src.domain.ontology_representation.artifact_types import SearchHit

    hits = [SearchHit(9.0 - i * 0.01, "entity", _entity(i)) for i in range(each)]
    hits += [SearchHit(8.0 - i * 0.01, "diagram", _diagram(i)) for i in range(each)]
    hits += [SearchHit(7.0 - i * 0.01, "document", _document(i)) for i in range(each)]
    hits += [SearchHit(note_score, "scratchpad-note", _note(i)) for i in range(notes)]
    return hits


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


class TestTheReservationSurvivesTheRoundRobin:
    """The floor was reserved and then thrown away, for every window the kind count divides.

    `_rank_balanced` draws one hit per non-subordinate kind per pass, so it extends in batches and
    overshoots `limit - reserved` whenever the kinds do not divide it. The guard that followed —
    `(ranked + subordinate)[:limit] if len(ranked) < limit else ranked[:limit]` — then saw a window
    already full and dropped the reserved slots.

    A window of twenty survived on arithmetic alone: three kinds reach eighteen and stop short of
    eighteen, so the tail was appended. Twelve reaches exactly twelve, so it was not, and the
    navigation dropdown — which asks for twenty and shows twelve — could never display a note
    however well it matched. Parametrised over the windows either side of every multiple, because
    one lucky window is what hid this.
    """

    @pytest.mark.parametrize("limit", [10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 24, 30])
    def test_a_window_of_ten_or_more_keeps_room_for_a_note(self, limit: int) -> None:
        ranked = _rank_balanced(_three_kinds_and_notes(40, 3), limit, None)

        assert len(ranked) == limit, "the window is still filled"
        assert "scratchpad-note" in _kinds(ranked), f"a window of {limit} reserved no room for a note"

    @pytest.mark.parametrize("limit", [1, 2, 5, 9])
    def test_a_small_window_still_belongs_to_model_content(self, limit: int) -> None:
        """The other half of the trade: below ten slots nothing is reserved, so a note cannot take
        a share of a window that small."""
        ranked = _rank_balanced(_hits(40, 3), limit, None)

        assert _kinds(ranked) == ["entity"] * limit

    def test_a_note_never_outranks_model_content_in_the_window_it_is_kept_in(self) -> None:
        """The reservation moves a note *into* the window; it must not move it up the order."""
        ranked = _rank_balanced(_three_kinds_and_notes(40, 1, note_score=99.0), 12, None)

        assert ranked[-1].record_type == "scratchpad-note", "a note is drawn last, whatever it scored"
        assert all(h.record_type != "scratchpad-note" for h in ranked[:-1])


class TestTheFloorSurvivesAVerbatimPromotion:
    """A title the reader typed exactly is promoted above the balanced ranking entirely, so the
    ranking sees a smaller window and fewer hits. The floor is computed against *that* window.

    The interaction to get wrong is double-counting: a note promoted for naming itself must not also
    consume the slot reserved for the notes that were not. It cannot, because it is no longer among
    the hits the balanced ranking is given — but the arithmetic is asserted here rather than argued,
    since the first version of this reservation was correct for four window sizes out of twelve.
    """

    @pytest.mark.parametrize("limit", [11, 12, 13, 14, 15, 18, 19, 20, 21, 24, 30])
    def test_a_promoted_note_does_not_spend_the_reservation(self, limit: int) -> None:
        from src.application.artifacts._ranking import rank_hits
        from src.domain.ontology_representation.artifact_types import SearchHit

        hits = _three_kinds_and_notes(40, 3)
        hits.append(SearchHit(1.0, "scratchpad-note", _note(99)))

        ranked = rank_hits(hits, "note 99", limit, None)

        assert len(ranked) == limit, "the window is still filled"
        assert ranked[0].record.artifact_id == "SCR@1.pad#note/n99", "the named note leads"
        assert _kinds(ranked).count("scratchpad-note") >= 2, "the other notes keep their floor"

    def test_a_promotion_can_take_the_window_below_the_floor_threshold(self) -> None:
        """The boundary, asserted rather than discovered: at a window of ten a promotion leaves nine,
        and nine is below the size at which a slot is reserved at all.

        That is the floor rule working, not a defect — reserving in a nine-slot window is the trade
        the subordination exists to refuse, and the reader has already been given the note they named.
        Stated here so the next reader of these numbers does not read the absence as starvation.
        """
        from src.application.artifacts._ranking import rank_hits
        from src.domain.ontology_representation.artifact_types import SearchHit

        hits = _three_kinds_and_notes(40, 3)
        hits.append(SearchHit(1.0, "scratchpad-note", _note(99)))

        ranked = rank_hits(hits, "note 99", 10, None)

        assert ranked[0].record.artifact_id == "SCR@1.pad#note/n99"
        assert _kinds(ranked).count("scratchpad-note") == 1

    @pytest.mark.parametrize("limit", [1, 2, 5, 9])
    def test_a_promotion_reaches_a_window_too_small_for_the_floor(self, limit: int) -> None:
        """Below ten slots nothing is reserved — but a title the reader typed is not a reservation,
        and it is drawn even into a window of one."""
        from src.application.artifacts._ranking import rank_hits
        from src.domain.ontology_representation.artifact_types import SearchHit

        hits = _three_kinds_and_notes(40, 3)
        hits.append(SearchHit(1.0, "scratchpad-note", _note(99)))

        ranked = rank_hits(hits, "note 99", limit, None)

        assert ranked[0].record.artifact_id == "SCR@1.pad#note/n99"
        assert len(ranked) == limit
