"""One page of an analysis's working set, with each node's relationship to it stated.

The working set is authored ∪ participating. A reader of a combined analysis must not lose which
is which — *a borrowed node has to look borrowed* — so every item carries an explicit
``relationship`` rather than leaving the caller to intersect two lists and hope it got the direction
right.

**Exposure filtering runs before the page is built.** Not after: a page assembled from the
unfiltered set and then filtered would return short pages of unpredictable length, and the totals
beside it would count records the reader may not see. `analysis_working_set` filters first, and this
module paginates what it returned — so the cursor walks the visible population and the counts
describe it.

Paging is the house convention: ``{"items": [...], "next_cursor": null}`` with an offset-encoded
cursor, as at `diagrams.py` and `_entity_display_search.py`. Ordering is deterministic and total —
authored before referenced, then by node id — because a cursor over an unstable order silently skips
and repeats rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.assurance.ports import ConfidentialAssuranceStore
from src.application.assurance.working_set import analysis_working_set

#: The house defaults. A maximum exists so one request cannot ask the store for everything.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

Relationship = Literal["authored", "referenced"]


@dataclass(frozen=True)
class WorkingSetItem:
    """One node of the working set, and how this analysis relates to it."""

    node: dict[str, Any]
    relationship: Relationship


@dataclass(frozen=True)
class WorkingSetPage:
    """One page, plus the totals of the *visible* population it was drawn from.

    ``authored_total`` and ``referenced_total`` are role totals over the whole visible working set,
    not over the page — a caller showing "12 authored, 3 borrowed" is describing the analysis, and a
    per-page count would change as they scrolled.
    """

    items: list[WorkingSetItem]
    next_cursor: str | None
    authored_total: int
    referenced_total: int


def effective_limit(requested: int | None) -> int:
    """The page size, clamped. A request for none or for absurdly many gets a sane page."""
    if requested is None:
        return DEFAULT_LIMIT
    return max(1, min(requested, MAX_LIMIT))


def _offset(cursor: str | None) -> int:
    """The cursor's offset. An unreadable cursor starts at the beginning rather than failing.

    A cursor is an opaque continuation token the server issued; a client that hands back something
    else has no page to resume, and refusing would turn a stale bookmark into an error the user
    cannot act on.
    """
    return int(cursor) if cursor and cursor.isdigit() else 0


def analysis_working_set_page(
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    analysis_id: str,
    *,
    relationship: Relationship | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> WorkingSetPage:
    """One page of what ``analysis_id`` reasons over, filtered before it is paginated.

    ``relationship`` narrows to one role. It is a filter over the collection, not a second
    resource: "the nodes this analysis authored" and "the nodes it borrowed" are two readings of one
    working set, and giving each its own path would put the same rows at two addresses.
    """
    working_set = analysis_working_set(store, policy, analysis_id)
    authored = working_set.authored_node_ids

    items = [
        WorkingSetItem(
            node=node,
            relationship="authored" if str(node.get("node_id", "")) in authored else "referenced",
        )
        for node in working_set.nodes
    ]
    # Deterministic and total: authored first, then by node id. A cursor over an order that ties
    # would skip and repeat rows between pages, invisibly.
    items.sort(key=lambda item: (item.relationship != "authored", str(item.node.get("node_id", ""))))

    authored_total = sum(1 for item in items if item.relationship == "authored")
    referenced_total = len(items) - authored_total

    if relationship is not None:
        items = [item for item in items if item.relationship == relationship]

    size = effective_limit(limit)
    start = _offset(cursor)
    page = items[start : start + size]
    next_cursor = str(start + size) if start + size < len(items) else None
    return WorkingSetPage(
        items=page,
        next_cursor=next_cursor,
        authored_total=authored_total,
        referenced_total=referenced_total,
    )
