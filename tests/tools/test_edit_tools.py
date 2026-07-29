"""Behavioural tests for entity, connection, and diagram edit/delete MCP tools.

 Covers model_edit_entity, model_delete_entity, model_edit_connection (remove),
 and model_edit_diagram / model_delete_diagram
via the MCP server interface, exercising dry-run and live writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.artifact_write import generate_diagram_id
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    root = _repo_root_for(path)
    if root is not None:
        shared_artifact_index(root).apply_file_changes([path])


def _repo_root_for(path: Path) -> Path | None:
    return next((parent for parent in path.parents if parent.name == "architecture-repository"), None)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type,
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _make_connection(repo: Path, src: str, tgt: str, conn_type: str) -> None:
    result = mcp.artifact_add_connection(
        source_entity=src,
        connection_type=conn_type,
        target_entity=tgt,
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result


# ---------------------------------------------------------------------------
# model_edit_entity
# ---------------------------------------------------------------------------


class TestEditEntity:
    def test_dry_run_returns_preview_content(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "Original Name")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            name="New Name",
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "New Name" in str(result.get("content", ""))

    def test_live_edit_name_updates_file(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "First Name")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            name="Updated Name",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        path = Path(str(result["path"]))
        content = path.read_text()
        assert "Updated Name" in content
        assert "name: Updated Name" in content

    def test_edit_renames_artifact_id_slug_and_path(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "Preserve Me")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            name="New Name",
            dry_run=False,
            repo_root=str(repo),
        )
        path = Path(str(result["path"]))
        new_id = str(result["artifact_id"])
        assert new_id != eid
        assert new_id.endswith(".new-name")
        assert path.name == f"{new_id}.md"
        assert new_id in path.read_text()

    def test_edit_entity_renames_owned_outgoing_and_updates_references(self, repo: Path) -> None:
        src = _make_entity(repo, "requirement", "Source Name")
        tgt = _make_entity(repo, "outcome", "Target Name")
        other = _make_entity(repo, "goal", "Other Name")
        _make_connection(repo, src, tgt, "archimate-realization")
        _make_connection(repo, other, src, "archimate-association")

        old_entity_path = next((repo / "model").rglob(f"{src}.md"))
        old_outgoing_path = old_entity_path.with_suffix(".outgoing.md")
        other_outgoing_path = next((repo / "model").rglob(f"{other}.outgoing.md"))

        result = mcp.artifact_edit_entity(
            artifact_id=src,
            name="Renamed Source",
            dry_run=False,
            repo_root=str(repo),
        )

        new_id = str(result["artifact_id"])
        new_entity_path = Path(str(result["path"]))
        new_outgoing_path = new_entity_path.with_suffix(".outgoing.md")

        assert not old_entity_path.exists()
        assert not old_outgoing_path.exists()
        assert new_entity_path.exists()
        assert new_outgoing_path.exists()
        assert new_id in new_entity_path.read_text()
        assert new_id in new_outgoing_path.read_text()
        assert src not in new_outgoing_path.read_text()
        assert new_id in other_outgoing_path.read_text()
        assert src not in other_outgoing_path.read_text()

    def test_model_registry_uses_canonical_connection_artifact_ids(self, repo: Path) -> None:
        src = _make_entity(repo, "driver", "Source Driver")
        tgt = _make_entity(repo, "assessment", "Target Assessment")
        _make_connection(repo, src, tgt, "archimate-influence")

        registry = ArtifactRegistry(shared_artifact_index([repo]))
        expected = f"{stable_id(src)}---{stable_id(tgt)}@@archimate-influence"

        assert expected in registry.connection_ids()

    def test_edit_nonexistent_entity_raises(self, repo: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            mcp.artifact_edit_entity(
                artifact_id="REQ@9999999999.NoExist.ghost",
                name="X",
                dry_run=False,
                repo_root=str(repo),
            )

    def test_edit_status(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "Status Test")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            status="active",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert "active" in Path(str(result["path"])).read_text()

    def test_edit_keywords(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "KW Test")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            keywords=["alpha", "beta"],
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        content = Path(str(result["path"])).read_text()
        assert "alpha" in content and "beta" in content

    def test_cannot_edit_global_entity_reference_directly(self, repo: Path) -> None:
        # GRF entities are auto-managed; direct creation is blocked at create_entity,
        # but we confirm the type guard is in place
        with pytest.raises(ValueError, match="global-entity-reference"):
            mcp.artifact_create_entity(
                artifact_type="global-entity-reference",
                name="Should Fail",
                dry_run=False,
                repo_root=str(repo),
            )


class TestDeleteEntity:
    def test_delete_entity_dry_run_returns_preview(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "Delete Me")
        result = mcp.artifact_delete_entity(
            artifact_id=eid,
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "Would delete entity" in str(result.get("content", ""))

    def test_delete_entity_removes_entity_and_owned_outgoing(self, repo: Path) -> None:
        src = _make_entity(repo, "requirement", "Source")
        tgt = _make_entity(repo, "outcome", "Target")
        _make_connection(repo, src, tgt, "archimate-realization")

        entity_path = next((repo / "model").rglob(f"{src}.md"))
        outgoing_path = entity_path.with_suffix(".outgoing.md")
        assert entity_path.exists()
        assert outgoing_path.exists()

        result = mcp.artifact_delete_entity(
            artifact_id=src,
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert not entity_path.exists()
        assert not outgoing_path.exists()

    def test_delete_entity_resolves_short_form_id(self, repo: Path) -> None:
        """Regression: registry.find_file_by_id previously did an exact-key lookup
        only, so a short id (no trailing .slug) always reported "not found"."""
        eid = _make_entity(repo, "requirement", "Delete Via Short Id")
        entity_path = next((repo / "model").rglob(f"{eid}.md"))
        assert entity_path.exists()

        result = mcp.artifact_delete_entity(
            artifact_id=stable_id(eid),
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert not entity_path.exists()

    def test_delete_entity_blocked_by_incoming_connection_tree(self, repo: Path) -> None:
        src = _make_entity(repo, "requirement", "Incoming Src")
        tgt = _make_entity(repo, "outcome", "Blocked Tgt")
        _make_connection(repo, src, tgt, "archimate-realization")

        with pytest.raises(ValueError, match="incoming-connections"):
            mcp.artifact_delete_entity(
                artifact_id=tgt,
                dry_run=False,
                repo_root=str(repo),
            )

    def test_delete_entity_blocked_by_diagram_reference_tree(self, repo: Path) -> None:
        eid = _make_entity(repo, "requirement", "Diagram Ref Entity")
        diag_path = repo / "diagram-catalog" / "diagrams" / "ref-diagram.puml"
        _write(
            diag_path,
            f"""\
