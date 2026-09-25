"""The measuring instrument, checked against a corpus the test owns.

The floor that uses this needs 31 MB of weights and skips without them, so the derivation would
otherwise be untested wherever the asset is not installed — which includes CI. Exact numbers are
fine here: the fixture is the test's own, so a count is a fact about the code rather than about
whatever happens to be authored.

The properties that matter are the ones a wrong derivation would break quietly. A stratum drawn from
the head of a sorted corpus instead of across it would still produce a rate; a `described` query that
kept the link to its own answer would name what it asks for; a summary query that kept the record's
heading would be the name stratum wearing a disguise. None of those fails — they just report a number
that means something else.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from tools.quality.relevance_suite import (
    RECALL_AT,
    STRATUM_SIZE,
    LabelledQuery,
    draw_strata,
    score,
)


def _entity(artifact_id: str, name: str, content: str = "", path: Path = Path("/nowhere.md")) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=name,
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain="",
        path=path,
        keywords=(),
        extra={},
        content_text=content,
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
    )


class _Store:
    """Just the questions the suite asks of a store."""

    def __init__(self, entities: list[EntityRecord], documents: list[DocumentRecord] | None = None) -> None:
        self._entities = {entity.artifact_id: entity for entity in entities}
        self._documents = documents or []

    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def list_documents(self) -> list[DocumentRecord]:
        return self._documents


def _document(content: str, path: Path) -> DocumentRecord:
    return DocumentRecord(
        artifact_id="ADR@1.d.decision", doc_type="adr", title="Decision", status="accepted", path=path,
        keywords=(), sections=(), content_text=content, extra={},
    )


def _store_of(count: int) -> _Store:
    entities = [
        _entity(f"REQ@1000000{index:03d}.aaaaaa.thing-{index}", f"Thing {index}", f"## Thing {index}\n\nProse {index}.")
        for index in range(count)
    ]
    return _Store(entities)


# ── drawing ──────────────────────────────────────────────────────────────────


def test_all_three_strata_are_drawn() -> None:
    strata = draw_strata(_store_of(10))
    assert set(strata) == {"name", "summary", "paraphrase", "described"}


def test_a_small_corpus_yields_every_candidate() -> None:
    strata = draw_strata(_store_of(7))
    assert len(strata["name"]) == 7


def test_a_large_corpus_is_capped_at_the_stratum_size() -> None:
    strata = draw_strata(_store_of(STRATUM_SIZE * 3))
    assert len(strata["name"]) == STRATUM_SIZE


def test_the_draw_spreads_across_the_corpus_rather_than_taking_the_head() -> None:
    """A draw clustered at one end measures that end, and would never say so."""
    strata = draw_strata(_store_of(STRATUM_SIZE * 3))
    drawn = [q.gold_artifact_id for q in strata["name"]]
    every = sorted(_store_of(STRATUM_SIZE * 3).entity_ids())
    assert drawn[0] == every[0]
    assert drawn[-1] > every[len(every) // 2], "the draw stopped before the second half"


def test_two_draws_over_one_corpus_agree() -> None:
    store = _store_of(STRATUM_SIZE * 2)
    assert draw_strata(store)["name"] == draw_strata(store)["name"]


def test_the_name_stratum_asks_an_artifacts_own_name() -> None:
    strata = draw_strata(_store_of(3))
    assert LabelledQuery("Thing 1", "REQ@1000000001.aaaaaa.thing-1") in strata["name"]


def test_the_summary_stratum_drops_the_heading() -> None:
    """The heading repeats the name, which would make this the name stratum in disguise."""
    store = _Store([_entity("REQ@1.a.x", "Peculiar Name", "## Peculiar Name\n\nThe prose body.")])
    query = draw_strata(store)["summary"][0].query
    assert query == "The prose body."
    assert "Peculiar" not in query


def test_an_entity_with_no_prose_contributes_no_summary_query() -> None:
    store = _Store([_entity("REQ@1.a.x", "Nameless Prose", "## Nameless Prose")])
    assert draw_strata(store)["summary"] == []


# ── the paraphrases ──────────────────────────────────────────────────────────


def test_a_paraphrase_is_answered_by_its_element_under_whatever_name_it_has_now() -> None:
    """Keyed by the rename-stable part of the id, so a rename changes nothing but the answer's slug."""
    store = _Store([_entity("APP@1.a.renamed-since", "Renamed Since")])
    drawn = draw_strata(store, paraphrases=[("APP@1.a", "what it does, in other words")])["paraphrase"]
    assert drawn == [LabelledQuery("what it does, in other words", "APP@1.a.renamed-since")]


