"""The title tiers `rank_hits` orders by, as statements about a title a reader can check.

Pure: a title and a query in, a tier or nothing out. The search path that applies them is held by
`tests/infrastructure/artifact_index/test_a_typed_title_reaches_the_window.py`.
"""

from __future__ import annotations

import pytest

from src.application.artifacts.title_match import TitleMatch, normalised_terms, title_match

_TITLE = "Artifact Index Service"


def _tier(title: str | None, query: str) -> TitleMatch | None:
    return title_match(normalised_terms(title) if title is not None else None, normalised_terms(query))


@pytest.mark.parametrize(
    ("query", "tier"),
    [
        ("Artifact Index Service", TitleMatch.EXACT),
        ("artifact, index — SERVICE!", TitleMatch.EXACT),
        ("A", TitleMatch.PREFIX),
        ("Artif", TitleMatch.PREFIX),
        ("Artifact Ind", TitleMatch.PREFIX),
        ("artifact index", TitleMatch.PREFIX),
        ("Index", TitleMatch.WORD_PREFIXES),
        ("ind serv", TitleMatch.WORD_PREFIXES),
        ("service artifact", TitleMatch.WORD_PREFIXES),
        ("dex", TitleMatch.INFIX),
        ("ct index ser", TitleMatch.INFIX),
        ("Indexes", None),
        ("de", None),
        ("graph", None),
    ],
)
def test_each_tier_says_something_true_of_the_title(query: str, tier: TitleMatch | None) -> None:
    assert _tier(_TITLE, query) is tier


def test_the_tiers_order_closest_first() -> None:
    assert list(TitleMatch) == sorted(TitleMatch)
    assert TitleMatch.EXACT < TitleMatch.PREFIX < TitleMatch.WORD_PREFIXES < TitleMatch.INFIX


def test_an_empty_query_matches_no_title() -> None:
    """Otherwise every record would be in the closest tier for a query of punctuation."""
    assert _tier(_TITLE, "") is None
    assert _tier(_TITLE, " — ") is None


def test_a_record_without_a_title_matches_nothing() -> None:
    """A connection has no title; it must not "equal" an empty one."""
    assert _tier(None, "index") is None
    assert _tier("", "index") is None


def test_a_synonym_is_not_a_title_match() -> None:
    """The scored path expands `view` to `diagram`; a tier does not, or its sentence stops being true."""
    assert _tier("Layered diagram", "layered view") is None


# ── order within a tier ──────────────────────────────────────────────────────


def _named(n: int, name: str):  # noqa: ANN202 - a test-local record builder
    from pathlib import Path

    from src.domain.ontology_representation.artifact_types import EntityRecord

    return EntityRecord(
        artifact_id=f"APP@{n}", artifact_type="application-component", name=name,
        version="0.1.0", status="active", domain="application", subdomain="", path=Path("e.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label=name, display_alias=f"APP{n}",
    )


def test_a_shorter_title_that_only_contains_the_word_comes_first() -> None:
    """Where the title only contains what was typed, the shorter title is nearer to it, whatever the
    bodies scored — a common word must not leave `Repository` behind longer titles."""
    from src.application.artifacts._ranking import rank_hits
    from src.domain.ontology_representation.artifact_types import SearchHit

    hits = [
        SearchHit(9.0, "entity", _named(1, "Engagement Repository Write Coordination")),
        SearchHit(5.0, "entity", _named(2, "Enterprise Repository")),
        SearchHit(7.0, "entity", _named(3, "Shared Repository Index")),
    ]
    ranked = [hit.record.name for hit in rank_hits(hits, "repository", limit=3, prefer_rt=None)]
    assert ranked == ["Enterprise Repository", "Shared Repository Index", "Engagement Repository Write Coordination"]


def test_a_title_that_begins_with_the_query_keeps_the_scorers_order() -> None:
    from src.application.artifacts._ranking import rank_hits
    from src.domain.ontology_representation.artifact_types import SearchHit

    hits = [
        SearchHit(5.0, "entity", _named(1, "Repository")),
        SearchHit(9.0, "entity", _named(2, "Repository Write Coordination")),
    ]
    ranked = [hit.record.name for hit in rank_hits(hits, "repo", limit=2, prefer_rt=None)]
    assert ranked == ["Repository Write Coordination", "Repository"]
