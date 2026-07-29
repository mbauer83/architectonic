"""Tests for diagram-to-model sync.

Covers:
- Stale entity IDs are returned in removed_entity_ids
- Stale connection IDs are returned in removed_connection_ids
- Surviving entities/connections stay in entity-ids-used frontmatter
- dry_run=True returns content without writing
- MCP artifact_edit_diagram dispatches to sync when puml="auto-sync"
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
import pytest
import yaml

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.diagram_sync import sync_diagram_to_model


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="requirement",
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _make_diagram(repo: Path, name: str, entity_ids: list[str]) -> str:
    """Write a diagram file directly so we can control entity-ids-used frontmatter.

    Entity IDs may be stale (already deleted) — that is intentional for sync tests.
    """
    import yaml as _yaml

    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000000.tstXX.{slug}"
    entity_ids_yaml = cast(str, _yaml.dump(entity_ids, default_flow_style=True)).strip()
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: {entity_ids_yaml}
connection-ids-used: []
---
@startuml {slug}
top to bottom direction
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


def _std_alias(artifact_id: str) -> str:
    prefix_part, random_part, *_ = artifact_id.split(".")
    prefix = prefix_part.split("@", 1)[0]
    return f"{prefix}_{random_part}"


def _delete_entity(repo: Path, artifact_id: str) -> None:
    """Delete an entity that is NOT referenced by any diagram (no dependency conflict)."""
    result = mcp.artifact_bulk_delete(
        items=[{"op": "delete_entity", "artifact_id": artifact_id}],
        dry_run=False,
        repo_root=str(repo),
    )
    results = result.get("results", [])
    assert results and results[0].get("wrote"), result


def _fresh_store(repo: Path) -> ArtifactRepository:
    return ArtifactRepository(shared_artifact_index(repo))


def _read_entity_ids_used(repo: Path, diagram_id: str) -> list[str]:
    path = repo / "diagram-catalog" / "diagrams" / f"{diagram_id}.puml"
    text = path.read_text()
    fm_text = text.split("---")[1]
    fm = yaml.safe_load(fm_text)
    return list(fm.get("entity-ids-used") or [])


def _make_context(repo: Path):  # type: ignore[return]
    from src.infrastructure.mcp.artifact_mcp.context import (
        clear_caches_for_repo,
        resolve_repo_roots,
        roots_key,
        verifier_for,
    )

    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=str(repo),
        repo_preset=None,
        enterprise_root=None,
    )
    verifier = verifier_for(roots_key(roots), include_registry=False)
    return verifier, clear_caches_for_repo


# ---------------------------------------------------------------------------
# sync_diagram_to_model (write-layer)
# ---------------------------------------------------------------------------


class TestSyncDiagramToModel:
    def test_stale_entity_reported_in_removed_ids(self, repo: Path) -> None:
        # Create both, delete e2 BEFORE the diagram is written so no dependency
        # conflict blocks the delete; diagram then has a stale reference to e2.
        e1 = _make_entity(repo, "Keep Me")
        e2 = _make_entity(repo, "Delete Me")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Sync Test Diagram", [e1, e2])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert e2 in result.removed_entity_ids
        assert e1 not in result.removed_entity_ids
        assert result.removed_connection_ids == []

    def test_surviving_entity_kept_in_frontmatter(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Survivor")
        e2 = _make_entity(repo, "Gone")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Survivor Diagram", [e1, e2])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert result.wrote is True
        ids_in_fm = _read_entity_ids_used(repo, diag_id)
        assert e1 in ids_in_fm
        assert e2 not in ids_in_fm

    def test_dry_run_does_not_modify_file(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Only Entity")
        _delete_entity(repo, e1)
        diag_id = _make_diagram(repo, "Dry Run Sync", [e1])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        before = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        after = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()
        assert result.wrote is False
        assert before == after
        assert result.removed_entity_ids == [e1]

    def test_no_stale_ids_means_empty_removed_lists(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Still Here")
        diag_id = _make_diagram(repo, "Clean Diagram", [e1])

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert result.removed_entity_ids == []
        assert result.removed_connection_ids == []

    def test_renamed_entity_is_updated_not_removed(self, repo: Path) -> None:
        # e1 gets created, its old ID goes into a diagram, then it is renamed.
        # Sync should follow the stable prefix and keep the entity (with the new ID),
        # not treat it as deleted.
        e1_old = _make_entity(repo, "Original Name")
        diag_id = _make_diagram(repo, "Rename Test Diagram", [e1_old])

        # Rename via MCP — produces a new artifact_id with a different slug
        rename_result = mcp.artifact_edit_entity(
            artifact_id=e1_old,
            name="New Name",
            dry_run=False,
            repo_root=str(repo),
        )
        assert rename_result["wrote"], rename_result
        e1_new = str(rename_result["artifact_id"])
        assert e1_new != e1_old, "rename must produce a new artifact_id"

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)

        result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        # The entity must NOT appear in removed_entity_ids
        assert e1_old not in result.removed_entity_ids
        assert e1_new not in result.removed_entity_ids
        # The diagram frontmatter must reference the NEW id
        ids_in_fm = _read_entity_ids_used(repo, diag_id)
        assert e1_new in ids_in_fm
        assert e1_old not in ids_in_fm

    def test_visible_stale_relation_is_removed_even_without_frontmatter_connection_id(self, repo: Path) -> None:
        src = _make_entity(repo, "Source")
        tgt = _make_entity(repo, "Target")
        _ = mcp.artifact_add_connection(
            source_entity=src,
            connection_type="archimate-influence",
            target_entity=tgt,
            dry_run=False,
            repo_root=str(repo),
        )
        result = mcp.artifact_bulk_delete(
            items=[
                {
                    "op": "delete_connection",
                    "source_entity": src,
                    "connection_type": "archimate-influence",
                    "target_entity": tgt,
                }
            ],
            dry_run=False,
            repo_root=str(repo),
        )
        assert result.get("results"), result

        src_alias = _std_alias(src)
        tgt_alias = _std_alias(tgt)
        diag_id = "DIA@1777000000.tstXX.visible-stale-relation"
        path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        path.write_text(
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "Visible Stale Relation"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: [{src}, {tgt}]
connection-ids-used: []
---
@startuml {diag_id}
rectangle "Source" <<Requirement>> as {src_alias}
rectangle "Target" <<Requirement>> as {tgt_alias}
Rel_Influence({src_alias}, {tgt_alias}, "")
@enduml
""",
            encoding="utf-8",
        )

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)
        sync_result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert sync_result.deleted_diagram is False
        assert f"{src}---{tgt}@@archimate-influence" in sync_result.removed_connection_ids
        text = path.read_text(encoding="utf-8")
        assert "Rel_Influence(" not in text

    def test_sync_does_not_delete_diagram_when_puml_entities_still_exist(self, repo: Path) -> None:
        src = _make_entity(repo, "Alive Source")
        tgt = _make_entity(repo, "Alive Target")
        src_alias = _std_alias(src)
        tgt_alias = _std_alias(tgt)
        diag_id = "DIA@1777000000.tstXX.puml-entities-survive"
        path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
        path.write_text(
            f"""\
---
artifact-id: {diag_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "PUML Entities Survive"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
---
@startuml {diag_id}
rectangle "Source" <<Requirement>> as {src_alias}
rectangle "Target" <<Requirement>> as {tgt_alias}
Rel_Influence({src_alias}, {tgt_alias}, "")
@enduml
""",
            encoding="utf-8",
        )

        store = _fresh_store(repo)
        verifier, clear_caches = _make_context(repo)
        sync_result = sync_diagram_to_model(
            repo_root=repo,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert sync_result.deleted_diagram is False
        assert path.exists()
        assert sync_result.removed_connection_ids == [f"{src}---{tgt}@@archimate-influence"]


# ---------------------------------------------------------------------------
# MCP artifact_edit_diagram with puml="auto-sync"
# ---------------------------------------------------------------------------


class TestMcpAutoSyncDispatch:
    def test_auto_sync_removes_stale_entity_via_mcp(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Present")
        e2 = _make_entity(repo, "Absent")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "MCP Sync Diagram", [e1, e2])

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=False,
            repo_root=str(repo),
        )

        assert result["wrote"] is True
        removed = cast(list[str], result.get("removed_entity_ids", []))
        assert e2 in removed
        assert e1 not in removed

    def test_auto_sync_dry_run_does_not_write(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Kept")
        e2 = _make_entity(repo, "Removed")
        _delete_entity(repo, e2)
        diag_id = _make_diagram(repo, "Dry Sync Via MCP", [e1, e2])

        before = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=True,
            repo_root=str(repo),
        )

        after = (repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml").read_text()
        assert result["wrote"] is False
        assert before == after
        assert "removed_entity_ids" in result

    def test_auto_sync_result_includes_removed_keys(self, repo: Path) -> None:
        e1 = _make_entity(repo, "Alpha")
        diag_id = _make_diagram(repo, "Keys Check", [e1])

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=True,
            repo_root=str(repo),
        )

        assert "removed_entity_ids" in result
        assert "removed_connection_ids" in result
