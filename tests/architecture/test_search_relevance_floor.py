"""Adding a retriever may not cost the queries the old one already answered.

Until this existed, "search is better now" was an opinion. It scores the same labelled strata twice
over one corpus — once with keyword retrieval alone, once with the vector branch fused in — and
compares the two. Nothing here compares a rate against a remembered number: the corpus changes with
every authored artifact, so a fixed threshold would fail on authoring rather than on regression.

**Two windows, because they answer different questions.** The `realises` stratum asks which
component realises a requirement, and its answer is always an entity; scoring it in the default
window measures the cross-kind round-robin rather than retrieval, since an entity gets under three of
those ten rows. So it is scored over entities. `name` and `summary` are general queries and are
scored as a reader would issue them, across every kind.

Both figures are reported on failure. Choosing only the flattering one would be the same defect this
module exists to catch.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.config.workspace_paths import resolve_workspace_repo_roots
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.bootstrap.embedding_model_asset import integrity_failures, model_directory
from src.infrastructure.search.text_encoder import StaticEmbeddingEncoder
from src.infrastructure.search.vector_retriever import VectorRetriever
from tools.quality.relevance_suite import RECALL_AT, LabelledQuery, StratumResult, draw_strata, score

_asset_failures = integrity_failures()
pytestmark = pytest.mark.skipif(
    bool(_asset_failures),
    reason=f"embedding weights not installed here — run get-embedding-model ({'; '.join(_asset_failures)})",
)


@pytest.fixture(scope="module")
def measured() -> dict[str, tuple[StratumResult, StratumResult]]:
    """Keyword-only and fused, over one corpus and one draw. Built once: the corpus is encoded."""
    roots = resolve_workspace_repo_roots(Path(__file__).resolve().parents[2])
    if not roots:
        pytest.skip("no workspace configuration")

    store = shared_artifact_index(roots[0])
    store.refresh()
    excluded = process_runtime_catalogs().ontology.entity_types_with_class("internal")
    keyword = ArtifactRepository(store, excluded_entity_types=excluded)
    fused = ArtifactRepository(
        store,
        excluded_entity_types=excluded,
        semantic_provider=VectorRetriever(store, StaticEmbeddingEncoder(model_directory())),
    )

    strata = draw_strata(store)
    results = {
        "name": _pair(keyword, fused, strata["name"], _every_kind),
        "summary": _pair(keyword, fused, strata["summary"], _every_kind),
        "realises": _pair(keyword, fused, strata["realises"], _entities_only),
        "realises (every kind)": _pair(keyword, fused, strata["realises"], _every_kind),
    }
    store.close()
    return results


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
    for name in ("name", "summary"):
        keyword, fused = measured[name]
        assert fused.answered >= keyword.answered, (
            f"fusing the vector branch lost queries on the {name} stratum\n{_report(measured)}"
        )


def test_the_vector_branch_earns_its_place_on_the_stratum_with_headroom(
    measured: dict[str, tuple[StratumResult, StratumResult]],
) -> None:
    """A retriever that costs 31 MB and changes no answer is one that should not ship."""
    keyword, fused = measured["realises"]
    assert fused.answered > keyword.answered, (
        "the vector branch answered no more requirement-to-component queries than keyword search "
        f"alone\n{_report(measured)}"
    )
