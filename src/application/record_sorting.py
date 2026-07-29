"""Server-side ordering of browsable artifact records.

Browse lists are paginated, so the order has to be decided over the *whole* filtered
population before the page slice — a client-side sort of one page would silently reorder
50 of 500 rows and read as if it had ordered everything.

Only fields the record itself carries are sortable here. Derived, page-scoped columns (a
connection count computed after the slice) are deliberately not in the allow-list: the
caller sorts those itself and says so in its UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from src.domain.ontology_representation.artifact_types import EntityRecord

SortOrder = Literal["asc", "desc"]

_ENTITY_SORT_ATTRS: dict[str, str] = {
    "name": "name",
    "type": "artifact_type",
    "artifact_type": "artifact_type",
    "status": "status",
    "domain": "domain",
    "last_updated": "last_updated",
}
"""Requestable sort field → `EntityRecord` attribute. `type` is accepted alongside the
serialized name `artifact_type` because that is the browse column's label."""

ENTITY_SORT_FIELDS = frozenset(_ENTITY_SORT_ATTRS)


def sort_entity_records(
    records: Sequence[EntityRecord],
    sort: str | None,
    order: str | None = "asc",
) -> list[EntityRecord]:
    """Order *records* by a native field, newest-first when *order* is ``desc``.

    An unknown or absent *sort* leaves the repository's natural order untouched (a browse
    request with a stale column name still returns a usable list rather than an error).
    Records missing the field entirely — no `last-updated` stamp, for instance — sort
    **last in both directions**: "unknown" is not "oldest", and a reversed sort should not
    lead with a column of blanks.
    """
    attribute = _ENTITY_SORT_ATTRS.get(sort or "")
    if attribute is None:
        return list(records)

    descending = (order or "asc").lower() == "desc"
    present = [r for r in records if getattr(r, attribute) is not None]
    missing = [r for r in records if getattr(r, attribute) is None]

    def key(record: EntityRecord) -> tuple[str, str]:
        return (str(getattr(record, attribute)).casefold(), record.artifact_id)

    return [*sorted(present, key=key, reverse=descending), *missing]
