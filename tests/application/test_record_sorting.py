"""Browse ordering runs over the whole filtered population, before the page slice.

The interesting cases are the ones a naive `sorted(..., reverse=True)` gets wrong: records
with no stamp at all (a reversed sort must not lead with a column of blanks) and a field name
the client no longer recognises (a bookmarked URL should still return a usable list).
"""

from __future__ import annotations

from pathlib import Path

from src.application.record_sorting import ENTITY_SORT_FIELDS, sort_entity_records
from src.domain.ontology_representation.artifact_types import EntityRecord


def _entity(artifact_id: str, *, name: str = "", stamp: str | None = None, status: str = "draft") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=name or artifact_id,
        version="0.1.0",
        status=status,
        domain="motivation",
        subdomain="requirement",
        path=Path(f"/repo/model/motivation/requirement/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="",
        display_alias="",
        last_updated=stamp,
    )


_STAMPED = [
    _entity("REQ@1.a.old", stamp="2026-01-01T00:00:00Z"),
    _entity("REQ@1.b.new", stamp="2026-07-24T09:15:00Z"),
    _entity("REQ@1.c.unstamped"),
    _entity("REQ@1.d.middle", stamp="2026-04-01T00:00:00Z"),
]


def _ids(records) -> list[str]:
    return [r.artifact_id for r in records]


def test_ascending_last_modified_puts_the_oldest_first() -> None:
    ordered = sort_entity_records(_STAMPED, "last_updated", "asc")
    assert _ids(ordered) == ["REQ@1.a.old", "REQ@1.d.middle", "REQ@1.b.new", "REQ@1.c.unstamped"]


def test_descending_last_modified_puts_the_newest_first() -> None:
    ordered = sort_entity_records(_STAMPED, "last_updated", "desc")
    assert _ids(ordered) == ["REQ@1.b.new", "REQ@1.d.middle", "REQ@1.a.old", "REQ@1.c.unstamped"]


def test_unstamped_records_sort_last_in_both_directions() -> None:
    for order in ("asc", "desc"):
        assert _ids(sort_entity_records(_STAMPED, "last_updated", order))[-1] == "REQ@1.c.unstamped"


def test_a_mixed_date_and_datetime_population_still_orders_chronologically() -> None:
    # Until every repo has run the upgrade, both shapes coexist in one list.
    mixed = [
        _entity("REQ@1.a.same-day-datetime", stamp="2026-07-24T09:15:00Z"),
        _entity("REQ@1.b.same-day-date", stamp="2026-07-24"),
        _entity("REQ@1.c.day-before", stamp="2026-07-23"),
    ]
    assert _ids(sort_entity_records(mixed, "last_updated", "asc")) == [
        "REQ@1.c.day-before",
        "REQ@1.b.same-day-date",
        "REQ@1.a.same-day-datetime",
    ]


def test_name_sort_is_case_insensitive() -> None:
    records = [_entity("REQ@1.a.x", name="zebra"), _entity("REQ@1.b.y", name="Apple")]
    assert _ids(sort_entity_records(records, "name", "asc")) == ["REQ@1.b.y", "REQ@1.a.x"]


def test_type_is_accepted_as_the_browse_column_name() -> None:
    assert "type" in ENTITY_SORT_FIELDS
    assert "artifact_type" in ENTITY_SORT_FIELDS


def test_unknown_field_leaves_the_repository_order_untouched() -> None:
    assert _ids(sort_entity_records(_STAMPED, "conn_total", "desc")) == _ids(_STAMPED)


def test_no_sort_leaves_the_repository_order_untouched() -> None:
    assert _ids(sort_entity_records(_STAMPED, None)) == _ids(_STAMPED)


def test_equal_values_tie_break_deterministically_on_id() -> None:
    tied = [
        _entity("REQ@1.b.second", stamp="2026-07-24T09:15:00Z"),
        _entity("REQ@1.a.first", stamp="2026-07-24T09:15:00Z"),
    ]
    assert _ids(sort_entity_records(tied, "last_updated", "asc")) == ["REQ@1.a.first", "REQ@1.b.second"]


def test_sorting_never_drops_or_duplicates_a_record() -> None:
    for field in sorted(ENTITY_SORT_FIELDS):
        for order in ("asc", "desc"):
            ordered = sort_entity_records(_STAMPED, field, order)
            assert sorted(_ids(ordered)) == sorted(_ids(_STAMPED))