def test_a_paraphrase_of_an_element_that_is_gone_drops_out() -> None:
    drawn = draw_strata(_Store([]), paraphrases=[("APP@1.gone", "nothing answers this")])["paraphrase"]
    assert drawn == []


# ── sentences in documents ───────────────────────────────────────────────────


def _linked(tmp_path: Path, content: str) -> list[LabelledQuery]:
    target = tmp_path / "model" / "APP@1.a.indexer.md"
    other = tmp_path / "model" / "APP@1.b.parser.md"
    entities = [_entity("APP@1.a.indexer", "Indexer", path=target), _entity("APP@1.b.parser", "Parser", path=other)]
    document = _document(content, tmp_path / "docs" / "ADR@1.d.decision.md")
    return draw_strata(_Store(entities, [document]))["described"]


def test_a_sentence_linking_one_element_asks_for_it_without_its_link(tmp_path: Path) -> None:
    content = "The [Indexer](../model/APP@1.a.indexer.md) rebuilds the searchable copy of every file."
    drawn = _linked(tmp_path, content)
    assert drawn == [LabelledQuery("The rebuilds the searchable copy of every file.", "APP@1.a.indexer")]


def test_a_sentence_linking_two_elements_asks_for_neither(tmp_path: Path) -> None:
    content = (
        "The [Indexer](../model/APP@1.a.indexer.md) reads what the [Parser](../model/APP@1.b.parser.md) wrote."
    )
    assert _linked(tmp_path, content) == []


def test_a_link_to_something_other_than_an_element_keeps_its_words(tmp_path: Path) -> None:
    content = (
        "The [Indexer](../model/APP@1.a.indexer.md) follows the [guide](../docs/guide.md) for every file it reads."
    )
    assert [q.query for q in _linked(tmp_path, content)] == ["The follows the guide for every file it reads."]


def test_a_sentence_too_short_to_be_a_question_is_skipped(tmp_path: Path) -> None:
    assert _linked(tmp_path, "See [Indexer](../model/APP@1.a.indexer.md).") == []


# ── scoring ──────────────────────────────────────────────────────────────────


def test_recall_counts_a_gold_answer_inside_the_window() -> None:
    stratum = [LabelledQuery("q", "gold")]
    assert score(lambda query: ["other", "gold"], stratum, "s").recall == 1.0


def test_recall_ignores_a_gold_answer_past_the_window() -> None:
    stratum = [LabelledQuery("q", "gold")]
    beyond = [f"filler-{index}" for index in range(RECALL_AT)] + ["gold"]
    assert score(lambda query: beyond, stratum, "s").recall == 0.0


def test_recall_over_an_empty_stratum_is_zero_rather_than_an_error() -> None:
    assert score(lambda query: ["anything"], [], "s").recall == 0.0


def test_the_result_carries_both_halves_of_the_fraction() -> None:
    """So a failure can report 3/120 rather than 2.5%, which is the number a reader can check."""
    stratum = [LabelledQuery("a", "x"), LabelledQuery("b", "y")]
    result = score(lambda query: ["x"], stratum, "s")
    assert (result.answered, result.asked) == (1, 2)
    assert result.recall == 0.5
