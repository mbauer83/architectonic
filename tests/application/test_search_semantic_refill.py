"""The vector branch is subject to the same visibility policy as every other branch.

A candidate that is hidden, of a non-matching type, in a non-matching domain, or no longer in the
store must never surface through it, and an explicit request fully consumed by the exclusion set
must not consult it at all.

**These used to be refill tests, and the refill is gone with the budget that needed it.** The old
supplement admitted exactly one entity, so an ineligible leading candidate would have consumed the
whole allowance and the branch had to deepen its request past it. Under rank fusion an ineligible
candidate is simply dropped: what it costs is one rank to the candidates below it, so every eligible
candidate now surfaces and the assertions say so.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.repository import ArtifactRepository
from src.domain.ontology_representation.artifact_types import SemanticSearchProvider
from src.domain.search_records import SearchCandidate
from src.infrastructure.artifact_index import shared_artifact_index
from tests.support.search_visibility_fixtures import (
    EXCLUDED_TYPES,
    GAR_TYPE,
    entity_md,
    gar_md,
    write_file,
)

_QUERY = "zymurgy fermentation processes"  # matches no fixture name → no FTS/fallback hits

ELIGIBLE_ID = "REQ@1000000201.SemEli.eligible-requirement"
CAPABILITY_ID = "CAP@1000000202.SemCap.other-capability"
GAR_A_ID = "GAR@1000000203.SemGarA.proxy-alpha"
GAR_B_ID = "GAR@1000000204.SemGarB.proxy-beta"
GAR_C_ID = "GAR@1000000205.SemGarC.proxy-gamma"


class RecordingSemantic(SemanticSearchProvider):
    """Ranked fixture provider that records every request made of it."""

    def __init__(self, ranked: list[str]) -> None:
        self._ranked = [SearchCandidate(record_type="entity", artifact_id=aid) for aid in ranked]
        self.calls: list[int] = []

    def ranked_candidates(self, query: str, limit: int) -> list[SearchCandidate]:
        self.calls.append(limit)
        return self._ranked[:limit]


def _build_corpus(tmp_path: Path) -> Path:
    """≥ 50 entities so the semantic supplement's corpus gate opens."""
    root = tmp_path / "engagements" / "ENG-SEM" / "architecture-repository"
    write_file(
        root / "model" / "motivation" / "requirement" / f"{ELIGIBLE_ID}.md",
        entity_md(ELIGIBLE_ID, "requirement", "Eligible Requirement"),
    )
    write_file(
        root / "model" / "strategy" / "capability" / f"{CAPABILITY_ID}.md",
        entity_md(CAPABILITY_ID, "capability", "Other Capability"),
    )
    for gar_id, name in ((GAR_A_ID, "Proxy Alpha"), (GAR_B_ID, "Proxy Beta"), (GAR_C_ID, "Proxy Gamma")):
        write_file(
            root / "model" / "common" / GAR_TYPE / f"{gar_id}.md",
            gar_md(gar_id, name, global_artifact_id="STD@1.x.d"),
        )
    for i in range(50):
        aid = f"REQ@1000000300.Fill{i:02d}.filler-requirement-{i}"
        write_file(
            root / "model" / "motivation" / "requirement" / f"{aid}.md",
            entity_md(aid, "requirement", f"Filler Requirement {i}"),
        )
    return root


def _repo(root: Path, semantic: SemanticSearchProvider) -> ArtifactRepository:
    return ArtifactRepository(
        shared_artifact_index(root), semantic_provider=semantic, excluded_entity_types=EXCLUDED_TYPES
    )


def _entity_ids(result) -> list[str]:
    return [h.record.artifact_id for h in result.hits if h.record_type == "entity"]


class TestIneligibleCandidatesNeverSurface:
    def test_a_hidden_candidate_is_dropped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([GAR_A_ID, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_several_hidden_candidates_are_all_dropped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([GAR_A_ID, GAR_B_ID, GAR_C_ID, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_a_candidate_of_the_wrong_type_is_dropped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([CAPABILITY_ID, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(
            _QUERY, limit=10, artifact_type="requirement"
        )
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_a_candidate_in_the_wrong_domain_is_dropped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([CAPABILITY_ID, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10, domain="motivation")
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_a_candidate_no_longer_in_the_store_is_dropped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic(["REQ@9999999999.Absent.not-in-store", ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_a_provider_offering_only_hidden_candidates_contributes_nothing(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([GAR_A_ID, GAR_B_ID, GAR_C_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == []
        assert len(sem.calls) == 1


class TestEveryEligibleCandidateSurfaces:
    """What the bound of one used to prevent."""

    def test_more_than_one_candidate_reaches_the_reader(self, tmp_path: Path) -> None:
        filler = "REQ@1000000300.Fill00.filler-requirement-0"
        sem = RecordingSemantic([ELIGIBLE_ID, filler])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert set(_entity_ids(result)) == {ELIGIBLE_ID, filler}

    def test_the_provider_order_survives_where_nothing_else_ranks_them(self, tmp_path: Path) -> None:
        """No keyword branch matches this query, so fusion is reading one list and must not reorder it."""
        filler = "REQ@1000000300.Fill00.filler-requirement-0"
        sem = RecordingSemantic([filler, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [filler, ELIGIBLE_ID]

    def test_a_hidden_leader_costs_a_rank_but_not_the_order(self, tmp_path: Path) -> None:
        filler = "REQ@1000000300.Fill00.filler-requirement-0"
        sem = RecordingSemantic([GAR_A_ID, filler, ELIGIBLE_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [filler, ELIGIBLE_ID]


class TestEmptyEffectiveRequest:
    def test_explicit_hidden_type_query_skips_semantic_entirely(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([GAR_A_ID])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(
            _QUERY,
            limit=10,
            artifact_type=GAR_TYPE,
            include_connections=False,
            include_diagrams=False,
            include_documents=False,
        )
        assert result.hits == []
        assert sem.calls == []
