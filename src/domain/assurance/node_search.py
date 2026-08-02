"""What it means for an assurance node to match a search, and which match comes first.

A domain rule, not a storage detail, and it was implemented four times. Three stores — private-git,
encrypted-private-git, PocketBase — carried the same byte-identical in-memory filter: substring, case
insensitive, over ``name`` then ``content_text``, first ``limit`` hits in list order. The SQLCipher store
expressed it in SQL and added something the other three do not have::

    ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, created_at

So the four backends did not agree on what `search_nodes` answers. Same query, same content, different
order: a node whose *name* matches ranks above one that merely mentions the term — which is the useful
behaviour, and the one three of four backends silently lacked. Nothing was broken enough to fail; the
answer was just quietly worse depending on where the store happened to be.

Clone detection would have found the three identical copies and reported them as tidy-up. What it could
not see is the fourth, which is not a copy at all and is the one that was right. Tracing the concern
end to end is what finds that, which is the lesson this module exists to embody as much as to fix.

**The SQL stays SQL.** A store that can filter and rank in the database must, or `search_nodes` becomes
"load every node into memory first". What is shared is therefore the *rule*, expressed twice by
necessity — and `tests/domain/test_node_search_ranking.py` is what holds the two expressions to the same
answer, because two expressions of one rule is exactly the arrangement that drifts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: The fields a query is matched against, in ranking order: a name match outranks a body match.
#:
#: Ordered rather than a set, because the order *is* the ranking rule. Adding a field here changes what
#: ranks where, which is a decision, and a set would let it be made by accident.
SEARCHED_FIELDS: tuple[str, ...] = ("name", "content_text")


def matches_node(node: Mapping[str, Any], query: str) -> bool:
    """Whether this node matches at all. Case-insensitive substring, over the searched fields."""
    return _match_rank(node, query) is not None


def rank_node_matches(
    nodes: Iterable[Mapping[str, Any]], query: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """The nodes matching *query*, name matches first, at most *limit* of them.

    Stable within a rank: two name matches keep the order the store listed them in, which for every
    caller is creation order. So the ranking adds a level above the store's ordering rather than
    replacing it — the same shape as the SQL's ``ORDER BY <rank>, created_at``.

    An empty query matches everything, which is what a caller asking for "" is asking for; the previous
    implementations agreed on that by accident of `"" in anything` and it is worth saying on purpose.
    """
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for position, node in enumerate(nodes):
        rank = _match_rank(node, query)
        if rank is not None:
            ranked.append((rank, position, dict(node)))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return [node for _rank, _position, node in ranked[:limit]]


def _match_rank(node: Mapping[str, Any], query: str) -> int | None:
    """Which searched field matched first, or ``None`` for no match. Lower is a better match."""
    needle = query.lower()
    for rank, field in enumerate(SEARCHED_FIELDS):
        if needle in str(node.get(field, "")).lower():
            return rank
    return None
