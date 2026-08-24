"""Merging two repository roots keeps every searchable record kind.

`merge_search_rows` interleaves the engagement and enterprise FTS rows by iterating a tuple of record
types and keeping the rows whose type it names. The tuple listed four and the vocabulary has five:
`scratchpad-note` was absent, so **every note row was dropped whenever both roots were merged** — which
is what the served backend always does.

The effect was not "no notes": `search` runs its scored supplement for any kind with zero FTS hits, and
notes always had zero, so they arrived by the supplement every time. That path scores a note's own title
and body and never its scratchpad's name, so a note was findable by its own words and a scratchpad was
not findable by its title at all. Two symptoms, one omitted tuple entry, and the FTS weights for notes
were never consulted in the product at all.

So the order is derived from the vocabulary instead of restated beside it. A hand-kept second list of
the record types is what drifted, and deriving it means a sixth kind cannot be silently dropped.
"""

from __future__ import annotations

from src.domain.ontology_representation.artifact_types import KIND_TO_RECORD_TYPE
from src.infrastructure.artifact_index._combined_support import _RECORD_TYPE_ORDER, merge_search_rows


def test_the_merge_order_covers_every_searchable_record_type() -> None:
    assert set(_RECORD_TYPE_ORDER) == set(KIND_TO_RECORD_TYPE.values()), (
        "the merge iterates a record-type list that differs from the vocabulary; any type it omits "
        "is dropped from every combined-root search"
    )


def test_it_names_each_type_once() -> None:
    assert len(_RECORD_TYPE_ORDER) == len(set(_RECORD_TYPE_ORDER))


class TestNoKindIsDropped:
    def _rows(self, record_type: str) -> list[tuple[str, str, float]]:
        return [(f"{record_type}@1", record_type, 5.0), (f"{record_type}@2", record_type, 4.0)]

    def test_a_row_of_every_kind_survives_the_merge(self) -> None:
        left = [row for rt in KIND_TO_RECORD_TYPE.values() for row in self._rows(rt)[:1]]
        right = [row for rt in KIND_TO_RECORD_TYPE.values() for row in self._rows(rt)[1:]]

        merged = merge_search_rows(left, right, limit=50)

        assert {row[1] for row in merged} == set(KIND_TO_RECORD_TYPE.values())

    def test_a_scratchpad_note_from_one_root_survives(self) -> None:
        """The case that was lost, stated on its own so a regression names itself."""
        note = ("SCR@1.pad#note/n1", "scratchpad-note", 3.0)

        merged = merge_search_rows([("APP@1", "entity", 9.0)], [note], limit=10)

        assert note in merged

    def test_an_unknown_record_type_is_still_dropped(self) -> None:
        """The tuple is a filter as well as an order, and that is deliberate: a row whose type the
        vocabulary does not know has no reader downstream."""
        merged = merge_search_rows([("X@1", "not-a-record-type", 9.0)], [], limit=10)

        assert merged == []
