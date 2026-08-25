"""How search hits are ordered once they have been found.

Its own module because finding and ordering are different questions and `_search.py` had reached the
source-length policy's hard limit answering both. What is here is the whole of the ordering decision:
the verbatim-title promotion, the per-kind round-robin, the subordinate tail and its floor.

**Why ordering cannot be a score.** Per-table bm25 and the token-match supplement produce numbers on
scales that say nothing about each other, so there is no common axis on which "this title is exactly
what you typed" could be worth *n* points. Inventing one undoes the reason the round-robin exists.
What can cross the scales is a **boolean**, computed identically for every kind — and that is what
the promotion below is.

**Two strengths of title evidence, and they earn different treatment.**

*The title is exactly the query* is unambiguous: the reader named the thing. It is promoted above
everything, kind-blind, and subordination does not apply to it — an artifact whose title someone
typed exactly is not a half-formed thought, whatever kind it is. That is what makes a scratchpad
findable by its own name.

*Every query term appears in the title* is much weaker, and measurement is what settled how weak. For
a single-word query it degenerates to "the word is in the title", which 66 entity titles satisfy for
`assurance` on the live repository. Promoting that above everything would have handed a whole class
of query to whichever kinds happened to match, and would have suspended two guarantees this project
already paid for: that a note never outranks model content on similarity alone, and that a caller's
`prefer_record_type` decides the head of the list. So it ranks hits **within** their kind, where it
means "a title match beats a body match" and nothing more.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.artifacts.scoring import tokenize
from src.domain.ontology_representation.artifact_types import SearchHit
from src.domain.search_records import RECORD_TYPE_ORDER, SUBORDINATE_RECORD_TYPES, record_title

#: Below this many slots a window is too small to give one away — see `subordinate_floor`.
_FLOOR_MIN_WINDOW = 10


def normalised_terms(text: str) -> tuple[str, ...]:
    """A title or a query as comparable terms.

    Through `tokenize`, which the scored path already uses, so the two cannot disagree about what a
    word is. Casefolding and punctuation fall out of it: `"Sketch, before naming a TYPE!"` and
    `"sketch before naming a type"` normalise alike.
    """
    return tuple(tokenize(text.lower()))


def _title_terms(hit: SearchHit) -> tuple[str, ...] | None:
    """This hit's title as terms, or `None` where the record has no title.

    `record_title` answers `None` rather than `""` for a connection, and that matters here: an empty
    query would otherwise "equal" an empty title and promote every connection in the corpus.
    """
    title = record_title(hit.record)
    return normalised_terms(title) if title is not None else None


def names_exactly(hit: SearchHit, query_terms: tuple[str, ...]) -> bool:
    """Whether the reader typed this record's title."""
    return bool(query_terms) and _title_terms(hit) == query_terms


def carries_every_term(hit: SearchHit, query_terms: tuple[str, ...]) -> bool:
    """Whether every query term appears in this record's title.

    Deliberately **not** using `expand_tokens`. The scored path expands synonyms — `diagram` and
    `view` stand in for each other — and this predicate's value is that it can be explained in one
    sentence: *you typed these words and all of them are in the title*. A synonym makes that sentence
    false. The cost is that a plural or an inflection misses; recorded rather than smoothed over,
    because prefix matching in one direction is the smallest widening that keeps the sentence, and
    stemming is not.
    """
    terms = _title_terms(hit)
    return bool(query_terms) and terms is not None and all(term in terms for term in query_terms)


def by_kind(hits: Sequence[SearchHit], query_terms: tuple[str, ...] = ()) -> dict[str, list[SearchHit]]:
    """Hits grouped by record type, each group in the order that kind should be drawn.

    A title carrying every query term sorts above one that matched only in its body, and score
    decides the rest. The artifact id is the final key so a tie is stable rather than incidental —
    two hits with the same score came from the same scorer on the same evidence, and which of them
    a reader sees first should not depend on dictionary order.
    """
    grouped: dict[str, list[SearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.record_type, []).append(hit)
    for group in grouped.values():
        group.sort(key=lambda h: (not carries_every_term(h, query_terms), -h.score, h.record.artifact_id))
    return grouped


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


def rank_balanced(
    hits: Sequence[SearchHit], limit: int, prefer_rt: str | None, query_terms: tuple[str, ...] = ()
) -> list[SearchHit]:
    """Select up to ``limit`` hits with fair representation across record kinds.

    Rank within each kind by that kind's own evidence, then round-robin across kinds — ordering the
    kinds by their strongest hit, ``prefer_rt`` first — so every matching kind stays visible. A
    single global sort would let a high-volume kind crowd the minority kinds out of the window
    entirely, and the scales do not permit one anyway.

    ``SUBORDINATE_RECORD_TYPES`` do not take part in the round-robin at all: they fill whatever slots
    are left once every other kind has had its turn. A scratchpad note is a half-formed thought and
    an entity is a commitment, and "never outranks model content, documents or diagrams" was the
    condition notes were allowed into the index under — a round-robin honours it only against the
    *first* hit of each other kind, and would still put a note above the second entity. A preference
    cannot lift them either.
    """
    grouped = by_kind(hits, query_terms)
    order = sorted(grouped, key=lambda rt: grouped[rt][0].score, reverse=True)
    if prefer_rt in grouped and prefer_rt not in SUBORDINATE_RECORD_TYPES:
        order = [prefer_rt, *(rt for rt in order if rt != prefer_rt)]
    subordinate = sorted(
        (h for rt in order if rt in SUBORDINATE_RECORD_TYPES for h in grouped[rt]),
        key=lambda h: (not carries_every_term(h, query_terms), -h.score, h.record.artifact_id),
    )
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


def rank_hits(hits: Sequence[SearchHit], query: str, limit: int, prefer_rt: str | None) -> list[SearchHit]:
    """The whole ordering: titles the reader typed, then the balanced ranking over the rest."""
    query_terms = normalised_terms(query)
    named, rest = [], []
    for hit in hits:
        (named if names_exactly(hit, query_terms) else rest).append(hit)
    promoted = round_robin(by_kind(named, query_terms), RECORD_TYPE_ORDER, limit)
    return (promoted + rank_balanced(rest, max(limit - len(promoted), 0), prefer_rt, query_terms))[:limit]
