"""Deterministic end-to-end promotion cycle on a local bare remote with a second
reviewer clone: promote → enterprise save → submit (upstream tracking asserted)
→ reviewer merges into main → bounded sync poll → checkout main with the
aggregate cleared — then the promoted content is visible under the Enterprise
facet while the GAR proxy stays raw-readable but invisible to every search
surface (GUI and MCP on combined roots, the query CLI on its single root).

Preconditions recorded: fresh tmp fixture (no browser/localStorage involved),
normal mode (no admin, no read-only), fixture entity REQ@…CycEnt.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.git.git_sync_enterprise import sync_enterprise
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers import sync_status_cache
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import install_mutation_executor
from src.infrastructure.write.workspace_authorization import (
    WorkspaceAuthorizationSnapshots,
    persisted_sync_health,
)
from tests.support.git_workflow_fixtures import build_workflow_pair, git, valid_entity_md

pytest.importorskip("httpx")

ENTITY_ID = "REQ@1000001201.CycEnt.cycle-promoted-requirement"
ENTITY_NAME = "Cycle Promoted Requirement"
QUERY = "cycle promoted requirement"
POLL_DEADLINE_S = 30.0
GAR_TYPE = "global-artifact-reference"


@pytest.fixture()
def cycle(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.gui.routers.connections import router as connections_router
    from src.infrastructure.gui.routers.entities import router as entities_router
    from src.infrastructure.gui.routers.entity_search import router as entity_search_router
    from src.infrastructure.gui.routers.promote import router as promote_router
    from src.infrastructure.gui.routers.sync import router as sync_router

    sync_status_cache.reset_sync_status_cache()
    engagement, enterprise = build_workflow_pair(tmp_path)
    entity_path = engagement / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md"
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    entity_path.write_text(valid_entity_md(ENTITY_ID, ENTITY_NAME), encoding="utf-8")
    git(engagement, "add", "-A")
    git(engagement, "commit", "-m", "add cycle entity")

    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    repo = ArtifactRepository(index, excluded_entity_types=frozenset({GAR_TYPE}))
    gui_state.init_state(repo, engagement, enterprise)
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement,
                enterprise_root=enterprise,
                admin_mode=False,
                read_only=False,
                gate=get_workspace_gate(),
                sync_health=persisted_sync_health(enterprise),
            )
        )
    )
    app = FastAPI()
    install_module_registry(app)
    for router in (promote_router, sync_router, entities_router, entity_search_router, connections_router):
        app.include_router(router)
    client = TestClient(app)
    origin = tmp_path / "enterprise-origin.git"
    yield client, engagement, enterprise, origin, repo
    sync_status_cache.reset_sync_status_cache()


def _reviewer_merge(tmp_path_parent: Path, origin: Path, branch: str) -> None:
    """A second clone plays the reviewer: merge the submitted branch into main."""
    reviewer = origin.parent / "reviewer-clone"
    subprocess.run(["git", "clone", str(origin), str(reviewer)], check=True, capture_output=True)
    git(reviewer, "config", "user.email", "reviewer@example.invalid")
    git(reviewer, "config", "user.name", "Reviewer")
    git(reviewer, "fetch", "origin", branch)
    git(reviewer, "merge", "--no-ff", f"origin/{branch}", "-m", f"merge {branch}")
    git(reviewer, "push", "origin", "main")


def _poll_until_synced(enterprise: Path) -> None:
    manager = GitSyncManager([])
    deadline = time.monotonic() + POLL_DEADLINE_S
    while time.monotonic() < deadline:
        asyncio.run(sync_enterprise(manager, enterprise))
        if enterprise_sync_state.load(enterprise).is_synced():
            return
        time.sleep(0.5)
    raise AssertionError(f"sync did not reach synced within {POLL_DEADLINE_S}s")


def test_full_cycle_promote_save_submit_merge_poll(cycle, tmp_path: Path) -> None:
    client, engagement, enterprise, origin, repo = cycle

    # 1. Promote (live) — enterprise gains the entity, the engagement gains a GAR proxy.
    execute = client.post("/api/promote/execute", json={"entity_ids": [ENTITY_ID], "dry_run": False})
    assert execute.status_code == 200, execute.text
    assert execute.json()["executed"] is True
    promoted_path = enterprise / "model" / "motivation" / "requirement"
    assert any(ENTITY_ID.split(".")[-1] in p.name for p in promoted_path.glob("*.md"))

    # 2. Enterprise save commits the working branch.
    save = client.post("/api/sync/enterprise/save", json={"message": "promote cycle entity"})
    assert save.status_code == 200, save.text
    branch = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
    assert branch.startswith("arch/work-")

    # 3. Submit pushes WITH upstream tracking and transitions to pending.
    submit = client.post("/api/sync/enterprise/submit")
    assert submit.status_code == 200, submit.text
    assert git(enterprise, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}") == f"origin/{branch}"
    assert enterprise_sync_state.load(enterprise).is_pending()

    # 4. Reviewer merges out-of-band; the bounded poll detects it.
    _reviewer_merge(tmp_path, origin, branch)
    _poll_until_synced(enterprise)
    assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert enterprise_sync_state.load(enterprise) == enterprise_sync_state.EnterpriseSyncState()

    # 5. The promoted content lists under the Enterprise facet.
    repo.refresh()
    sync_status_cache.reset_sync_status_cache()
    listed = client.get("/api/entities?scope=global").json()
    listed_names = [item["name"] for item in listed["items"]]
    assert ENTITY_NAME in listed_names
    row = next(item for item in listed["items"] if item["name"] == ENTITY_NAME)
    assert row["is_global"] is True

    # 6. The GAR proxy exists in raw reads…
    gars = repo.list_entities(artifact_type=GAR_TYPE)
    assert len(gars) == 1
    gar_id = gars[0].artifact_id

    # …but is absent from EVERY search surface.
    gui_search_ids = [hit["artifact_id"] for hit in client.get(f"/api/search?q={QUERY}").json()["hits"]]
    artifact_search_ids = [
        hit["artifact_id"] for hit in client.get(f"/api/artifact-search?q={QUERY}").json()["hits"]
    ]
    repo_hits = [hit.record.artifact_id for hit in repo.search_artifacts(QUERY, limit=20).hits]
    assert gar_id not in gui_search_ids
    assert gar_id not in artifact_search_ids
    assert gar_id not in repo_hits
    # The promoted enterprise entity IS findable.
    assert any(ENTITY_ID.split("@")[0] in hit or ENTITY_NAME for hit in gui_search_ids)
    assert any(hit != gar_id for hit in repo_hits)


def test_cli_single_root_search_hides_the_gar_after_promotion(cycle, tmp_path: Path, capsys) -> None:
    client, engagement, enterprise, origin, repo = cycle
    execute = client.post("/api/promote/execute", json={"entity_ids": [ENTITY_ID], "dry_run": False})
    assert execute.status_code == 200, execute.text

    from src.infrastructure.cli.artifact_query_cli import main

    gars = ArtifactRepository(shared_artifact_index(engagement)).list_entities(artifact_type=GAR_TYPE)
    assert len(gars) == 1
    exit_code = main(["search", QUERY, "--repo", str(engagement)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert gars[0].artifact_id not in out
    # Raw CLI listing still shows the GAR (single-root construction).
    exit_code = main(["entities", "--repo", str(engagement), "--type", GAR_TYPE])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert gars[0].artifact_id in out
