"""Fusing the vector branch in may not push keyword search's first answer out of the window.

The labelled suite's floor (`tests/architecture/test_search_relevance_floor.py`) found this on the
live corpus: a summary query whose answer keyword search ranked first fell to third among entities,
behind candidates both retrievers agreed on lower down, and the window held two entities. That test
reads the real repository, so it moves with authoring; this one owns its corpus and holds the
property itself, through the whole search path rather than the fusion function alone.

The vector branch is a fixture that returns every keyword hit *except* the lead, which is the
hardest form of the case: each of those candidates is found twice, and the lead only once.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.repository import ArtifactRepository
from src.domain.ontology_representation.artifact_types import SemanticSearchProvider
from src.domain.search_records import SearchCandidate
from src.infrastructure.artifact_index import shared_artifact_index
from tests.support.search_visibility_fixtures import entity_md, write_file

_QUERY = "zymurgy fermentation"

#: The window the property is held in. The live window held two entities; at two, the candidates the
#: vector branch agrees with fill it under plain RRF in both cases below.
_WINDOW = 2


class FixedRanking(SemanticSearchProvider):
    """A vector branch that answers every query with one fixed ranking."""

    def __init__(self, ranked: list[str]) -> None:
        self._ranked = [SearchCandidate(record_type="entity", artifact_id=aid) for aid in ranked]

    def ranked_candidates(self, query: str, limit: int) -> list[SearchCandidate]:
        return self._ranked[:limit]


def _corpus(tmp_path: Path) -> Path:
    """Fifty-odd entities, so the vector branch's corpus gate opens; six of them match the query.

    No title carries both query terms, so the ranking policy's name sections stay empty and the
    order in the window is fusion's.
    """
    root = tmp_path / "engagements" / "ENG-FUSE" / "architecture-repository"
    folder = root / "model" / "motivation" / "requirement"
    matching = [
        ("Strong", "Zymurgy and fermentation, fermentation and zymurgy, are what this is about."),
        *((f"Weaker {i}", f"Mentions fermentation once, among other things {i}.") for i in range(5)),
    ]
    for index, (name, body) in enumerate(matching):
        aid = f"REQ@1000000400.Match{index}.matching-{index}"
        write_file(folder / f"{aid}.md", entity_md(aid, "requirement", name, body=body))
    for index in range(50):
        aid = f"REQ@1000000500.Fill{index:02d}.filler-{index}"
        write_file(folder / f"{aid}.md", entity_md(aid, "requirement", f"Filler {index}"))
    return root


def _window(repo: ArtifactRepository) -> list[str]:
    return [hit.record.artifact_id for hit in repo.search_artifacts(_QUERY, limit=_WINDOW).hits]


def _keyword_ranking(root: Path) -> list[str]:
    return [
        hit.record.artifact_id
        for hit in ArtifactRepository(shared_artifact_index(root)).search_artifacts(_QUERY, limit=50).hits
    ]


def test_keyword_searchs_lead_survives_fusion_into_the_window(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    keyword = _keyword_ranking(root)
    assert len(keyword) > _WINDOW, f"the fixture must give keyword search more hits than the window: {keyword}"
    lead, *rest = keyword

    fused = ArtifactRepository(shared_artifact_index(root), semantic_provider=FixedRanking(rest))

    assert _window(fused)[0] == lead


def test_the_lead_survives_where_the_vector_branch_places_it_last(tmp_path: Path) -> None:
    """The live case: found by both, but far down the vector list, behind agreement at second place."""
    root = _corpus(tmp_path)
    lead, *rest = _keyword_ranking(root)

    fused = ArtifactRepository(shared_artifact_index(root), semantic_provider=FixedRanking([*rest, lead]))

    assert lead in _window(fused)