---
artifact-id: ref-diagram
artifact-type: diagram
diagram-type: activity
name: "Ref Diagram"
entity-ids-used:
  - {eid}
version: 0.1.0
status: active
last-updated: '2026-04-20'
---
@startuml
:x;
@enduml
""",
        )

        with pytest.raises(ValueError, match="diagrams"):
            mcp.artifact_delete_entity(
                artifact_id=eid,
                dry_run=False,
                repo_root=str(repo),
            )


# ---------------------------------------------------------------------------
# connection updates and removal (via edit_tools)
# ---------------------------------------------------------------------------


class TestUpdateConnection:
    def test_typed_metadata_update_preserves_description(self, repo: Path) -> None:
        source = _make_entity(repo, "requirement", "Metadata Source")
        target = _make_entity(repo, "outcome", "Metadata Target")
        added = mcp.artifact_add_connection(
            source_entity=source,
            connection_type="archimate-realization",
            target_entity=target,
            description="Existing relationship description",
            dry_run=False,
            repo_root=str(repo),
        )
        assert added["wrote"] is True

        result = mcp.artifact_edit_connection(
            source_entity=source,
            connection_type="archimate-realization",
            target_entity=target,
            metadata={"weight": 2, "enabled": True},
            dry_run=True,
            repo_root=str(repo),
        )

        preview = str(result["content"])
        assert "weight: 2" in preview
        assert "enabled: true" in preview
        assert "Existing relationship description" in preview


class TestRemoveConnection:
    def test_dry_run_remove_returns_preview(self, repo: Path) -> None:
        src = _make_entity(repo, "application-component", "SrcApp")
        tgt = _make_entity(repo, "application-component", "TgtApp")
        _make_connection(repo, src, tgt, "archimate-serving")

        result = mcp.artifact_edit_connection(
            source_entity=src,
            connection_type="archimate-serving",
            target_entity=tgt,
            operation="remove",
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False

    def test_live_remove_deletes_connection_header(self, repo: Path) -> None:
        src = _make_entity(repo, "application-component", "SrcDel")
        tgt = _make_entity(repo, "application-component", "TgtDel")
        _make_connection(repo, src, tgt, "archimate-serving")

        result = mcp.artifact_edit_connection(
            source_entity=src,
            connection_type="archimate-serving",
            target_entity=tgt,
            operation="remove",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        outgoing_path = Path(str(result["path"]))
        # File may be deleted entirely when last connection removed, or connection header absent
        if outgoing_path.exists():
            assert f"archimate-serving → {tgt}" not in outgoing_path.read_text()
        # Either way the connection is gone

    def test_remove_nonexistent_connection_raises(self, repo: Path) -> None:
        src = _make_entity(repo, "application-component", "SrcOnly")
        with pytest.raises((ValueError, Exception)):
            mcp.artifact_edit_connection(
                source_entity=src,
                connection_type="archimate-serving",
                target_entity="APP@9999999999.NoExist.ghost",
                operation="remove",
                dry_run=False,
                repo_root=str(repo),
            )


# ---------------------------------------------------------------------------
# model_edit_diagram
# ---------------------------------------------------------------------------


class TestEditDiagram:
    def _make_diagram(self, repo: Path, name: str) -> str:
        # Use activity diagram type — no archimate !include required
        artifact_id = generate_diagram_id("activity", name)
        puml = f"""\
