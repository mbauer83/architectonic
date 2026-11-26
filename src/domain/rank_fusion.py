"""Reciprocal rank fusion: one ordered list from several that do not share a scale.

Two retrievers answer a search — full-text matching and vector similarity — and their scores are not
comparable. `scoring.py` says so about the full-text scales outright ("incomparable scales"), and
`_ranking.py` already works around it: it orders kinds by round-robin *because* "the scales do not
permit" a global sort. So this codebase had already reasoned its way to rank-based fusion;
round-robin is a cruder form of it.

Two, and not the three an earlier draft of this module named. Graph traversal was built as a third
list and measured: at equal weight it takes the labelled summary stratum from 98.3% to 61.7%, because
a structural neighbour of the top hit scores the same `1/(k+1)` the top hit does, and forty
neighbours tie the answer they surround. Damped enough to stop that, it contributes nothing. It may
return, but only with per-list weights and a stratum whose ground truth is not the relation it
walks.

`score(candidate) = Σ over lists of 1 / (k + rank)`, rank starting at 1. A candidate absent from a
list contributes nothing from it. `k` damps the difference between the top ranks: at k=60 the first
and second place differ by about 0.03% of the total, so appearing in *two* lists matters more than
placing highly in one — which is the property fusion is for.

**Agreement can also take a lead away, and one list may be held to it.** Under RRF a candidate
placed second by both lists, `2/(k+2)`, outscores one placed first by one list and sixth by the other,
`1/(k+1) + 1/(k+6)`, at *every* k — the function is convex in rank, so no choice of k restores it.
Measured on the labelled suite (2026-11-26): a summary query's answer, first by keyword and sixth by
vector, fell to third in its kind — behind one second in both and one sixth and first, which tied it
and won on id — while the kind had two slots of the window. No k from 1 to 60 kept it there.
`fuse_keeping_the_lead` names one list whose first place stays first; which list earns that is the
caller's claim, and the caller says why.

**This is not the product's ranking.** `rank_hits` keeps three sections earned by three noticed
failures: an exact name match first whatever it scores, then hits carrying every term, then
round-robin across kinds with a reserved floor for preliminary thinking. Fusion produces the candidate
list that policy then orders. A flat fused sort in its place would discard all of it.

**The tie-break is for determinism, and claims nothing about quality.** Equal fused scores are broken
by the existing kind order and then by id, so the same inputs give the same output on every machine
and every run. A tie-break that preferred, say, whichever candidate placed highest in any single list
would be a claim that doing so ranks better — and quality claims belong to the labelled query suite
that can test them, not to a function that cannot.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.domain.search_records import RECORD_TYPE_ORDER, SearchCandidate

#: The damping constant from the original RRF paper, and what every hybrid-search implementation
#: defaults to. Measured against the labelled suite (2026-11-26, 120/120/76/83 queries over the name,
#: summary, paraphrase and described strata): k from 60 down to 5 moves no stratum by more than one
#: query, and k of 2 or 1 costs summary queries, so the paper's value stands.
RRF_K = 60


@dataclass(frozen=True, slots=True)
class FusedCandidate:
    """A candidate and its fused score, in the order fusion put them."""

    candidate: SearchCandidate
    score: float


def fuse_ranked_lists(
    ranked_lists: Iterable[Sequence[SearchCandidate]], *, k: int = RRF_K
) -> list[FusedCandidate]:
    """Fuse ranked lists into one order, highest fused score first.

    Duplicates *within* one list are ignored after the first: a retriever that returned the same
    candidate twice has stated one opinion about it, and counting the repeat would let a retriever
    inflate a candidate by repeating it.
    """
    if k < 1:
        raise ValueError(f"RRF's k must be at least 1; got {k}. At k=0 a rank-1 hit divides by zero.")

    totals: dict[SearchCandidate, float] = {}
    for ranked in ranked_lists:
        for rank, candidate in enumerate(_first_occurrences(ranked), start=1):
            totals[candidate] = totals.get(candidate, 0.0) + 1.0 / (k + rank)

    return [
        FusedCandidate(candidate=candidate, score=score)
        for candidate, score in sorted(totals.items(), key=lambda pair: _order(*pair))
    ]


def fuse_keeping_the_lead(
    anchor: Sequence[SearchCandidate],
    others: Iterable[Sequence[SearchCandidate]],
    *,
    k: int = RRF_K,
) -> list[FusedCandidate]:
    """Fuse as `fuse_ranked_lists` does, except that `anchor`'s first place stays first.

    The lead is scored `n / (k + 1)` over the `n` non-empty lists: what a candidate placed first by
    every list would score, the most fusion can award. No other candidate reaches it, because doing so
    means being first in `anchor` too. Every other score, and so every other position, is RRF's own.
    """
    lists = [list(anchor), *others]
    fused = fuse_ranked_lists(lists, k=k)
    if not anchor or fused[0].candidate == anchor[0]:
        return fused
    lead = FusedCandidate(candidate=anchor[0], score=sum(1 for ranked in lists if ranked) / (k + 1))
    return [lead, *(entry for entry in fused if entry.candidate != lead.candidate)]


def _first_occurrences(ranked: Sequence[SearchCandidate]) -> list[SearchCandidate]:
    """`ranked` with repeats after the first dropped, order preserved."""
    seen: set[SearchCandidate] = set()
    kept: list[SearchCandidate] = []
    for candidate in ranked:
        if candidate not in seen:
            seen.add(candidate)
            kept.append(candidate)
    return kept


def _order(candidate: SearchCandidate, score: float) -> tuple[float, int, str]:
    """Highest score first, then the existing kind order, then the id. Total and machine-independent."""
    kind = (
        RECORD_TYPE_ORDER.index(candidate.record_type)
        if candidate.record_type in RECORD_TYPE_ORDER
        else len(RECORD_TYPE_ORDER)
    )
    return (-score, kind, candidate.artifact_id)
