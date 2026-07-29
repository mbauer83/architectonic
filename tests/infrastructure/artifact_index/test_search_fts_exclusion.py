"""Adapter tests for the ``excluded_entity_types`` parameter of ``search_fts``:
the SQLite store pushes the exclusion into the prepared query (before the per-kind
LIMIT, so hidden rows never consume the result budget) and the combined view
delegates the parameter to both stores.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from tests.support.search_visibility_fixtures import (
    ENTERPRISE_REQ_ID,
    EXCLUDED_TYPES,
    GAR_ID,
    GAR_TYPE,
    QUERY,
    REQ_ID,
    build_engagement_repo,
    build_enterprise_repo,
    entity_md,
    gar_md,
    write_file,
)


class TestSqliteExclusionPushdown:
    def test_excluded_types_absent_from_fts_rows(self, tmp_path: Path) -> None:
        index = shared_artifact_index(build_engagement_repo(tmp_path))
        index.refresh()
        rows = index.search_fts(QUERY, limit=10, excluded_entity_types=EXCLUDED_TYPES)
        ids = [artifact_id for artifact_id, _, _ in rows]
        assert REQ_ID in ids
        assert GAR_ID not in ids

    def test_empty_exclusion_set_returns_all_rows(self, tmp_path: Path) -> None:
        index = shared_artifact_index(build_engagement_repo(tmp_path))
        index.refresh()
        ids = [artifact_id for artifact_id, _, _ in index.search_fts(QUERY, limit=10)]
        assert REQ_ID in ids
        assert GAR_ID in ids

    def test_hidden_rows_do_not_consume_the_per_kind_budget(self, tmp_path: Path) -> None:
        """Many strongly-matching GARs + one eligible entity: with limit=1 the eligible
        entity must fill the slot — exclusion happens before LIMIT, not after."""
        root = tmp_path / "engagements" / "ENG-BUDGET" / "architecture-repository"
        write_file(
            root / "model" / "motivation" / "requirement" / f"{REQ_ID}.md",
            entity_md(REQ_ID, "requirement", "Guidelines Requirement"),
        )
        for i in range(20):
            gar_id = f"GAR@1000000400.Bdgt{i:02d}.guidelines-proxy-{i}"
            write_file(
                root / "model" / "common" / GAR_TYPE / f"{gar_id}.md",
                gar_md(gar_id, f"Guidelines Guidelines Proxy {i}", global_artifact_id="STD@1.x.d"),
            )
        index = shared_artifact_index(root)
        index.refresh()
        rows = index.search_fts(QUERY, limit=1, excluded_entity_types=EXCLUDED_TYPES)
        assert [artifact_id for artifact_id, _, _ in rows] == [REQ_ID]


class TestCombinedDelegation:
    def test_exclusion_delegated_to_both_stores(self, tmp_path: Path) -> None:
        engagement = build_engagement_repo(tmp_path)
        enterprise = build_enterprise_repo(tmp_path)
        enterprise_gar = "GAR@1000000401.EntGar.enterprise-guidelines-proxy"
        write_file(
            enterprise / "model" / "common" / GAR_TYPE / f"{enterprise_gar}.md",
            gar_md(enterprise_gar, "Enterprise guidelines proxy", global_artifact_id="STD@1.x.d"),
        )
        combined = combined_artifact_index(engagement, enterprise)
        combined.refresh()
        rows = combined.search_fts(QUERY, limit=20, excluded_entity_types=EXCLUDED_TYPES)
        ids = [artifact_id for artifact_id, _, _ in rows]
        assert REQ_ID in ids
        assert ENTERPRISE_REQ_ID in ids
        assert GAR_ID not in ids
        assert enterprise_gar not in ids

    def test_combined_empty_exclusion_returns_gars_from_both(self, tmp_path: Path) -> None:
        engagement = build_engagement_repo(tmp_path)
        enterprise = build_enterprise_repo(tmp_path)
        enterprise_gar = "GAR@1000000401.EntGar.enterprise-guidelines-proxy"
        write_file(
            enterprise / "model" / "common" / GAR_TYPE / f"{enterprise_gar}.md",
            gar_md(enterprise_gar, "Enterprise guidelines proxy", global_artifact_id="STD@1.x.d"),
        )
        combined = combined_artifact_index(engagement, enterprise)
        combined.refresh()
        ids = [artifact_id for artifact_id, _, _ in combined.search_fts(QUERY, limit=20)]
        assert GAR_ID in ids
        assert enterprise_gar in ids