@startuml {artifact_id}

title {name}

:Step A;
:Step B;

@enduml
"""
        result = mcp.artifact_create_diagram(
            diagram_type="activity",
            name=name,
            puml=puml,
            artifact_id=artifact_id,
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"], result
        return str(result["artifact_id"])

    def test_edit_diagram_name_updates_title(self, repo: Path) -> None:
        diag_id = self._make_diagram(repo, "Original Diagram")
        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            name="Updated Diagram",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        content = Path(str(result["path"])).read_text()
        assert "Updated Diagram" in content

    def test_edit_diagram_dry_run_returns_preview(self, repo: Path) -> None:
        diag_id = self._make_diagram(repo, "Dry Run Diagram")
        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            name="New Title",
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "New Title" in str(result.get("content", ""))


class TestDeleteDiagram:
    def test_delete_diagram_dry_run_returns_preview(self, repo: Path) -> None:
        diag_id = TestEditDiagram()._make_diagram(repo, "Delete Dry Diagram")
        result = mcp.artifact_delete_diagram(
            artifact_id=diag_id,
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "Would delete diagram" in str(result.get("content", ""))

    def test_delete_diagram_removes_source_and_rendered_files(self, repo: Path) -> None:
        diag_id = TestEditDiagram()._make_diagram(repo, "Delete Live Diagram")
        diag_path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        rendered_dir = repo / "diagram-catalog" / "rendered"
        rendered_dir.mkdir(parents=True, exist_ok=True)
        png = rendered_dir / f"{diag_id}.png"
        svg = rendered_dir / f"{diag_id}.svg"
        png.write_text("png", encoding="utf-8")
        svg.write_text("svg", encoding="utf-8")

        result = mcp.artifact_delete_diagram(
            artifact_id=diag_id,
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert not diag_path.exists()
        assert not png.exists()
        assert not svg.exists()
