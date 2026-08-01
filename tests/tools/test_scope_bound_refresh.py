"""Tests for scope-bound (model-backed) diagram refresh safety invariants.

Covers:
- refresh_diagram on a scope-bound diagram never deletes it
- refresh_diagram re-projects from the model (entity-ids-used updated)
- dry_run is byte-for-byte non-mutating on scope-bound diagrams
- idempotent: re-projecting a diagram yields byte-stable output, the modification stamp aside
- sync_diagram_to_model raises ValueError when called on a scope-bound diagram
- ArchiMate-reconcile behavior unchanged through refresh_diagram
- MCP auto-sync and REST /api/diagrams/{artifact_id}/sync route through refresh_diagram
- standalone (non-scope-bound diagram-entities) diagram is never deleted on refresh
- ArchiMate reconcile with all-unresolved entities preserves the diagram
- REST /api/diagrams/{artifact_id}/sync adapter delegates to refresh_diagram
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.application.artifacts.repository import ArtifactRepository
from src.domain.clock import frozen_now
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.diagram_sync import (
    refresh_diagram,
    sync_diagram_to_model,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_app_entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="application-component",
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _make_archimate_diagram(repo: Path, name: str, entity_ids: list[str]) -> str:
    """Write a plain ArchiMate-reconcile diagram (no scoped-by binding)."""
    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000000.tsync.{slug}"
    entity_ids_yaml = yaml.dump(entity_ids, default_flow_style=True).strip()
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


def _make_scope_bound_diagram(repo: Path, name: str, scope_entity_id: str) -> str:
    """Write a scope-bound (model-backed) C4 diagram using the canonical bindings form."""
    slug = name.lower().replace(" ", "-")
    artifact_id = f"CSC@1777000001.tscp.{slug}"
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-system-context
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities: {{}}
bindings:
- id: bind-scope
  subject:
    kind: diagram
  correspondence_kind: scoped-by
  target:
    entity_id: {scope_entity_id}
---
@startuml {slug}
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


def _fresh_store(repo: Path) -> ArtifactRepository:
    return ArtifactRepository(shared_artifact_index(repo))


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


def _diagram_path(repo: Path, artifact_id: str) -> Path:
    return repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"


def _read_frontmatter(repo: Path, artifact_id: str) -> dict:
    text = _diagram_path(repo, artifact_id).read_text()
    fm_text = text.split("---")[1]
    return yaml.safe_load(fm_text)


# ---------------------------------------------------------------------------
# scope-bound safety: refresh_diagram never deletes
# ---------------------------------------------------------------------------


class TestScopeBoundRefreshNeverDeletes:
    def test_scope_bound_diagram_not_deleted_on_empty_model(self, repo: Path) -> None:
        """Even with an empty model (no neighbours), a scope-bound diagram must survive."""
        scope_id = _make_app_entity(repo, "Scope System")
        diag_id = _make_scope_bound_diagram(repo, "Empty Context", scope_id)

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert result.deleted_diagram is False
        assert _diagram_path(repo, diag_id).exists()

    def test_scope_bound_refresh_preserves_binding(self, repo: Path) -> None:
        """After refresh the scoped-by binding must still be present in frontmatter."""
        scope_id = _make_app_entity(repo, "Bound System")
        diag_id = _make_scope_bound_diagram(repo, "Bound Context", scope_id)

        verifier, clear_caches = _make_context(repo)
        refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        fm = _read_frontmatter(repo, diag_id)
        bindings = fm.get("bindings") or []
        scoped_by = [b for b in bindings if b.get("correspondence_kind") == "scoped-by"]
        assert scoped_by, "scoped-by binding must survive refresh"
        assert scoped_by[0]["target"]["entity_id"] == scope_id

    def test_scope_bound_refresh_updates_entity_ids_used(self, repo: Path) -> None:
        """After a successful refresh the scope entity appears in entity-ids-used."""
        scope_id = _make_app_entity(repo, "Tracked System")
        diag_id = _make_scope_bound_diagram(repo, "Tracked Context", scope_id)

        verifier, clear_caches = _make_context(repo)
        refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        fm = _read_frontmatter(repo, diag_id)
        entity_ids_used = fm.get("entity-ids-used") or []
        assert scope_id in entity_ids_used, "scope entity must appear in entity-ids-used after refresh"

    def test_sync_diagram_to_model_raises_for_scope_bound(self, repo: Path) -> None:
        """sync_diagram_to_model must raise ValueError for scope-bound diagrams."""
        scope_id = _make_app_entity(repo, "Guard System")
        diag_id = _make_scope_bound_diagram(repo, "Guard Context", scope_id)

        verifier, clear_caches = _make_context(repo)
        with pytest.raises(ValueError, match="scope-bound"):
            sync_diagram_to_model(
                repo_root=repo,
                store=_fresh_store(repo),
                verifier=verifier,
                clear_repo_caches=clear_caches,
                artifact_id=diag_id,
                dry_run=True,
            )


# ---------------------------------------------------------------------------
# dry-run is byte-for-byte non-mutating
# ---------------------------------------------------------------------------


class TestScopeBoundDryRunNonMutating:
    def test_dry_run_does_not_write(self, repo: Path) -> None:
        scope_id = _make_app_entity(repo, "Dry System")
        diag_id = _make_scope_bound_diagram(repo, "Dry Context", scope_id)
        path = _diagram_path(repo, diag_id)
        before = path.read_bytes()

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        after = path.read_bytes()
        assert result.wrote is False
        assert before == after, "dry-run must be byte-for-byte non-mutating"


# ---------------------------------------------------------------------------
# idempotency: 3x refreshes are byte-stable
# ---------------------------------------------------------------------------


class TestScopeBoundRefreshIdempotent:
    """Re-projecting the same model twice must produce the same diagram.

    The written file also records *when* it was written, so byte-equality is asserted with the
    clock pinned; the follow-up test then shows that instant is the only thing a later refresh
    moves — the projection itself does not drift.
    """

    def _refresh(self, repo: Path, verifier, clear_caches, diag_id: str) -> None:
        refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

    def test_repeated_refreshes_are_byte_stable(self, repo: Path) -> None:
        scope_id = _make_app_entity(repo, "Stable System")
        diag_id = _make_scope_bound_diagram(repo, "Stable Context", scope_id)
        path = _diagram_path(repo, diag_id)

        verifier, clear_caches = _make_context(repo)
        with frozen_now("2026-07-24T09:15:00Z"):
            for _ in range(3):
                self._refresh(repo, verifier, clear_caches, diag_id)
            bytes_after_3 = path.read_bytes()

            self._refresh(repo, verifier, clear_caches, diag_id)
            bytes_after_4 = path.read_bytes()

        assert bytes_after_3 == bytes_after_4, "repeated refreshes must be idempotent"

    def test_a_later_refresh_moves_only_the_modification_stamp(self, repo: Path) -> None:
        scope_id = _make_app_entity(repo, "Stable System")
        diag_id = _make_scope_bound_diagram(repo, "Stable Context", scope_id)
        path = _diagram_path(repo, diag_id)

        verifier, clear_caches = _make_context(repo)
        with frozen_now("2026-07-24T09:15:00Z"):
            self._refresh(repo, verifier, clear_caches, diag_id)
            earlier = path.read_text(encoding="utf-8")
        with frozen_now("2026-07-25T10:30:00Z"):
            self._refresh(repo, verifier, clear_caches, diag_id)
            later = path.read_text(encoding="utf-8")

        assert len(earlier.splitlines()) == len(later.splitlines())
        changed = [
            (before, after)
            for before, after in zip(earlier.splitlines(), later.splitlines())
            if before != after
        ]
        assert changed == [("last-updated: '2026-07-24T09:15:00Z'", "last-updated: '2026-07-25T10:30:00Z'")]


# ---------------------------------------------------------------------------
# ArchiMate-reconcile behavior is unchanged through refresh_diagram
# ---------------------------------------------------------------------------


class TestArchiMateReconcileUnchanged:
    def test_refresh_removes_stale_entity_same_as_sync(self, repo: Path) -> None:
        e1 = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="Keep Me",
            summary="Keep",
            dry_run=False,
            repo_root=str(repo),
        )["artifact_id"]
        e2 = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="Delete Me",
            summary="Gone",
            dry_run=False,
            repo_root=str(repo),
        )["artifact_id"]
        mcp.artifact_bulk_delete(
            items=[{"op": "delete_entity", "artifact_id": e2}],
            dry_run=False,
            repo_root=str(repo),
        )
        diag_id = _make_archimate_diagram(repo, "Reconcile Diagram", [e1, e2])

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert e2 in result.removed_entity_ids
        assert e1 not in result.removed_entity_ids
        assert result.deleted_diagram is False

    def test_refresh_dry_run_archimate_non_mutating(self, repo: Path) -> None:
        e1 = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="Only",
            summary="x",
            dry_run=False,
            repo_root=str(repo),
        )["artifact_id"]
        mcp.artifact_bulk_delete(
            items=[{"op": "delete_entity", "artifact_id": e1}],
            dry_run=False,
            repo_root=str(repo),
        )
        diag_id = _make_archimate_diagram(repo, "Dry Archimate", [e1])
        path = _diagram_path(repo, diag_id)
        before = path.read_bytes()

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert result.wrote is False
        assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# MCP adapter routes scope-bound through refresh_diagram (not sync)
# ---------------------------------------------------------------------------


class TestMcpAutoSyncScopeBound:
    def test_mcp_auto_sync_does_not_delete_scope_bound(self, repo: Path) -> None:
        scope_id = _make_app_entity(repo, "MCP Scope")
        diag_id = _make_scope_bound_diagram(repo, "MCP Context", scope_id)

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=False,
            repo_root=str(repo),
        )

        assert result.get("deleted_diagram") is False
        assert _diagram_path(repo, diag_id).exists()

    def test_mcp_auto_sync_scope_bound_dry_run_non_mutating(self, repo: Path) -> None:
        scope_id = _make_app_entity(repo, "MCP Dry Scope")
        diag_id = _make_scope_bound_diagram(repo, "MCP Dry Context", scope_id)
        path = _diagram_path(repo, diag_id)
        before = path.read_bytes()

        result = mcp.artifact_edit_diagram(
            artifact_id=diag_id,
            puml="auto-sync",
            dry_run=True,
            repo_root=str(repo),
        )

        assert result.get("wrote") is False
        assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# Standalone diagram: refresh re-renders, never deletes
# ---------------------------------------------------------------------------


def _make_standalone_diagram(repo: Path, name: str) -> str:
    """Write a standalone diagram with explicit diagram-entities but no scoped-by binding."""
    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000010.tstnd.{slug}"
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  software-system:
  - id: sys
    label: MySystem
---
@startuml {slug}
title {name}
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


class TestStandaloneDiagramRefresh:
    def test_standalone_diagram_not_deleted_on_refresh(self, repo: Path) -> None:
        """A standalone C4 diagram (diagram-entities, no scoped-by) must survive refresh."""
        diag_id = _make_standalone_diagram(repo, "Standalone C4")

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert result.deleted_diagram is False
        assert _diagram_path(repo, diag_id).exists()

    def test_standalone_refresh_dry_run_non_mutating(self, repo: Path) -> None:
        diag_id = _make_standalone_diagram(repo, "Standalone Dry")
        path = _diagram_path(repo, diag_id)
        before = path.read_bytes()

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=True,
        )

        assert result.wrote is False
        assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# ArchiMate reconcile: all-unresolved preserves diagram (no silent deletion)
# ---------------------------------------------------------------------------


class TestArchiMateEmptyPreservesDiagram:
    def test_archimate_all_stale_preserves_diagram(self, repo: Path) -> None:
        """When ALL entity refs are unresolved, sync must keep the diagram (not delete it)."""
        e1 = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="Gone Entity",
            summary="x",
            dry_run=False,
            repo_root=str(repo),
        )["artifact_id"]
        mcp.artifact_bulk_delete(
            items=[{"op": "delete_entity", "artifact_id": e1}],
            dry_run=False,
            repo_root=str(repo),
        )
        diag_id = _make_archimate_diagram(repo, "All Stale Diagram", [e1])

        verifier, clear_caches = _make_context(repo)
        result = refresh_diagram(
            repo_root=repo,
            store=_fresh_store(repo),
            verifier=verifier,
            clear_repo_caches=clear_caches,
            artifact_id=diag_id,
            dry_run=False,
        )

        assert result.deleted_diagram is False, "All-stale ArchiMate diagram must not be silently deleted"
        assert _diagram_path(repo, diag_id).exists()
        assert result.warnings, "Should warn about unresolved entities"


# ---------------------------------------------------------------------------
# REST adapter: POST /api/diagrams/{artifact_id}/sync delegates to refresh_diagram
# ---------------------------------------------------------------------------


class TestRestSyncAdapter:
    def test_rest_sync_endpoint_calls_refresh_diagram(self, repo: Path) -> None:
        """Thin adapter test: the REST handler calls refresh_diagram and returns correct keys."""
        from src.application.artifacts.repository import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers._diagram_write import SyncDiagramToModelBody, sync_diagram_to_model_gui

        scope_id = _make_app_entity(repo, "REST Sync App")
        diag_id = _make_scope_bound_diagram(repo, "REST Sync Diagram", scope_id)

        gui_state.init_state(ArtifactRepository(shared_artifact_index(repo)), repo, None)

        result = sync_diagram_to_model_gui(diag_id, SyncDiagramToModelBody(dry_run=True))

        assert "wrote" in result
        assert result["deleted_diagram"] is False, (
            "REST /api/diagrams/{artifact_id}/sync must report that it did not delete the diagram"
        )

    def test_rest_sync_reports_the_no_deletion_guarantee_over_http(self, repo: Path) -> None:
        """The assertion above could only say ``is not True`` while the handler omitted the key, and an
        absent key reads as a satisfied guarantee — which is the one thing it must not do. Through the
        application the body is validated against ``SyncDiagramToModelResponse`` as well, so a field the
        contract does not declare fails the request rather than reaching a client undocumented."""
        from starlette.testclient import TestClient

        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers._diagram_write import router as diagram_write_router
        from tests.support.api_app import build_api_app

        scope_id = _make_app_entity(repo, "REST Sync Http App")
        diag_id = _make_scope_bound_diagram(repo, "REST Sync Http Diagram", scope_id)
        gui_state.init_state(ArtifactRepository(shared_artifact_index(repo)), repo, None)

        client = TestClient(build_api_app(diagram_write_router))
        response = client.post(f"/api/diagrams/{diag_id}/sync", json={"dry_run": True})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["deleted_diagram"] is False
        assert body["removed_entity_ids"] == [] and body["removed_connection_ids"] == []
        assert _diagram_path(repo, diag_id).exists()

    def test_rest_sync_scope_bound_not_deleted(self, repo: Path) -> None:
        """REST sync on a scope-bound diagram must leave the file on disk."""
        from src.application.artifacts.repository import ArtifactRepository
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers._diagram_write import SyncDiagramToModelBody, sync_diagram_to_model_gui

        scope_id = _make_app_entity(repo, "REST Scope App2")
        diag_id = _make_scope_bound_diagram(repo, "REST Scope Diag2", scope_id)
        path = _diagram_path(repo, diag_id)

        gui_state.init_state(ArtifactRepository(shared_artifact_index(repo)), repo, None)

        sync_diagram_to_model_gui(diag_id, SyncDiagramToModelBody(dry_run=False))
        assert path.exists()
