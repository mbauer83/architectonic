"""How search hits are ordered once they have been found.

Its own module because finding and ordering are different questions and `_search.py` had reached the
source-length policy's hard limit answering both. What is here is the whole of the ordering decision.

**Two sections, and the first runs across artifact kinds.**

1. **The title matches what was typed**, in the tiers `title_match` declares: the title is the query,
   begins with it, has a word beginning with each typed word, or contains it. Closest tier first; the
   reader named the thing, or is part way through naming it, so it leads — whatever kind it is.
2. **Everything else, by score**, with the kinds interleaved: model content, diagrams and documents
   together, then scratchpads, then — when they become searchable — viewpoints.

**Why the first cannot be a score.** Per-table bm25, the token-match supplement and rank fusion
produce numbers on scales that say nothing about each other, so there is no common axis on which
"this title is exactly what you typed" could be worth *n* points. Inventing one undoes the reason the
round-robin in section 2 exists. What crosses the scales is a **statement about the title**, computed
identically for every kind — and that is what the tiers are. It is also why the vector branch cannot
push a title the reader is typing out of the window: fusion re-scores, and a score never outranks a
tier.

**Why subordination lives in section 2 only.** A scratchpad is preliminary and an entity is a
commitment, so a pad never pushes model content down a list it reached *on similarity*. But an
artifact whose title someone typed is not a half-formed thought, whatever kind it is: it is the thing
they asked for by name. Holding it back would make a scratchpad unfindable by its own title, which is
the defect the tiers exist to fix. So the tiers are kind-blind and section 2 subordinates.

**A preference reorders kinds wherever kinds are interleaved.** `prefer_record_type` applies to every
tier as well as to the scored section. Applying it to the scored section alone silently disabled it
for any query some title matched — the preference decided the head of a list whose head was already
spoken for. It still cannot lift a subordinate kind, which is what subordination means.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from src.application.artifacts.title_match import TitleMatch, normalised_terms, title_match
from src.domain.ontology_representation.artifact_types import SearchHit
from src.domain.search_records import (
    RECORD_TYPE_ORDER,
    SUBORDINATE_RECORD_ORDER,
    SUBORDINATE_RECORD_TYPES,
    record_title,
)

#: Below this many slots a window is too small to give one away — see `subordinate_floor`.
_FLOOR_MIN_WINDOW = 10


def _title_tier(hit: SearchHit, query_terms: tuple[str, ...]) -> TitleMatch | None:
    """How closely this hit's title matches the query — see `title_match` for the tiers."""
    title = record_title(hit.record)
    return title_match(normalised_terms(title) if title is not None else None, query_terms)


#: A sort key within one title tier: two numbers, then the artifact id for a stable tie.
WithinTierKey = tuple[float, float, str]


def strongest_first(hit: SearchHit) -> WithinTierKey:
    """By score; the artifact id is the final key so a tie is stable rather than incidental — two hits
    with the same score came from the same scorer on the same evidence, and which of them a reader sees
    first should not depend on dictionary order."""
    return (-hit.score, 0.0, hit.record.artifact_id)


def shortest_title_first(hit: SearchHit) -> WithinTierKey:
    """By title length, then score: among titles that only *contain* what was typed, the shorter one
    is more nearly what was typed — `Repository` before `Repository Write Coordination Service` — and a
    common word no longer leaves a short title behind longer ones that score higher on their bodies."""
    title = record_title(hit.record)
    return (float(len(title)) if title is not None else float("inf"), -hit.score, hit.record.artifact_id)


