"""Semantic-supplement refill: leading candidates that are hidden, of a non-matching
type, or in a non-matching domain must not consume the semantic result budget — the
supplement refills past them, preserving provider ranking; an explicit request fully
consumed by the exclusion set skips semantic search entirely.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_repository import ArtifactRepository
from src.domain.ontology_representation.artifact_types import SemanticSearchProvider
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
    """Ranked fixture provider that records every top_k request."""

    def __init__(self, ranked: list[tuple[float, str]]) -> None:
        self._ranked = ranked
        self.calls: list[int] = []

    def top_k(self, query: str, k: int, *, threshold: float = 0.75) -> list[tuple[float, str]]:
        self.calls.append(k)
        return [(score, aid) for score, aid in self._ranked if score >= threshold][:k]


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


class TestRefillPastIneligibleCandidates:
    def test_leading_gar_does_not_consume_budget(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.95, GAR_A_ID), (0.9, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_multiple_leading_gars_are_all_skipped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.97, GAR_A_ID), (0.96, GAR_B_ID), (0.95, GAR_C_ID), (0.9, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_leading_wrong_type_candidate_is_skipped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.95, CAPABILITY_ID), (0.9, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(
            _QUERY, limit=10, artifact_type="requirement"
        )
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_leading_wrong_domain_candidate_is_skipped(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.95, CAPABILITY_ID), (0.9, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10, domain="motivation")
        assert _entity_ids(result) == [ELIGIBLE_ID]

    def test_provider_ranking_preserved_for_first_eligible(self, tmp_path: Path) -> None:
        """The FIRST eligible candidate wins, not a later higher-typed one."""
        filler_id = "REQ@1000000300.Fill00.filler-requirement-0"
        sem = RecordingSemantic([(0.95, GAR_A_ID), (0.9, filler_id), (0.89, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [filler_id]


class TestEmptyEffectiveRequest:
    def test_explicit_hidden_type_query_skips_semantic_entirely(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.95, GAR_A_ID)])
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


class TestRefillTermination:
    def test_provider_with_only_hidden_candidates_yields_no_entity_hits(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.97, GAR_A_ID), (0.96, GAR_B_ID), (0.95, GAR_C_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == []
        assert len(sem.calls) >= 1

    def test_unknown_candidate_ids_are_refilled_past(self, tmp_path: Path) -> None:
        sem = RecordingSemantic([(0.95, "REQ@9999999999.Absent.not-in-store"), (0.9, ELIGIBLE_ID)])
        result = _repo(_build_corpus(tmp_path), sem).search_artifacts(_QUERY, limit=10)
        assert _entity_ids(result) == [ELIGIBLE_ID]
