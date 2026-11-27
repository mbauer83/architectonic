"""An artifact's title, typed a character at a time, reaches the window long before it is complete.

Reported against the served repository: nearly the whole name had to be typed before the artifact
appeared in the search box's list. Three causes, each held here on a corpus the test owns:

- the keyword index matched whole words only, so the unfinished last word of `Artifact Ind` matched
  nothing and the query meant *artifact* alone;
- each kind's window was cut by bm25, which prefers a body repeating a common word over a title that
  carries it once — so the title being typed was not admitted at all, and the ranking above it never
  saw it; and the cut was made again, by score alone, where two repositories' answers are merged;
- the ranking promoted a title only when it carried every query term *whole*.

The fixture is the shape of the failure: a dozen documents whose bodies say *artifact index* over
and over, and one whose title is `Artifact Index` and whose body does not. Documents, because their
columns are ranked unweighted, so the bodies outscore the title on bm25 — which the first test checks
before it relies on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.domain.search_records import KeywordRow, SearchCandidate, SemanticSearchProvider, TitleAdmission
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.artifact_index._combined_support import merge_search_rows
from tests.support.search_visibility_fixtures import entity_md, write_file

_TITLE = "Artifact Index"
_TARGET = "STD@1000000600.Target.artifact-index"
_NOISE = "artifact index " * 8

#: Smaller than the number of records that mention the word, so the window must choose.
_WINDOW = 4


def _document(artifact_id: str, title: str, body: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: document\n"
        "doc-type: standard\n"
        f"title: {title}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"# {title}\n\n{body}\n"
    )


def _repo(root: Path, prefix: str, *, target: bool, noise: int) -> Path:
    folder = root / "docs" / "standard"
    if target:
        write_file(folder / f"{_TARGET}.md", _document(_TARGET, _TITLE, "Short."))
    for index in range(noise):
        aid = f"STD@1000000{prefix}{index:02d}.Noise{index}.noise-{index}"
        write_file(folder / f"{aid}.md", _document(aid, f"Record {index}", _NOISE))
    return root


@pytest.fixture
def engagement(tmp_path: Path) -> Path:
    return _repo(tmp_path / "engagements" / "ENG-TYPE" / "architecture-repository", "7", target=True, noise=12)


@pytest.fixture
def enterprise(tmp_path: Path) -> Path:
    return _repo(tmp_path / "enterprise-repository", "8", target=False, noise=12)


_DOCUMENTS = frozenset({"documents"})


def _window(repo: ArtifactRepository, query: str) -> list[str]:
    hits = repo.search_artifacts(
        query, limit=_WINDOW, include_entities=False, include_connections=False, include_diagrams=False,
        include_scratchpads=False, include_scratchpad_notes=False,
    ).hits
    return [hit.record.artifact_id for hit in hits]


class TestTheKeywordIndex:
    def test_an_unfinished_last_word_matches_as_a_prefix(self, engagement: Path) -> None:
        index = shared_artifact_index(engagement)
        assert _TARGET in [row.artifact_id for row in index.search_fts("Artif", limit=50, kinds=_DOCUMENTS)]
        assert _TARGET in [row.artifact_id for row in index.search_fts("Artifact Ind", limit=50, kinds=_DOCUMENTS)]
        assert shared_artifact_index(engagement).search_fts("Indexx", limit=50) == []

    def test_a_title_match_is_admitted_ahead_of_bodies_that_outscore_it(self, engagement: Path) -> None:
        """The regression: ordered by bm25 alone, twelve bodies filled a window of four."""
        index = shared_artifact_index(engagement)
        rows = index.search_fts("artifact", limit=_WINDOW, kinds=_DOCUMENTS)
        everything = index.search_fts("artifact", limit=50, kinds=_DOCUMENTS)

        by_score = sorted(everything, key=lambda row: -row.score)
        assert by_score[0].artifact_id != _TARGET, "the fixture must make bodies outscore the title"
        assert _TARGET in [row.artifact_id for row in rows]
        assert [row.title for row in rows if row.artifact_id == _TARGET] == [TitleAdmission.BEGINNING]
        assert not any(row.title for row in rows if row.artifact_id != _TARGET)

    def test_a_title_beginning_with_the_query_is_admitted_ahead_of_one_merely_containing_it(
        self, tmp_path: Path
    ) -> None:
        """A unique prefix must reach the window even when other titles carry every typed word."""
        root = _repo(tmp_path / "engagements" / "ENG-ORDER" / "architecture-repository", "7", target=True, noise=0)
        for index in range(12):
            aid = f"STD@1000000800{index:02d}.Words{index}.words-{index}"
            write_file(root / "docs" / "standard" / f"{aid}.md", _document(aid, f"Index of Artifact {index}", _NOISE))

        rows = shared_artifact_index(root).search_fts("artifact ind", limit=2, kinds=_DOCUMENTS)

        assert _TARGET in [row.artifact_id for row in rows]
        assert {row.title for row in rows} == {TitleAdmission.BEGINNING, TitleAdmission.EVERY_WORD}

    def test_an_exact_title_is_admitted_ahead_of_longer_titles_beginning_alike(self, tmp_path: Path) -> None:
        """`Architect` was crowded out of a picker by a dozen `Architecture …` records."""
        root = _repo(tmp_path / "engagements" / "ENG-EXACT" / "architecture-repository", "7", target=False, noise=0)
        exact = "STD@1000000610.Exact.artifact"
        write_file(root / "docs" / "standard" / f"{exact}.md", _document(exact, "Artifact", "Short."))
        for index in range(12):
            aid = f"STD@1000000810{index:02d}.Longer{index}.longer-{index}"
            write_file(root / "docs" / "standard" / f"{aid}.md", _document(aid, f"Artifacts Record {index}", _NOISE))

        rows = shared_artifact_index(root).search_fts("artifact", limit=2, kinds=_DOCUMENTS)

        assert exact in [row.artifact_id for row in rows]

    def test_merging_two_repositories_keeps_the_title_match(self, engagement: Path, enterprise: Path) -> None:
        """The second cut: the combined view re-cut each kind by score and dropped it again."""
        combined = combined_artifact_index(engagement, enterprise)

        rows = combined.search_fts("artif", limit=_WINDOW, kinds=_DOCUMENTS)

        assert _TARGET in [row.artifact_id for row in rows]


def test_the_merge_orders_each_kind_as_the_index_admitted_it() -> None:
    left = [
        KeywordRow("A", "entity", 9.0, TitleAdmission.NONE),
        KeywordRow("W", "entity", 8.0, TitleAdmission.EVERY_WORD),
    ]
    right = [
        KeywordRow("T", "entity", 1.0, TitleAdmission.BEGINNING),
        KeywordRow("C", "entity", 7.0, TitleAdmission.NONE),
    ]

    merged = merge_search_rows(left, right, limit=2)

    assert {row.artifact_id for row in merged} == {"T", "W"}


class TestTheSearchUseCase:
    def test_every_prefix_of_the_title_puts_it_first(self, engagement: Path) -> None:
        repo = ArtifactRepository(shared_artifact_index(engagement))

        for typed in range(2, len(_TITLE) + 1):
            assert _window(repo, _TITLE[:typed])[0] == _TARGET, f"typed {_TITLE[:typed]!r}"

    def test_a_word_from_the_middle_of_the_title_reaches_the_window(self, engagement: Path) -> None:
        repo = ArtifactRepository(shared_artifact_index(engagement))

        assert _window(repo, "Ind")[0] == _TARGET
        assert _window(repo, "dex")[0] == _TARGET

    def test_the_vector_branch_cannot_push_a_typed_title_out(self, engagement: Path) -> None:
        """Fusion re-scores; a score never outranks a title tier, however many neighbours agree."""
        for index in range(50):  # the vector branch opens only over a corpus of some size
            aid = f"REQ@1000000900.Fill{index:02d}.filler-{index}"
            write_file(
                engagement / "model" / "motivation" / "requirement" / f"{aid}.md",
                entity_md(aid, "requirement", f"Filler {index}"),
            )
        noise = [f"STD@10000007{index:02d}.Noise{index}.noise-{index}" for index in range(12)]
        repo = ArtifactRepository(shared_artifact_index(engagement), semantic_provider=_Neighbours(noise))

        assert _window(repo, "Artifact In")[0] == _TARGET


class _Neighbours(SemanticSearchProvider):
    """A vector branch that answers every query with the same records, none of them the target."""

    def __init__(self, ranked: list[str]) -> None:
        self._ranked = [SearchCandidate(record_type="document", artifact_id=aid) for aid in ranked]

    def ranked_candidates(self, query: str, limit: int) -> list[SearchCandidate]:
        return self._ranked[:limit]
