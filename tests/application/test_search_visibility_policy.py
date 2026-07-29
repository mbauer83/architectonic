"""Application-level search visibility: hidden internal entity types (GAR proxies)
never surface through any search branch — FTS, scored fallback, or kind-hit marking —
on single and combined roots, while eligible artifacts keep appearing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from tests.support.search_visibility_fixtures import (
    CAP_ID,
    DOC_ID,
    ENTERPRISE_REQ_ID,
    EXCLUDED_TYPES,
    GAR_ID,
    GAR_TYPE,
    QUERY,
    REQ_ID,
    build_engagement_repo,
    build_enterprise_repo,
    entity_md,
    write_file,
)


def _repo(root: Path) -> ArtifactRepository:
    return ArtifactRepository(shared_artifact_index(root), excluded_entity_types=EXCLUDED_TYPES)


def _hit_ids(result) -> list[str]:
    return [h.record.artifact_id for h in result.hits]


class TestFtsBranch:
    def test_gar_hidden_and_real_entity_returned(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10))
        assert REQ_ID in ids
        assert GAR_ID not in ids

    def test_unfiltered_repo_still_sees_gar(self, tmp_path: Path) -> None:
        """Sanity: the GAR is indexed and matchable — hiding it is the policy's doing."""
        root = build_engagement_repo(tmp_path)
        plain = ArtifactRepository(shared_artifact_index(root))
        assert GAR_ID in _hit_ids(plain.search_artifacts(QUERY, limit=10))

    def test_entity_type_filter_still_applies(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10, artifact_type="capability", include_documents=False))
        assert ids == [CAP_ID]

    def test_domain_filter_still_applies(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10, domain="strategy", include_documents=False))
        assert ids == [CAP_ID]

    def test_call_specific_exclusions_are_combined_with_repository_policy(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10, excluded_entity_types=frozenset({"requirement"})))
        assert REQ_ID not in ids
        assert GAR_ID not in ids


class TestExplicitHiddenTypeQuery:
    def test_explicit_gar_type_query_returns_zero_entity_hits(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        result = repo.search_artifacts(
            QUERY,
            limit=10,
            artifact_type=GAR_TYPE,
            include_connections=False,
            include_diagrams=False,
            include_documents=False,
        )
        assert result.hits == []

    def test_mixed_type_request_keeps_visible_member(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        ids = _hit_ids(
            repo.search_artifacts(QUERY, limit=10, artifact_type=[GAR_TYPE, "requirement"], include_documents=False)
        )
        assert ids == [REQ_ID]


class TestFallbackBranch:
    def test_fallback_hides_gar_when_fts_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = build_engagement_repo(tmp_path)
        index = shared_artifact_index(root)
        index.refresh()
        monkeypatch.setattr(index, "search_fts", lambda *args, **kwargs: [])
        repo = ArtifactRepository(index, excluded_entity_types=EXCLUDED_TYPES)
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10))
        assert REQ_ID in ids
        assert GAR_ID not in ids

    def test_gar_only_fts_hit_does_not_mark_entity_kind_as_hit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A store without pushdown may still emit hidden FTS rows: they must not count
        as entity hits, so the scored fallback still surfaces the eligible entity."""
        root = build_engagement_repo(tmp_path)
        index = shared_artifact_index(root)
        index.refresh()
        monkeypatch.setattr(index, "search_fts", lambda *args, **kwargs: [(GAR_ID, "entity", 5.0)])
        repo = ArtifactRepository(index, excluded_entity_types=EXCLUDED_TYPES)
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=10))
        assert GAR_ID not in ids
        assert REQ_ID in ids


class TestCombinedRoots:
    def test_combined_search_hides_gar_and_merges_both_tiers(self, tmp_path: Path) -> None:
        engagement = build_engagement_repo(tmp_path)
        enterprise = build_enterprise_repo(tmp_path)
        index = combined_artifact_index(engagement, enterprise)
        index.refresh()
        repo = ArtifactRepository(index, excluded_entity_types=EXCLUDED_TYPES)
        ids = _hit_ids(repo.search_artifacts(QUERY, limit=20))
        assert REQ_ID in ids
        assert ENTERPRISE_REQ_ID in ids
        assert GAR_ID not in ids


class TestGarFreeRepo:
    def test_policy_is_inert_without_hidden_artifacts(self, tmp_path: Path) -> None:
        root = tmp_path / "engagements" / "ENG-CLEAN" / "architecture-repository"
        write_file(
            root / "model" / "motivation" / "requirement" / f"{REQ_ID}.md",
            entity_md(REQ_ID, "requirement", "Coding Guidelines Requirement"),
        )
        repo = _repo(root)
        assert _hit_ids(repo.search_artifacts(QUERY, limit=10)) == [REQ_ID]


class TestOtherKindsUnaffected:
    def test_documents_still_returned_alongside_hidden_entities(self, tmp_path: Path) -> None:
        repo = _repo(build_engagement_repo(tmp_path))
        result = repo.search_artifacts(QUERY, limit=20)
        doc_ids = [h.record.artifact_id for h in result.hits if h.record_type == "document"]
        assert DOC_ID in doc_ids
