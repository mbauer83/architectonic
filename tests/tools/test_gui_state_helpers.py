"""Unit tests for GUI router state.py helper functions.

Covers the branches and functions not reached through HTTP tests:
uninitialized-state errors, enterprise-root paths, entity_to_summary,
connection_to_dict, diagram_to_summary, get_both_roots, resolve_gar.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.ontology_representation.artifact_types import ConnectionRecord, DiagramRecord, EntityRecord
from src.infrastructure.rest.routers import state as s

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_entity(
    artifact_id: str = "REQ@1.AA.req",
    name: str = "My Req",
    path: Path | None = None,
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="requirement",
        name=name,
        version="0.1.0",
        status="active",
        domain="motivation",
        subdomain="requirement",
        path=path or Path("/tmp/repo/model/motivation/requirement/REQ@1.AA.req.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias="REQ_AA",
    )


def _make_connection(
    source: str = "REQ@1.AA.src",
    target: str = "REQ@2.BB.tgt",
    conn_type: str = "archimate-association",
    content_text: str = "",
) -> ConnectionRecord:
    artifact_id = f"{source}---{target}@@{conn_type}"
    return ConnectionRecord(
        artifact_id=artifact_id,
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="active",
        path=Path("/tmp/repo/model/motivation/requirement/src.outgoing.md"),
        extra={},
        content_text=content_text,
    )


def _make_diagram(artifact_id: str = "DIAG@1.CC.diag", name: str = "My Diag") -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type="diagram",
        name=name,
        diagram_type="component",
        version="0.1.0",
        status="draft",
        path=Path("/tmp/repo/diagram-catalog/diagrams/DIAG@1.CC.diag.md"),
        extra={},
    )


# ── state initialization ──────────────────────────────────────────────────────


class TestInitState:
    def test_sets_repo_and_roots(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        root = tmp_path / "engagements" / "ENG-S" / "architecture-repository"
        root.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([root]))
        s.init_state(repo, root, None)
        assert s.maybe_engagement_root() == root
        assert s.maybe_enterprise_root() is None
        assert s.is_admin_mode() is False
        assert s.is_read_only() is False

    def test_admin_mode(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        root = tmp_path / "engagements" / "ENG-S2" / "architecture-repository"
        root.mkdir(parents=True)
        ent = tmp_path / "enterprise-repository"
        ent.mkdir()
        repo = ArtifactRepository(shared_artifact_index([root]))
        s.init_state(repo, root, ent, admin_mode=True)
        assert s.is_admin_mode() is True

    def test_read_only(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        root = tmp_path / "engagements" / "ENG-S3" / "architecture-repository"
        root.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([root]))
        s.init_state(repo, root, None, read_only=True)
        assert s.is_read_only() is True


# ── configured_roots ──────────────────────────────────────────────────────────


class TestConfiguredRoots:
    def test_with_enterprise_root(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-CR" / "architecture-repository"
        ent = tmp_path / "enterprise-repository"
        eng.mkdir(parents=True)
        ent.mkdir()
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, ent)
        roots = s.configured_roots()
        assert len(roots) == 2

    def test_without_enterprise_root(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-CR2" / "architecture-repository"
        eng.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, None)
        roots = s.configured_roots()
        assert len(roots) == 1


# ── is_global ─────────────────────────────────────────────────────────────────


class TestIsGlobal:
    def test_path_under_enterprise_root(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-IG" / "architecture-repository"
        ent = tmp_path / "enterprise-repository"
        eng.mkdir(parents=True)
        ent.mkdir()
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, ent)
        global_path = ent / "model" / "motivation" / "REQ@2.BB.bb.md"
        global_path.parent.mkdir(parents=True)
        global_path.touch()
        assert s.is_global(global_path) is True

    def test_engagement_path_is_not_global(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-IG2" / "architecture-repository"
        ent = tmp_path / "enterprise-repository"
        eng.mkdir(parents=True)
        ent.mkdir()
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, ent)
        local_path = eng / "model" / "REQ@1.AA.aa.md"
        assert s.is_global(local_path) is False


# ── entity_to_summary ─────────────────────────────────────────────────────────


class TestEntityToSummary:
    def test_without_conn_counts(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-ES" / "architecture-repository"
        eng.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, None)
        entity = _make_entity()
        result = s.entity_to_summary(entity)
        assert result["artifact_id"] == entity.artifact_id
        assert "conn_in" not in result

    def test_with_conn_counts(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-ES2" / "architecture-repository"
        eng.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, None)
        entity = _make_entity()
        counts = {entity.artifact_id: (2, 1, 3)}
        result = s.entity_to_summary(entity, conn_counts=counts)
        assert result["conn_in"] == 2
        assert result["conn_sym"] == 1
        assert result["conn_out"] == 3


# ── connection_to_dict ────────────────────────────────────────────────────────


class TestConnectionToDict:
    def test_basic(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-CD" / "architecture-repository"
        eng.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, None)
        conn = _make_connection()
        result = s.connection_to_dict(conn)
        assert result["artifact_id"] == conn.artifact_id
        assert result["conn_type"] == "archimate-association"
        assert "source_name" in result
        assert "target_name" in result


# ── diagram_to_summary ────────────────────────────────────────────────────────


class TestDiagramToSummary:
    def test_basic(self) -> None:
        diag = _make_diagram()
        result = s.diagram_to_summary(diag)
        assert result["artifact_id"] == diag.artifact_id
        assert result["name"] == diag.name
        assert result["diagram_type"] == "component"


# ── get_both_roots ────────────────────────────────────────────────────────────


class TestGetBothRoots:
    def test_raises_when_enterprise_missing(self, tmp_path: Path) -> None:
        from src.application.artifacts.query import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index

        eng = tmp_path / "engagements" / "ENG-BR" / "architecture-repository"
        eng.mkdir(parents=True)
        repo = ArtifactRepository(shared_artifact_index([eng]))
        s.init_state(repo, eng, None)
        with pytest.raises(Exception):
            s.get_both_roots()


# ── write_result_to_dict ──────────────────────────────────────────────────────


class TestWriteResultToDict:
    def test_converts_result(self) -> None:
        mock_result = MagicMock()
        mock_result.wrote = True
        mock_result.path = Path("/tmp/some/path.md")
        mock_result.artifact_id = "REQ@1.AA.req"
        mock_result.content = "content"
        mock_result.warnings = []
        mock_result.verification = {}
        result = s.write_result_to_dict(mock_result)
        assert result["wrote"] is True
        assert result["artifact_id"] == "REQ@1.AA.req"
        assert "path" in result
