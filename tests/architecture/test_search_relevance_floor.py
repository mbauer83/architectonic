"""Adding a retriever may not cost the queries the old one already answered.

Until this existed, "search is better now" was an opinion. It scores the same labelled strata twice
over one corpus — once with keyword retrieval alone, once with the vector branch fused in — and
compares the two. Nothing here compares a rate against a remembered number: the corpus changes with
every authored artifact, so a fixed threshold would fail on authoring rather than on regression.

**Two windows, because they answer different questions.** The `paraphrase` and `described` strata
ask for an element by what it is, and their answer is always an entity; scoring them in the default
window would measure the cross-kind round-robin rather than retrieval, since an entity gets under
three of those ten rows. So they are scored over entities. `name` and `summary` are general queries
and are scored as a reader would issue them, across every kind.

Both figures are reported on failure. Choosing only the flattering one would be the same defect this
module exists to catch.

**Two properties are stated as invariants rather than compared.** An element's exact name ranks it
first among the elements bearing that name, and the shortest beginning of its name that no other name
shares ranks it first outright — the moment a reader typing into a search box has said enough to mean
it, it is the answer at the top. Both hold for every element, with or without the vector branch, so
neither is a rate.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.application.artifacts.title_match import normalised_terms
from src.config.workspace_paths import resolve_workspace_repo_roots
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.bootstrap.embedding_model_asset import integrity_failures, model_directory
from src.infrastructure.search.text_encoder import StaticEmbeddingEncoder
from src.infrastructure.search.vector_retriever import VectorRetriever
from tools.quality.paraphrase_queries import PARAPHRASES
from tools.quality.relevance_suite import RECALL_AT, LabelledQuery, StratumResult, draw_strata, score

_asset_failures = integrity_failures()
pytestmark = pytest.mark.skipif(
    bool(_asset_failures),
    reason=f"embedding weights not installed here — run get-embedding-model ({'; '.join(_asset_failures)})",
)


@dataclass(frozen=True)
class _Corpus:
    """One corpus and one draw, searched two ways. Built once: the corpus is encoded."""

    keyword: ArtifactRepository
    fused: ArtifactRepository
    strata: dict[str, list[LabelledQuery]]
    namesakes: Counter[tuple[str, ...]]
    searchable: frozenset[str]


@pytest.fixture(scope="module")
def corpus() -> Iterator[_Corpus]:
    roots = resolve_workspace_repo_roots(Path(__file__).resolve().parents[2])
    if not roots:
        pytest.skip("no workspace configuration")

    store = shared_artifact_index(roots[0])
    store.refresh()
    excluded = process_runtime_catalogs().ontology.entity_types_with_class("internal")
    entities = store.list_entities()
    yield _Corpus(
        keyword=ArtifactRepository(store, excluded_entity_types=excluded),
        fused=ArtifactRepository(
            store,
            excluded_entity_types=excluded,
            semantic_provider=VectorRetriever(store, StaticEmbeddingEncoder(model_directory())),
        ),
        strata=draw_strata(store),
        namesakes=Counter(normalised_terms(entity.name) for entity in entities),
        searchable=frozenset(e.artifact_id for e in entities if e.artifact_type not in excluded),
    )
    store.close()


@pytest.fixture(scope="module")
def measured(corpus: _Corpus) -> dict[str, tuple[StratumResult, StratumResult]]:
    """Keyword-only and fused, over one corpus and one draw."""
    keyword, fused, strata = corpus.keyword, corpus.fused, corpus.strata
    return {
        "name": _pair(keyword, fused, strata["name"], _every_kind),
        "summary": _pair(keyword, fused, strata["summary"], _every_kind),
        "paraphrase": _pair(keyword, fused, strata["paraphrase"], _entities_only),
        "described": _pair(keyword, fused, strata["described"], _entities_only),
        "typed": _pair(keyword, fused, strata["typed"], _entities_only),
    }


def _every_kind(repo: ArtifactRepository) -> Callable[[str], list[str]]:
    return lambda query: [hit.record.artifact_id for hit in repo.search(query, limit=RECALL_AT).hits]


def _entities_only(repo: ArtifactRepository) -> Callable[[str], list[str]]:
    return lambda query: [
        hit.record.artifact_id
        for hit in repo.search_artifacts(
            query,
            limit=RECALL_AT,
            include_connections=False,
            include_diagrams=False,
            include_documents=False,
            include_scratchpads=False,
            include_scratchpad_notes=False,
        ).hits
    ]


def _pair(
    keyword: ArtifactRepository,
    fused: ArtifactRepository,
    stratum: list[LabelledQuery],
    window: Callable[[ArtifactRepository], Callable[[str], list[str]]],
) -> tuple[StratumResult, StratumResult]:
    return score(window(keyword), stratum, "keyword"), score(window(fused), stratum, "fused")


def _report(measured: dict[str, tuple[StratumResult, StratumResult]]) -> str:
    return "\n".join(
        f"  {name:24} keyword {k.recall:6.1%} ({k.answered}/{k.asked})"
        f"   fused {f.recall:6.1%} ({f.answered}/{f.asked})"
        for name, (k, f) in measured.items()
    )


def test_the_suite_asks_enough_to_measure_anything(
    measured: dict[str, tuple[StratumResult, StratumResult]],
) -> None:
    """A stratum that drew nothing would make every comparison below vacuously true."""
    for name, (keyword, _) in measured.items():
        assert keyword.asked > 0, f"{name} drew no queries\n{_report(measured)}"
    live, _ = measured["paraphrase"]
    assert live.asked * 2 > len(PARAPHRASES), (
        f"only {live.asked} of {len(PARAPHRASES)} paraphrases still name an element; the set has gone stale"
    )


def test_the_easy_strata_are_easy(
    measured: dict[str, tuple[StratumResult, StratumResult]],
) -> None:
    """The instrument's own sanity check: a query that *is* an artifact's name must find it.

    Half is a floor on the derivation, not on search quality — it fails when the strata stop being
    what they claim to be, not when a few artifacts are authored.
    """
    for name in ("name", "summary"):
        keyword, _ = measured[name]
        assert keyword.recall > 0.5, f"the {name} stratum is not measuring what it claims\n{_report(measured)}"


def test_nothing_regresses_where_keyword_search_already_answers(
    measured: dict[str, tuple[StratumResult, StratumResult]],
) -> None:
    """The floor. Fusing a second retriever in may not cost a query the first one answered."""
    for name in ("name", "summary", "described"):
        keyword, fused = measured[name]
        assert fused.answered >= keyword.answered, (
            f"fusing the vector branch lost queries on the {name} stratum\n{_report(measured)}"
        )


def test_the_vector_branch_earns_its_place_where_the_name_is_not_known(
    measured: dict[str, tuple[StratumResult, StratumResult]],
) -> None:
    """A retriever that costs 31 MB and finds nothing more by meaning is one that should not ship."""
    keyword, fused = measured["paraphrase"]
    assert fused.answered > keyword.answered, (
        "the vector branch found no more elements described without their names than keyword search "
        f"alone\n{_report(measured)}"
    )


def _misplaced(
    corpus: _Corpus, stratum: list[LabelledQuery], first_among: Callable[[LabelledQuery], int]
) -> list[str]:
    """Each query whose answer, searched both ways over entities, is not within its first places."""
    misses: list[str] = []
    for labelled in stratum:
        if labelled.gold_artifact_id not in corpus.searchable:
            continue
        for label, repo in (("keyword", corpus.keyword), ("fused", corpus.fused)):
            ranked = _entities_only(repo)(labelled.query)
            places = first_among(labelled)
            if labelled.gold_artifact_id not in ranked[:places]:
                misses.append(f"{label}: {labelled.query!r} → {ranked[:3]} (wanted {labelled.gold_artifact_id})")
    return misses


def test_an_exact_name_ranks_its_element_first_among_those_bearing_it(corpus: _Corpus) -> None:
    misses = _misplaced(corpus, corpus.strata["name"], lambda q: corpus.namesakes[normalised_terms(q.query)])
    assert not misses, "an element's exact name did not rank it first:\n  " + "\n  ".join(misses)


def test_the_shortest_unshared_beginning_of_a_name_ranks_its_element_first(corpus: _Corpus) -> None:
    """The typing reader's property: once what they typed begins one name only, that element leads."""
    assert corpus.strata["typed"], "the typed stratum drew nothing; the invariant below would be vacuous"
    misses = _misplaced(corpus, corpus.strata["typed"], lambda _: 1)
    assert not misses, "a uniquely typed name did not rank its element first:\n  " + "\n  ".join(misses)
