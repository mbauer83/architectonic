"""Ordering of assurance node listings.

The store decides the order, not the exposure filter downstream of it: filtering out
above-ceiling records preserves the relative order of what remains, so ordering first and
filtering second can neither change *which* nodes a reader sees nor reveal how many were
withheld. Ordering after the filter would be equally safe but would have to be re-done by
every caller; doing it in the store also lets the SQL backend use an index.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

SortOrder = Literal["asc", "desc"]

NODE_SORT_COLUMNS: dict[str, str] = {
    "updated_at": "updated_at",
    "created_at": "created_at",
    "name": "name",
    "node_type": "node_type",
}
"""Requestable sort field → node column. The values double as SQL identifiers, so a
request can only ever name a column that exists here."""

NATURAL_NODE_ORDERING: tuple[str, SortOrder] = ("created_at", "asc")
"""What an unspecified or unrecognised sort means: the order nodes were created in. Callers
that analyse a graph rely on this being stable; only a reader-facing listing overrides it."""

MOST_RECENTLY_UPDATED_FIRST: tuple[str, SortOrder] = ("updated_at", "desc")
"""The ordering reader-facing node listings default to — what changed last, first."""


def resolve_node_sort(sort: str | None, order: str | None) -> tuple[str, SortOrder]:
    """Normalize a requested (sort, order) pair to a supported one.

    An unknown field falls back to the natural ordering rather than erroring — a listing is
    a read, and a stale column name in a bookmarked URL should still show the reader their
    nodes.
    """
    column = NODE_SORT_COLUMNS.get(sort or "")
    if column is None:
        return NATURAL_NODE_ORDERING
    direction: SortOrder = "desc" if (order or "").lower() == "desc" else "asc"
    return column, direction


def sorted_node_dicts(
    nodes: Sequence[dict[str, object]],
    sort: str | None,
    order: str | None,
) -> list[dict[str, object]]:
    """Order node records the way the SQL backend's ``ORDER BY`` would.

    For the file- and REST-backed stores, which have no query engine to delegate to.
    """
    column, direction = resolve_node_sort(sort, order)
    # Two stable passes, so equal values always tie-break on node_id ascending — the same
    # total order the SQL backend produces with `ORDER BY <column> <dir>, node_id ASC`.
    ordered = sorted(nodes, key=lambda node: str(node.get("node_id", "")))
    ordered.sort(key=lambda node: str(node.get(column) or "").casefold(), reverse=direction == "desc")
    return ordered
