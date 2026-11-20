"""The sync status says there is unsaved work whenever the save would commit something.

Three readings of "does this engagement repository hold unsaved work" exist, and they do not agree:

* the **status** the GUI polls (`status_cache._measure`) asks git about `model/`, `docs/` and
  `diagram-catalog/` only;
* the **save** (`commit_engagement_work`) and the **background pull** (`GitSyncManager._is_clean`) ask
  about everything except `.arch/`;
* the **save dialog's list** (`sync.changes.list_changes`) classifies each changed path by the layout,
  and drops a scratchpad on purpose.

So a change under `scratchpads/` — or under `projects/<slug>/model/`, where a repository laid out by
group keeps every entity — is committed by a save, holds back the pull, and is reported as nothing to
save. The GUI offers Save only while the status says dirty (`reduceCluster`: `engagementDirty`), so
the one action that would publish the work is the one withheld.

Through the routes, with the real mutation executor and the real scratchpad write path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.git.git_sync import GitSyncManager
from src.infrastructure.rest.routers import scratchpads as scratchpad_router
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.sync import status_cache as sync_status_cache
from src.infrastructure.rest.routers.sync.router import router as sync_router
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import install_mutation_executor
from src.infrastructure.write.workspace_authorization import (
    WorkspaceAuthorizationSnapshots,
    persisted_sync_health,
)
from tests.support.api_app import build_api_app
from tests.support.git_workflow_fixtures import build_workflow_pair, git, valid_entity_md, write_entity

FLAT_ID = "REQ@1000000931.UnsFl.edited-under-model"
GROUPED_ID = "REQ@1000000932.UnsGr.edited-under-projects"
GROUPED_PATH = Path("projects") / "p" / "model" / "motivation" / "requirement" / f"{GROUPED_ID}.md"


@dataclass
class Workspace:
    client: TestClient
    engagement: Path

    def says_unsaved(self) -> bool:
        sync_status_cache.invalidate_sync_status_cache()
        response = self.client.get("/api/sync/status")
        assert response.status_code == 200, response.text
        return bool(response.json()["engagement"]["has_uncommitted_changes"])

    def listed_for_saving(self) -> list[str]:
        response = self.client.get("/api/sync/changes", params={"repo": "engagement"})
        assert response.status_code == 200, response.text
        return [row["artifact_id"] for row in response.json()["artifacts"]]

    def save(self) -> str:
        response = self.client.post("/api/sync/engagement/save", json={"message": "save", "push": False})
        assert response.status_code == 200, response.text
        return git(self.engagement, "show", "--name-only", "--format=", "HEAD")

    def create_a_scratchpad(self) -> str:
        response = self.client.post("/api/scratchpads", json={"name": "Thinking aloud", "group": "p"})
        assert response.status_code == 201, response.text
        return str(response.json()["artifact-id"])

    def pull_would_be_held_back(self) -> bool:
        """What the background pull asks before it will touch the tree."""
        return not asyncio.run(GitSyncManager([])._is_clean(self.engagement))


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    sync_status_cache.reset_sync_status_cache()
    engagement, enterprise = build_workflow_pair(tmp_path)
    grouped = engagement / GROUPED_PATH
    grouped.parent.mkdir(parents=True)
    grouped.write_text(valid_entity_md(GROUPED_ID, "Edited Under Projects"), encoding="utf-8")
    write_entity(engagement, FLAT_ID, "Edited Under Model")
    git(engagement, "add", "-A")
    git(engagement, "commit", "-q", "-m", "both layouts")
    gui_state.init_state(ArtifactRepository(shared_artifact_index([engagement])), engagement, enterprise)
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
    with TestClient(build_api_app(sync_router, scratchpad_router.router)) as client:
        yield Workspace(client, engagement)
    sync_status_cache.reset_sync_status_cache()


def test_a_freshly_committed_repository_is_reported_saved(workspace: Workspace) -> None:
    """The baseline every test below departs from, so a `True` there is about the edit."""
    assert workspace.says_unsaved() is False
    assert workspace.pull_would_be_held_back() is False


def test_an_entity_edited_under_model_is_reported_unsaved(workspace: Workspace) -> None:
    """The control: the flat layout's directory is in the status's list."""
    write_entity(workspace.engagement, FLAT_ID, "Edited Under Model Again")

    assert workspace.says_unsaved() is True
    assert workspace.listed_for_saving() == [FLAT_ID]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "status_cache._measure asks has_uncommitted_changes about model/, docs/ and diagram-catalog/ "
        "only, so a scratchpad nobody has saved reads as nothing to save and the GUI withholds Save"
    ),
)
def test_a_scratchpad_nobody_has_saved_is_reported_unsaved(workspace: Workspace) -> None:
    workspace.create_a_scratchpad()

    assert workspace.says_unsaved() is True


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "the same three-directory list: an entity under projects/<slug>/model/ — every entity of a "
        "repository laid out by group — is edited, listed in the save dialog, and reported saved"
    ),
)
def test_an_entity_edited_under_projects_is_reported_unsaved(workspace: Workspace) -> None:
    (workspace.engagement / GROUPED_PATH).write_text(
        valid_entity_md(GROUPED_ID, "Edited Under Projects Again"), encoding="utf-8"
    )
    # The save dialog's own list sees it, so this is the status alone disagreeing.
    assert workspace.listed_for_saving() == [GROUPED_ID]

    assert workspace.says_unsaved() is True


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "sync.changes._classify returns None for a scratchpad, so the save dialog lists nothing for "
        "a file the save it confirms will commit"
    ),
)
def test_the_save_dialog_lists_a_scratchpad_the_save_will_commit(workspace: Workspace) -> None:
    pad_id = workspace.create_a_scratchpad()

    assert workspace.listed_for_saving() == [pad_id]


def test_a_save_carries_a_scratchpad_whatever_the_status_said(workspace: Workspace) -> None:
    """The commit side is whole: it stages everything but `.arch/`, the scratchpad included.

    Which is what makes the status's silence matter — the work is not excluded from saving, only
    from being *offered* for it."""
    pad_id = workspace.create_a_scratchpad()

    committed = workspace.save()

    assert f"scratchpads/p/{pad_id}.scratchpad.yaml" in committed.splitlines()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "GitSyncManager._is_clean counts scratchpads/ and the status does not: with only a scratchpad "
        "unsaved the background pull is skipped ('uncommitted changes') while the status reports a "
        "saved repository, so the clone stops following its remote with nothing on screen to resolve"
    ),
)
def test_the_status_and_the_pull_agree_on_whether_work_is_unsaved(workspace: Workspace) -> None:
    workspace.create_a_scratchpad()

    assert workspace.says_unsaved() is workspace.pull_would_be_held_back()
