"""Retrieval by meaning: one matrix over the corpus, and the candidates a query is nearest to.

There is no persisted cache and no generation scheme. Building the whole corpus takes 0.2 s
measured, so the matrix is built in memory when the retriever is constructed — which removes a
file, a content-addressed generation, an atomically replaced pointer, a grace period before
collecting a superseded one, and the staleness question all of them existed to answer.

The corpus is the engagement and enterprise repositories. Assurance content is excluded entirely
rather than embedded under an inherited classification: an embedding is a derived representation of
the text that produced it, and one matrix holding both tiers would let a similarity score surface
the existence of classified content through a surface governed by the engagement repository's rules.
This module reads the artifact store, which is that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

import numpy as np

from src.application.ports import ReadableArtifactStore
from src.domain.corpus_text import CorpusRecord, embeddable_text, text_chunks
from src.domain.search_records import RecordType, SearchCandidate
from src.infrastructure.search.text_encoder import TextEncoder


@dataclass(frozen=True, slots=True)
class _Passage:
    """One chunk of one record: what was encoded, and what it stands for."""

    candidate: SearchCandidate
    text: str


class VectorRetriever:
    """Ranks the corpus by how close each record's meaning is to a query's.

    A record contributes as many vectors as it has chunks and is ranked by its best one, so a long
    document is not penalised for the paragraphs that have nothing to do with the query — which is
    the failure mean-pooling a whole document into one vector produces.
    """

    def __init__(self, store: ReadableArtifactStore, encoder: TextEncoder) -> None:
        self._encoder = encoder
        self._passages = tuple(_corpus_passages(store))
        self._matrix = encoder.encode([passage.text for passage in self._passages])

    @property
    def corpus_size(self) -> int:
        """Passages encoded. Zero means every query answers empty, which is a valid state."""
        return len(self._passages)

    def ranked_candidates(self, query: str, limit: int) -> tuple[SearchCandidate, ...]:
        """The corpus ordered by similarity to `query`, best first, one entry per record.

        Rank order and nothing else. What the caller does with the ordering — fuse it, filter it,
        cut it — is the caller's, and returning a score here would invite comparing this retriever's
        scale against another's, which is exactly what rank fusion exists to avoid.
        """
        return tuple(candidate for _, candidate in self._ranked(query)[:limit]) if limit > 0 else ()

    def _ranked(self, query: str) -> list[tuple[float, SearchCandidate]]:
        """Every record with the similarity of its best-matching passage, descending.

        A record appears once. Sorting the passages first and keeping the first sighting of each
        record is the same answer as a per-record maximum, without computing one: the first time a
        record is seen is by construction at its own best passage.
        """
        if not self._passages:
            return []
        similarities = self._matrix @ self._encoder.encode([query])[0]
        ranked: list[tuple[float, SearchCandidate]] = []
        seen: set[SearchCandidate] = set()
        for position in np.argsort(-similarities, kind="stable"):
            candidate = self._passages[int(position)].candidate
            if candidate not in seen:
                seen.add(candidate)
                ranked.append((float(similarities[position]), candidate))
        return ranked

    # ── The seam the application consumes today ──────────────────────────────
    #
    # `SemanticSearchProvider.top_k` is entity-only and score-carrying, which is what the consumer
    # in `_search_eligibility.py` was written against. Both go away when that consumer moves to rank
    # fusion; until then this answers the older shape from the same ranking rather than building a
    # second corpus for it.

    def top_k(self, query: str, k: int, *, threshold: float = 0.75) -> list[tuple[float, str]]:
        """The `k` nearest entities as `(cosine similarity, id)`, none below `threshold`.

        Real similarities, not positions: the caller weighs them against keyword scores, and a
        fabricated number would be weighed just as readily.
        """
        entities = (
            (score, candidate.artifact_id)
            for score, candidate in self._ranked(query)
            if candidate.record_type == "entity" and score >= threshold
        )
        return list(islice(entities, max(k, 0)))


def _corpus_passages(store: ReadableArtifactStore) -> list[_Passage]:
    """Every chunk of every record worth a vector, in a stable order.

    Stable because the matrix rows are addressed by position: a different order for the same corpus
    would be a different matrix, and a test comparing two builds would be comparing orderings.
    """
    return [
        _Passage(SearchCandidate(record_type=record_type, artifact_id=artifact_id), chunk)
        for record_type, artifact_id, record in _corpus_records(store)
        for chunk in text_chunks(embeddable_text(record))
    ]


def _corpus_records(store: ReadableArtifactStore) -> list[tuple[RecordType, str, CorpusRecord]]:
    entities = (
        (store.get_entity(artifact_id), artifact_id) for artifact_id in sorted(store.entity_ids())
    )
    return [
        *(("entity", artifact_id, record) for record, artifact_id in entities if record is not None),
        *(("document", record.artifact_id, record) for record in store.list_documents()),
        *(("diagram", record.artifact_id, record) for record in store.list_diagrams()),
    ]
