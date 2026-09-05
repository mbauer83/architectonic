"""Retrieval by meaning, over a real store and a stand-in encoder.

The store is real, because enumerating the corpus is half of what this class does and a fake store
would let a kind quietly fall out of it. The encoder is not, because requiring 31 MB of downloaded
weights would make the suite refuse to run on a machine that has not provisioned them — and because
a stand-in whose vectors the test chooses is what makes an assertion about ranking mean anything.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from src.domain.search_records import SearchCandidate
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.search.vector_retriever import VectorRetriever
from tests.support.search_visibility_fixtures import document_md, entity_md, write_file

#: The stand-in encoder's whole vocabulary. A passage is the unit vector of its counts over these,
#: so a query shares direction with a passage exactly to the extent they use the same words.
_VOCABULARY = ("promotion", "embedding", "ranking", "graph", "colour", "ledger")


class VocabularyEncoder:
    """Counts over a fixed vocabulary, normalised. Predictable enough to assert an order against."""

    def __init__(self) -> None:
        self.encoded: list[list[str]] = []

    def encode(self, passages: list[str]) -> NDArray[np.float32]:
        self.encoded.append(list(passages))
        rows = np.array(
            [[float(passage.lower().count(word)) for word in _VOCABULARY] for passage in passages],
            dtype=np.float32,
        ).reshape(len(passages), self.dimensions)
        lengths = np.linalg.norm(rows, axis=1, keepdims=True)
        return np.divide(rows, lengths, out=np.zeros_like(rows), where=lengths > 0)

    @property
    def dimensions(self) -> int:
        return len(_VOCABULARY)


def _repo(tmp_path: Path, *, entities: dict[str, str], documents: dict[str, str] | None = None) -> Path:
    root = tmp_path / "engagements" / "ENG-VEC" / "architecture-repository"
    for artifact_id, body in entities.items():
        write_file(
            root / "model" / "motivation" / "requirement" / f"{artifact_id}.md",
            entity_md(artifact_id, "requirement", artifact_id.split(".")[-1], body=body),
        )
    for artifact_id, title in (documents or {}).items():
        write_file(root / "docs" / "adr" / f"{artifact_id}.md", document_md(artifact_id, title))
    return root


def _retriever(root: Path, encoder: VocabularyEncoder) -> VectorRetriever:
    store = shared_artifact_index(root)
    store.refresh()
    return VectorRetriever(store, encoder)


_PROMOTION = "REQ@1000000401.Aaaaaa.promotion-requirement"
_EMBEDDING = "REQ@1000000402.Bbbbbb.embedding-requirement"
_GRAPH = "REQ@1000000403.Cccccc.graph-requirement"


@pytest.fixture
def three_records(tmp_path: Path) -> Path:
    return _repo(
        tmp_path,
        entities={
            _PROMOTION: "promotion promotion promotion",
            _EMBEDDING: "embedding embedding embedding",
            _GRAPH: "graph graph graph",
        },
    )


def test_the_nearest_record_ranks_first(three_records: Path) -> None:
    ranked = _retriever(three_records, VocabularyEncoder()).ranked_candidates("embedding", limit=3)
    assert ranked[0].artifact_id == _EMBEDDING


def test_every_ranked_entry_is_a_typed_candidate(three_records: Path) -> None:
    for candidate in _retriever(three_records, VocabularyEncoder()).ranked_candidates("graph", limit=3):
        assert isinstance(candidate, SearchCandidate)
        assert candidate.record_type in {"entity", "document", "diagram"}


def test_limit_truncates_and_zero_asks_for_nothing(three_records: Path) -> None:
    retriever = _retriever(three_records, VocabularyEncoder())
    assert len(retriever.ranked_candidates("promotion", limit=2)) == 2
    assert retriever.ranked_candidates("promotion", limit=0) == ()
    assert retriever.ranked_candidates("promotion", limit=-1) == ()


def test_a_record_appears_once_however_many_chunks_it_has(tmp_path: Path) -> None:
    """A long record contributes several vectors and must still be one result."""
    root = _repo(tmp_path, entities={_PROMOTION: " ".join(["promotion ledger"] * 400)})
    retriever = _retriever(root, VocabularyEncoder())
    assert retriever.corpus_size > 1, "the fixture is meant to chunk"
    ranked = retriever.ranked_candidates("promotion", limit=10)
    assert [candidate.artifact_id for candidate in ranked].count(_PROMOTION) == 1


def test_a_record_is_ranked_by_its_best_passage_not_its_average(tmp_path: Path) -> None:
    """The failure that mean-pooling a whole document into one vector produces."""
    long_record = " ".join(["colour"] * 400) + " " + " ".join(["embedding"] * 60)
    root = _repo(tmp_path, entities={_PROMOTION: long_record, _GRAPH: "embedding graph"})
    ranked = _retriever(root, VocabularyEncoder()).ranked_candidates("embedding", limit=2)
    assert ranked[0].artifact_id == _PROMOTION


def test_documents_are_in_the_corpus_beside_entities(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        entities={_PROMOTION: "promotion"},
        documents={"ADR@1000000404.Dddddd.embedding-decision": "Embedding Decision"},
    )
    ranked = _retriever(root, VocabularyEncoder()).ranked_candidates("embedding", limit=10)
    assert "document" in {candidate.record_type for candidate in ranked}


def test_an_empty_corpus_answers_empty_rather_than_failing(tmp_path: Path) -> None:
    root = _repo(tmp_path, entities={})
    retriever = _retriever(root, VocabularyEncoder())
    assert retriever.corpus_size == 0
    assert retriever.ranked_candidates("anything", limit=5) == ()


def test_a_query_the_encoder_has_no_vectors_for_ranks_nothing_above_anything(three_records: Path) -> None:
    """An all-zero query must not produce NaN, which sorts as neither greater nor less."""
    ranked = _retriever(three_records, VocabularyEncoder()).ranked_candidates("zymurgy", limit=3)
    assert len(ranked) == 3


def test_two_builds_of_one_store_rank_identically(three_records: Path) -> None:
    """Matrix rows are addressed by position, so corpus order has to be stable."""
    first = _retriever(three_records, VocabularyEncoder()).ranked_candidates("promotion", limit=3)
    second = _retriever(three_records, VocabularyEncoder()).ranked_candidates("promotion", limit=3)
    assert first == second


def test_the_corpus_is_encoded_once_at_construction_not_per_query(three_records: Path) -> None:
    encoder = VocabularyEncoder()
    retriever = _retriever(three_records, encoder)
    assert len(encoder.encoded) == 1
    retriever.ranked_candidates("promotion", limit=3)
    retriever.ranked_candidates("embedding", limit=3)
    assert [len(batch) for batch in encoder.encoded[1:]] == [1, 1]


# ── the contract the application consumes ───────────────────────────────────


def test_the_retriever_satisfies_the_provider_protocol(three_records: Path) -> None:
    """What the application depends on, checked against the application's own declaration."""
    from src.domain.search_records import SemanticSearchProvider

    assert isinstance(_retriever(three_records, VocabularyEncoder()), SemanticSearchProvider)


def test_nothing_carries_a_score_across_the_seam(three_records: Path) -> None:
    """A score would invite comparing this retriever's scale against the keyword branch's."""
    ranked = _retriever(three_records, VocabularyEncoder()).ranked_candidates("embedding", limit=3)
    assert ranked
    assert [field.name for field in fields(SearchCandidate)] == ["record_type", "artifact_id"]
    assert all(not hasattr(candidate, "score") for candidate in ranked)


def test_a_deeper_request_returns_a_prefix_of_itself(three_records: Path) -> None:
    """Fusion asks deeper than the window; a deeper ask must not reorder what a shallower one gave."""
    retriever = _retriever(three_records, VocabularyEncoder())
    assert retriever.ranked_candidates("embedding", limit=2) == retriever.ranked_candidates(
        "embedding", limit=5
    )[:2]
