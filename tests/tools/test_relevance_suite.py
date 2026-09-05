"""The measuring instrument, checked against a corpus the test owns.

The floor that uses this needs 31 MB of weights and skips without them, so the derivation would
otherwise be untested wherever the asset is not installed — which includes CI. Exact numbers are
fine here: the fixture is the test's own, so a count is a fact about the code rather than about
whatever happens to be authored.

The properties that matter are the ones a wrong derivation would break quietly. A stratum drawn from
the head of a sorted corpus instead of across it would still produce a rate; a `realises` query that
kept the realising component's own name in it would make the hard stratum look easy; a summary query
that kept the record's heading would be the name stratum wearing a disguise. None of those fails —
they just report a number that means something else.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from tools.quality.relevance_suite import (
    RECALL_AT,
    STRATUM_SIZE,
    LabelledQuery,
    draw_strata,
    score,
)


def _entity(artifact_id: str, name: str, content: str = "") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=name,
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain="",
        path=Path("/nowhere.md"),
        keywords=(),
        extra={},
        content_text=content,
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
    )


class _Store:
    """Just the two questions the suite asks of a store."""

    def __init__(self, entities: list[EntityRecord], connections: list[ConnectionRecord]) -> None:
        self._entities = {entity.artifact_id: entity for entity in entities}
        self._connections = connections

    def entity_ids(self) -> set[str]:
        return set(self._entities)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]:
        return [c for c in self._connections if c.conn_type in types]


def _realisation(source: str, target: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source}---{target}@@archimate-realization",
        source=source,
        target=target,
        conn_type="archimate-realization",
        version="0.1.0",
        status="draft",
        path=Path("/nowhere.outgoing.md"),
        extra={},
        content_text="",
    )


def _store_of(count: int) -> _Store:
    entities = [
        _entity(f"REQ@1000000{index:03d}.aaaaaa.thing-{index}", f"Thing {index}", f"## Thing {index}\n\nProse {index}.")
        for index in range(count)
    ]
    return _Store(entities, [])


# ── drawing ──────────────────────────────────────────────────────────────────


def test_all_three_strata_are_drawn() -> None:
    strata = draw_strata(_store_of(10))
    assert set(strata) == {"name", "summary", "realises"}


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
    store = _Store([_entity("REQ@1.a.x", "Peculiar Name", "## Peculiar Name\n\nThe prose body.")], [])
    query = draw_strata(store)["summary"][0].query
    assert query == "The prose body."
    assert "Peculiar" not in query


def test_an_entity_with_no_prose_contributes_no_summary_query() -> None:
    store = _Store([_entity("REQ@1.a.x", "Nameless Prose", "## Nameless Prose")], [])
    assert draw_strata(store)["summary"] == []


# ── the hard stratum ─────────────────────────────────────────────────────────


def test_the_realises_stratum_asks_for_the_component_that_realises_a_requirement() -> None:
    store = _Store(
        [
            _entity("SRV@1.a.indexer", "SQLite Indexer"),
            _entity("REQ@1.b.search", "Fast Lookup", "## Fast Lookup\n\nResults shall return quickly."),
        ],
        [_realisation("SRV@1.a.indexer", "REQ@1.b.search")],
    )
    drawn = draw_strata(store)["realises"]
    assert [q.gold_artifact_id for q in drawn] == ["SRV@1.a.indexer"]
    assert "Fast Lookup" in drawn[0].query


def test_the_realising_components_own_name_is_removed_from_the_query() -> None:
    """Leaving it in would let term matching find the answer by name and hide the headroom."""
    store = _Store(
        [
            _entity("SRV@1.a.indexer", "SQLite Indexer"),
            _entity("REQ@1.b.search", "SQLite Indexer Behaviour", "## x\n\nThe SQLite Indexer shall index."),
        ],
        [_realisation("SRV@1.a.indexer", "REQ@1.b.search")],
    )
    query = draw_strata(store)["realises"][0].query
    assert "SQLite" not in query
    assert "Indexer" not in query
    assert "shall index" in query


def test_a_realisation_naming_an_unknown_endpoint_is_skipped() -> None:
    store = _Store(
        [_entity("REQ@1.b.search", "Fast Lookup", "## x\n\nProse.")],
        [_realisation("SRV@gone", "REQ@1.b.search")],
    )
    assert draw_strata(store)["realises"] == []


def test_a_realisation_whose_query_is_left_empty_is_skipped() -> None:
    """A requirement worded entirely in its realiser's own words leaves nothing to ask."""
    store = _Store(
        [_entity("SRV@1.a.x", "Fast Lookup"), _entity("REQ@1.b.y", "Fast Lookup", "")],
        [_realisation("SRV@1.a.x", "REQ@1.b.y")],
    )
    assert draw_strata(store)["realises"] == []


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
