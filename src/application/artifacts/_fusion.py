"""Combining what the retrievers found, before the ordering policy sees any of it.

Two retrievers answer a search on scales that say nothing about each other. The old merge multiplied
one into the other's range by a constant; this fuses them by rank, which is the one thing they both
express the same way.

**Fusion happens per record type, and that is deliberate.** A kind's keyword hits are ranked against
each other on one scale — bm25 within a table, or the token-match supplement, never both for one
kind. Ranking a document against a connection was never meaningful, and turning that into a *rank*
would launder a comparison the codebase has refused everywhere else into a number. So each kind's two
lists are fused, and how the kinds then relate is `_ranking.py`'s question, as it already was.

One thing improves as a side effect. `rank_balanced` orders the kinds by their strongest hit's score,
which previously compared bm25 against token-match totals; after fusion every kind's score is an RRF
score computed the same way, so that comparison means something for the first time.

**The keyword branch's first hit in a kind keeps first place in it.** The vector branch was added to
find what keyword search misses, and the floor it was admitted under is that it costs nothing keyword
search already answers. Plain RRF breaks that floor: a window of ten holds two or three hits of a
kind, and agreement at second place outscores a keyword lead the vector branch placed sixth at every
k. Measured on the labelled suite (2026-11-26; queries answered in the window, keyword alone first):

| configuration                  | name    | summary | paraphrase | described |
| ------------------------------ | ------- | ------- | ---------- | --------- |
| keyword only                   | 120/120 | 119/120 | 44/76      | 49/83     |
| RRF, k=60                      | 120/120 | 118/120 | 53/76      | 51/83     |
| RRF, k=10                      | 120/120 | 118/120 | 54/76      | 51/83     |
| RRF, k=1                       | 120/120 | 116/120 | 51/76      | 51/83     |
| RRF weighted 2:1 keyword, k=60 | 120/120 | 119/120 | 50/76      | 52/83     |
| both lists' leads kept, k=60   | 120/120 | 117/120 | 53/76      | 51/83     |
| keyword lead kept, k=60        | 120/120 | 119/120 | 53/76      | 51/83     |

Weighting the keyword list restores the floor by spending a third of the paraphrase gain. Keeping
the vector branch's lead as well costs two summary queries, so the claim is the keyword branch's
alone: its first place is lexical evidence the vector branch's is not.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

from src.domain.ontology_representation.artifact_types import SearchHit
from src.domain.rank_fusion import fuse_keeping_the_lead
from src.domain.search_records import RecordType, SearchCandidate

#: Resolves a candidate the vector branch found that the keyword branch did not, or None when the
#: record has gone. Injected because reading a record by kind is the store's vocabulary, not this
#: module's, and every kind's accessor has a different name.
RecordResolver = Callable[[SearchCandidate], object | None]


def fuse(
    keyword_hits: Sequence[SearchHit],
    semantic_by_type: dict[str, list[SearchCandidate]],
    *,
    resolve: RecordResolver,
) -> list[SearchHit]:
    """One hit list, each hit scored by rank fusion within its own kind.

    A hit the keyword branch found keeps its record; one only the vector branch found is resolved
    through `resolve` and dropped where the record has gone, which is the same treatment the keyword
    branches give a candidate whose file disappeared between the index and the read.
    """
    by_type = _keyword_hits_by_type(keyword_hits)
    fused: list[SearchHit] = []
    for record_type in by_type.keys() | semantic_by_type.keys():
        keyword_ranked = [_candidate_of(hit) for hit in by_type.get(record_type, ())]
        records = {_candidate_of(hit): hit.record for hit in by_type.get(record_type, ())}
        for entry in fuse_keeping_the_lead(keyword_ranked, [semantic_by_type.get(record_type, [])]):
            record = records.get(entry.candidate) or resolve(entry.candidate)
            if record is not None:
                fused.append(
                    SearchHit(
                        score=entry.score,
                        record_type=cast(RecordType, entry.candidate.record_type),
                        record=record,  # type: ignore[arg-type]
                    )
                )
    return fused


def _keyword_hits_by_type(hits: Sequence[SearchHit]) -> dict[str, list[SearchHit]]:
    """Hits grouped by kind, each group strongest first — which is the rank fusion reads.

    The id breaks a tie so two hits the same scorer scored alike get a stable order, matching what
    `_ranking.by_kind` does with the same question.
    """
    grouped: dict[str, list[SearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.record_type, []).append(hit)
    for group in grouped.values():
        group.sort(key=lambda hit: (-hit.score, hit.record.artifact_id))
    return grouped


def _candidate_of(hit: SearchHit) -> SearchCandidate:
    return SearchCandidate(record_type=hit.record_type, artifact_id=hit.record.artifact_id)
