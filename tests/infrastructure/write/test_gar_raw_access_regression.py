"""Raw GAR access must survive the search-visibility policy: promotion internals
(`find_existing_gar` / `build_gar_map`) and raw list/id reads keep full GAR access
even on a repository constructed with the internal-type exclusion set.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.global_artifact_reference import build_gar_map, find_existing_gar
from tests.support.search_visibility_fixtures import (
    DOC_ID,
    EXCLUDED_TYPES,
    GAR_ID,
    GAR_TYPE,
    build_engagement_repo,
)


def _policy_repo(root: Path) -> ArtifactRepository:
    return ArtifactRepository(shared_artifact_index(root), excluded_entity_types=EXCLUDED_TYPES)


class TestPromotionInternalsSeeGars:
    def test_find_existing_gar_resolves_on_policy_bearing_repo(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        assert find_existing_gar(repo, DOC_ID) == GAR_ID

    def test_build_gar_map_contains_gar_on_policy_bearing_repo(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        assert build_gar_map(repo) == {GAR_ID: DOC_ID}


class TestRawAccessUnfiltered:
    def test_list_entities_by_type_returns_gar(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        assert [rec.artifact_id for rec in repo.list_entities(artifact_type=GAR_TYPE)] == [GAR_ID]

    def test_unfiltered_list_entities_contains_gar(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        assert GAR_ID in {rec.artifact_id for rec in repo.list_entities()}

    def test_get_entity_returns_gar(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        record = repo.get_entity(GAR_ID)
        assert record is not None
        assert record.artifact_type == GAR_TYPE

    def test_entity_ids_contains_gar(self, tmp_path: Path) -> None:
        repo = _policy_repo(build_engagement_repo(tmp_path))
        assert GAR_ID in repo.entity_ids()