def by_kind(
    hits: Sequence[SearchHit], order_key: Callable[[SearchHit], WithinTierKey] = strongest_first
) -> dict[str, list[SearchHit]]:
    """Hits grouped by record type, each group ordered by `order_key` (strongest first by default)."""
    grouped: dict[str, list[SearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.record_type, []).append(hit)
    for group in grouped.values():
        group.sort(key=order_key)
    return grouped


def preferred_first(order: Sequence[str], prefer_rt: str | None) -> list[str]:
    """``order`` with the caller's preferred kind moved to the front, where that is permitted.

    A preference cannot lift a subordinate kind: that is what subordination means, and a caller
    asking for scratchpads gets them where they belong rather than ahead of committed content.
    """
    if prefer_rt is None or prefer_rt in SUBORDINATE_RECORD_TYPES or prefer_rt not in order:
        return list(order)
    return [prefer_rt, *(rt for rt in order if rt != prefer_rt)]


def round_robin(grouped: dict[str, list[SearchHit]], order: Sequence[str], limit: int) -> list[SearchHit]:
    """One hit per kind per pass, in ``order``, until the window is full or the kinds run dry.

    Shared by the verbatim promotion and the balanced ranking, which differ only in the order they
    pass: the promotion passes the declared kind sequence, because its members are equal on the one
    thing it asserts; the balanced ranking passes the kinds ranked by their strongest hit.
    """
    drawn: list[SearchHit] = []
    rank = 0
    while len(drawn) < limit:
        this_pass = [grouped[rt][rank] for rt in order if rt in grouped and rank < len(grouped[rt])]
        if not this_pass:
            break
        drawn.extend(this_pass)
        rank += 1
    return drawn[:limit]


def subordinate_floor(limit: int, available: int) -> int:
    """How many of the window's slots the subordinate kinds may not be starved out of.

    They are drawn last and that does not change: the condition they were admitted under is that a
    note never outranks model content. But that is a statement about *order*, and being kept out of
    the window is a different thing — it made a scratchpad unfindable by its own title, because any
    query model content also matches filled twenty slots before the notes were reached.

    The floor only applies where the window can afford it. A window of four belongs to committed
    content, and spending a quarter of it on a half-formed thought is the trade the subordination
    exists to refuse — so below ten slots nothing is reserved at all.
    """
    if available <= 0 or limit < _FLOOR_MIN_WINDOW:
        return 0
    return min(available, max(1, limit // 10))


def rank_balanced(hits: Sequence[SearchHit], limit: int, prefer_rt: str | None) -> list[SearchHit]:
    """Section 2: fair representation across record kinds, subordinate kinds last.

    Rank within each kind by its own score, then round-robin across kinds — ordering the kinds by
    their strongest hit, the preferred kind first — so every matching kind stays visible. A single
    global sort would let a high-volume kind crowd the minority kinds out of the window entirely,
    and the scales do not permit one anyway.

    ``SUBORDINATE_RECORD_TYPES`` do not take part in that round-robin: they fill whatever slots are
    left once every other kind has had its turn, in the order the vocabulary declares them. A
    round-robin would honour "never outranks model content" only against the *first* hit of each
    other kind, and would still put a scratchpad above the second entity.
    """
    grouped = by_kind(hits)
    # Kinds whose strongest hits tie are met in the declared order, not in the order `search`
    # collected them: that walks a set of kind names, whose iteration follows string hashing, so the
    # same query could rank two kinds either way round depending on the process (an empty query,
    # which scores everything equally, did under 2 of 151 hash seeds).
    scored_order = sorted(
        grouped, key=lambda rt: (-grouped[rt][0].score, RECORD_TYPE_ORDER.index(rt)),
    )
    order = preferred_first(scored_order, prefer_rt)
    subordinate = [h for rt in SUBORDINATE_RECORD_ORDER for h in grouped.get(rt, [])]
    reserved = subordinate_floor(limit, len(subordinate))
    ranked = round_robin(
        {rt: group for rt, group in grouped.items() if rt not in SUBORDINATE_RECORD_TYPES},
        [rt for rt in order if rt not in SUBORDINATE_RECORD_TYPES],
        max(limit - reserved, 0),
    )
    # Trimmed to the reservation before the tail is appended. The round-robin draws one hit per kind
    # per pass, so it extends in batches and overshoots `limit - reserved` whenever the kind count
    # does not divide it — and the guard this replaces (`if len(ranked) < limit`) then saw a full
    # window and dropped the reserved slots on the floor. A window of twenty survived on arithmetic
    # alone: three kinds reach eighteen and stop short. Twelve reached exactly twelve, so the floor
    # was silently spent and a note was unreachable in any dropdown that asked for one.
    return (ranked[: limit - reserved] + subordinate)[:limit]


#: How each tier orders its own hits. Where the title *is*, or *begins with*, what was typed, the
#: scorers' evidence decides; where it only contains the typed words, the shorter title does.
_WITHIN_TIER: dict[TitleMatch, Callable[[SearchHit], WithinTierKey]] = {
    TitleMatch.EXACT: strongest_first,
    TitleMatch.PREFIX: strongest_first,
    TitleMatch.WORD_PREFIXES: shortest_title_first,
    TitleMatch.INFIX: shortest_title_first,
}


def rank_hits(hits: Sequence[SearchHit], query: str, limit: int, prefer_rt: str | None) -> list[SearchHit]:
    """The whole ordering: the title tiers closest first, then everything else by score."""
    query_terms = normalised_terms(query)
    tiers: dict[TitleMatch, list[SearchHit]] = {tier: [] for tier in TitleMatch}
    rest: list[SearchHit] = []
    for hit in hits:
        tier = _title_tier(hit, query_terms)
        (rest if tier is None else tiers[tier]).append(hit)
    order = preferred_first(RECORD_TYPE_ORDER, prefer_rt)
    ranked: list[SearchHit] = []
    for tier in TitleMatch:
        if len(ranked) >= limit:
            return ranked[:limit]
        ranked.extend(round_robin(by_kind(tiers[tier], _WITHIN_TIER[tier]), order, limit - len(ranked)))
    return (ranked + rank_balanced(rest, max(limit - len(ranked), 0), prefer_rt))[:limit]
