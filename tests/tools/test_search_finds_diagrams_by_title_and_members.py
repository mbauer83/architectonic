"""A diagram is findable by its title and by the entities it draws, in the served result window.

Every part of this already worked except the last step. `_diagram_fts` indexes a diagram's title, its
type and the *names of its member entities* — so the index ranks a diagram searched for by its exact
title top of its kind — and `_rank_balanced` round-robins across kinds precisely because bm25 and the
token-match supplement are incomparable scales.

The REST layer then re-sorted, putting every non-entity record behind every entity. With a window of
twenty and forty entity hits, a diagram could not appear at all: searching a diagram's exact title
returned forty entities and none of it. Two deciders, and the second overrode a guarantee it did not
know about.

Stated over the real repository, and therefore about invariants rather than counts: which diagram is
top of its kind for a given title is content, and a test that pinned it would fail the day someone
authors another diagram — the false regression this project's own convention forbids.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest


@lru_cache(maxsize=1)
def _repo():
    root = Path("engagements/ENG-ARCH-REPO/architecture-repository").resolve()
    if not root.exists():  # pragma: no cover - present in this checkout
        pytest.skip("engagement repository not available")
    from src.infrastructure.write.artifact_write._artifact_deduplication import get_repository

    return get_repository(root)


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    return build_runtime_catalogs(build_module_registry())


def _served(query: str, limit: int = 20) -> list:
    """What the route hands back: the use case's ranking, then the global-search policy."""
    from src.infrastructure.rest.routers._global_search import (
        filter_global_hits,
        hidden_diagram_entity_types,
        prioritize_global_hits,
    )

    result = _repo().search_artifacts(
        query,
        limit=limit * 3,
        include_connections=False,
        excluded_entity_types=hidden_diagram_entity_types(_catalogs()),
    )
    visible = filter_global_hits(result.hits, _catalogs())
    return prioritize_global_hits(visible)[:limit]


def _kinds(hits) -> set[str]:
    return {hit.record_type for hit in hits}


class TestADiagramSurvivesTheWindow:
    def test_searching_a_diagram_title_returns_that_diagram(self) -> None:
        """`Why a Scratchpad` is a diagram's exact title, and the query also matches many entities —
        which is what made it the reproducing case."""
        hits = _served("Why a Scratchpad")

        diagrams = [h for h in hits if h.record_type == "diagram"]
        assert diagrams, f"no diagram in the window; kinds present: {_kinds(hits)}"
        assert any("why-a-scratchpad" in h.record.artifact_id for h in diagrams)

    def test_a_query_matching_many_entities_still_shows_other_kinds(self) -> None:
        """The starvation itself, stated without naming a count: a window filled by one kind is the
        failure, whatever the corpus size."""
        hits = _served("scratchpad")

        assert _kinds(hits) != {"entity"}, "the window is entities only"

    def test_a_diagram_is_findable_by_an_entity_it_draws(self) -> None:
        """What `_diagram_fts`'s member_names column is for. `Architecture Backend` is an entity, and
        several diagrams draw it — so a diagram must be reachable by naming its content."""
        hits = _served("Architecture Backend")

        assert [h for h in hits if h.record_type == "diagram"], (
            f"no diagram reached by the name of an entity it draws; kinds: {_kinds(hits)}"
        )


class TestWhatStaysDemoted:
    def test_a_diagram_owned_entity_does_not_outrank_model_entities(self) -> None:
        """The concern the old bucketing was really expressing, kept."""
        from src.domain.ontology_representation.artifact_types import SearchHit
        from src.infrastructure.rest.routers._global_search import prioritize_global_hits

        model, local = None, None
        for hit in _served("scratchpad", limit=60):
            if hit.record_type != "entity":
                continue
            if getattr(hit.record, "host_diagram_id", None) is None:
                model = model or hit
            else:
                local = local or hit
        if model is None or local is None:
            pytest.skip("this corpus has no pair of model and diagram-owned entity hits")

        ordered = prioritize_global_hits([local, model])

        assert ordered[0] is model
        assert isinstance(ordered[0], SearchHit)
