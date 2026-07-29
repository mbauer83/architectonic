"""Tests for find_connections_for fields projection.

The 'fields' parameter allows callers to request only specific keys from each
connection record — useful for fast deduplication checks without receiving full records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make(repo: Path, artifact_type: str, name: str) -> str:
    r = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert r["wrote"], r
    return str(r["artifact_id"])


def _connect(repo: Path, src: str, tgt: str, conn_type: str) -> None:
    mcp.artifact_add_connection(
        source_entity=src, connection_type=conn_type, target_entity=tgt, dry_run=False, repo_root=str(repo)
    )


def _find(entity_id: str, repo: Path, **kwargs):
    fn = mcp.mcp_read._tool_manager._tools["artifact_query_find_connections_for"].fn
    return fn(entity_id, repo_root=str(repo), repo_scope="engagement", **kwargs)


class TestFindConnectionsNoFields:
    def test_returns_records_for_existing_connection(self, repo: Path) -> None:
        src = _make(repo, "requirement", "Src")
        tgt = _make(repo, "outcome", "Tgt")
        _connect(repo, src, tgt, "archimate-realization")
        results = _find(src, repo)
        assert len(results) == 1

    def test_full_record_contains_expected_keys(self, repo: Path) -> None:
        src = _make(repo, "goal", "GSrc")
        tgt = _make(repo, "requirement", "GTgt")
        _connect(repo, src, tgt, "archimate-influence")
        results = _find(src, repo)
        # Connection summary records use source/target/conn_type, not source_entity etc.
        assert "source" in results[0]
        assert "target" in results[0]
        assert "conn_type" in results[0]
        assert "artifact_id" in results[0]

    def test_empty_result_for_entity_with_no_connections(self, repo: Path) -> None:
        eid = _make(repo, "driver", "Isolated")
        assert _find(eid, repo) == []

    def test_direction_filter_outbound_only(self, repo: Path) -> None:
        # archimate-influence is directed; use it so outbound ≠ inbound
        src = _make(repo, "goal", "DirSrc")
        tgt = _make(repo, "requirement", "DirTgt")
        _connect(repo, src, tgt, "archimate-influence")
        outbound = _find(src, repo, direction="outbound")
        inbound = _find(src, repo, direction="inbound")
        assert len(outbound) == 1
        assert len(inbound) == 0

    def test_symmetric_connection_appears_in_outbound_for_source(self, repo: Path) -> None:
        # archimate-association is symmetric; direction="outbound" must still return it
        # from the source entity's perspective (regression for Bug 2 — symmetric
        # connections were silently dropped by direction_bucket='symmetric' ≠ 'outbound').
        src = _make(repo, "stakeholder", "SymSrc")
        tgt = _make(repo, "driver", "SymTgt")
        _connect(repo, src, tgt, "archimate-association")
        assert _find(src, repo, direction="outbound") != []
        assert _find(tgt, repo, direction="inbound") != []
        assert _find(src, repo, direction="any") != []
        # Source should NOT appear as inbound target, target should NOT appear as outbound source
        assert _find(src, repo, direction="inbound") == []
        assert _find(tgt, repo, direction="outbound") == []


class TestFindConnectionsWithFields:
    def test_triple_field_projection(self, repo: Path) -> None:
        src = _make(repo, "requirement", "ProjSrc")
        tgt = _make(repo, "outcome", "ProjTgt")
        _connect(repo, src, tgt, "archimate-realization")
        results = _find(src, repo, fields=["source", "target", "conn_type"])
        assert results
        assert set(results[0].keys()) == {"source", "target", "conn_type"}

    def test_single_field_projection(self, repo: Path) -> None:
        src = _make(repo, "goal", "SingleSrc")
        tgt = _make(repo, "requirement", "SingleTgt")
        _connect(repo, src, tgt, "archimate-influence")
        results = _find(src, repo, fields=["conn_type"])
        assert results
        assert list(results[0].keys()) == ["conn_type"]
        assert results[0]["conn_type"] == "archimate-influence"

    def test_artifact_id_only_projection(self, repo: Path) -> None:
        src = _make(repo, "driver", "IdSrc")
        tgt = _make(repo, "assessment", "IdTgt")
        _connect(repo, src, tgt, "archimate-association")
        results = _find(src, repo, fields=["artifact_id"])
        assert results
        assert set(results[0].keys()) == {"artifact_id"}

    def test_nonexistent_field_silently_excluded(self, repo: Path) -> None:
        src = _make(repo, "requirement", "SkipSrc")
        tgt = _make(repo, "outcome", "SkipTgt")
        _connect(repo, src, tgt, "archimate-realization")
        results = _find(src, repo, fields=["conn_type", "nonexistent_key"])
        assert results
        assert "nonexistent_key" not in results[0]
        assert "conn_type" in results[0]

    def test_multiple_connections_all_projected(self, repo: Path) -> None:
        src = _make(repo, "goal", "MultiSrc")
        tgt1 = _make(repo, "requirement", "MultiTgt1")
        tgt2 = _make(repo, "requirement", "MultiTgt2")
        _connect(repo, src, tgt1, "archimate-influence")
        _connect(repo, src, tgt2, "archimate-influence")
        results = _find(src, repo, fields=["target"])
        assert len(results) == 2
        assert all(list(r.keys()) == ["target"] for r in results)

    def test_fields_and_direction_filter_combine(self, repo: Path) -> None:
        # archimate-influence is directed so outbound returns exactly 1 result
        src = _make(repo, "goal", "CombSrc")
        tgt = _make(repo, "requirement", "CombTgt")
        _connect(repo, src, tgt, "archimate-influence")
        results = _find(src, repo, direction="outbound", fields=["source", "conn_type"])
        assert results
        assert set(results[0].keys()) == {"source", "conn_type"}
