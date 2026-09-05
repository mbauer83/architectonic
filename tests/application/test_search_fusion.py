"""Combining the retrievers by rank, and the properties that replaced a multiplication by 3.0.

Fusion happens per record type, so what these state is: within a kind the two lists are fused; the
kinds are never compared here; and a candidate two retrievers found outranks one that only a single
retriever placed highly. The last is the whole reason for fusing rather than concatenating, and it
is the property a weighted merge could not express, because there was no scale on which to say how
much agreement is worth.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts._fusion import fuse
from src.domain.ontology_representation.artifact_types import EntityRecord, SearchHit
from src.domain.search_records import SearchCandidate


def _entity(artifact_id: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=artifact_id,
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain="",
        path=Path("/nowhere.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias=artifact_id,
    )


def _hit(artifact_id: str, score: float, record_type: str = "entity") -> SearchHit:
    return SearchHit(score=score, record_type=record_type, record=_entity(artifact_id))  # type: ignore[arg-type]


def _candidate(artifact_id: str, record_type: str = "entity") -> SearchCandidate:
    return SearchCandidate(record_type=record_type, artifact_id=artifact_id)  # type: ignore[arg-type]


def _resolver(known: dict[str, EntityRecord]):  # noqa: ANN202 — a closure over the test's own records
    return lambda candidate: known.get(candidate.artifact_id)


def _ids(hits: list[SearchHit]) -> list[str]:
    return [hit.record.artifact_id for hit in sorted(hits, key=lambda h: -h.score)]


def test_a_candidate_both_retrievers_found_outranks_one_only_a_single_retriever_led_with() -> None:
    """The property a weighted merge had no scale to express."""
    keyword = [_hit("alone", 99.0), _hit("agreed", 1.0)]
    semantic = {"entity": [_candidate("agreed"), _candidate("other")]}
    fused = fuse(keyword, semantic, resolve=_resolver({"other": _entity("other")}))
    assert _ids(fused)[0] == "agreed"


def test_a_keyword_only_result_still_reaches_the_reader() -> None:
    fused = fuse([_hit("keyword-only", 5.0)], {}, resolve=lambda candidate: None)
    assert _ids(fused) == ["keyword-only"]


def test_a_vector_only_result_reaches_the_reader() -> None:
    records = {"vector-only": _entity("vector-only")}
    fused = fuse([], {"entity": [_candidate("vector-only")]}, resolve=_resolver(records))
    assert _ids(fused) == ["vector-only"]


def test_a_vector_candidate_whose_record_has_gone_is_dropped() -> None:
    """The same treatment a keyword candidate gets when its file disappeared under the index."""
    fused = fuse([], {"entity": [_candidate("vanished")]}, resolve=lambda candidate: None)
    assert fused == []


def test_the_keyword_order_survives_when_only_one_retriever_answered() -> None:
    keyword = [_hit("second", 1.0), _hit("first", 9.0), _hit("third", 0.5)]
    assert _ids(fuse(keyword, {}, resolve=lambda candidate: None)) == ["first", "second", "third"]


def test_the_vector_order_survives_when_only_one_retriever_answered() -> None:
    records = {name: _entity(name) for name in ("first", "second", "third")}
    semantic = {"entity": [_candidate("first"), _candidate("second"), _candidate("third")]}
    assert _ids(fuse([], semantic, resolve=_resolver(records))) == ["first", "second", "third"]


def test_kinds_are_fused_separately_and_never_against_each_other() -> None:
    """Ranking a document against a connection was never meaningful; fusion must not make it look so."""
    keyword = [_hit("doc", 500.0, record_type="document"), _hit("ent", 0.1)]
    fused = fuse(keyword, {}, resolve=lambda candidate: None)
    scores = {hit.record_type: hit.score for hit in fused}
    assert scores["document"] == scores["entity"], "each was rank 1 of its own kind"


def test_every_fused_score_comes_from_the_same_formula() -> None:
    """Which is what makes `rank_balanced`'s comparison of kinds mean something for the first time."""
    keyword = [_hit("a", 1000.0), _hit("d", 0.001, record_type="diagram")]
    fused = fuse(keyword, {}, resolve=lambda candidate: None)
    assert len({hit.score for hit in fused}) == 1


def test_a_kind_the_vector_branch_does_not_cover_is_untouched() -> None:
    keyword = [_hit("c1", 3.0, record_type="connection"), _hit("c2", 1.0, record_type="connection")]
    fused = fuse(keyword, {"entity": []}, resolve=lambda candidate: None)
    assert _ids(fused) == ["c1", "c2"]


def test_nothing_in_and_nothing_out() -> None:
    assert fuse([], {}, resolve=lambda candidate: None) == []
