"""The sync status says there is unsaved work whenever the save would commit something.

Two readings of "does this engagement repository hold unsaved work" existed, and they did not agree:

* the **status** the GUI polls asked git about `model/`, `docs/` and `diagram-catalog/` only;
* the **save** and the **background pull** asked about everything except `.arch/`.

So a change under `scratchpads/` — or under `projects/<slug>/model/`, where a repository laid out by
group keeps every entity — was committed by a save, held back the pull, and was reported as nothing
to save. The GUI offers Save only while the status says dirty, so the one action that would publish
the work was the one withheld.

They are one reading now (`_git_command.CONTENT_PATHSPEC`: the repository, less its declared runtime
state), and these are its consequences through the routes, with the real mutation executor and the
real scratchpad write path.
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
from src.infrastructure.git._git_command import STAGE_ALL_BUT_RUNTIME_STATE, run_repo_git
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


def test_a_scratchpad_nobody_has_saved_is_reported_unsaved(workspace: Workspace) -> None:
    workspace.create_a_scratchpad()

    assert workspace.says_unsaved() is True


def test_an_entity_edited_under_projects_is_reported_unsaved(workspace: Workspace) -> None:
    (workspace.engagement / GROUPED_PATH).write_text(
        valid_entity_md(GROUPED_ID, "Edited Under Projects Again"), encoding="utf-8"
    )
    # The save dialog's own list sees it, so this is the status alone disagreeing.
    assert workspace.listed_for_saving() == [GROUPED_ID]

    assert workspace.says_unsaved() is True


def test_the_save_dialog_lists_artifacts_and_a_scratchpad_is_not_one(workspace: Workspace) -> None:
    """What the author sees with only a scratchpad unsaved: Save is offered, because the status is
    what offers it, and the dialog's list is empty — it lists model artifacts, and whether a
    scratchpad is shown there as content about to be published is a separate question from whether
    the work can be saved. The second is what this pins: the list is not what offers the save."""
    workspace.create_a_scratchpad()

    assert workspace.says_unsaved() is True
    assert workspace.listed_for_saving() == []


def test_a_save_carries_a_scratchpad(workspace: Workspace) -> None:
    """The commit side was always whole, which is what made the status's silence matter — the work
    was not excluded from saving, only from being *offered* for it."""
    pad_id = workspace.create_a_scratchpad()

    committed = workspace.save()

    assert f"scratchpads/p/{pad_id}.scratchpad.yaml" in committed.splitlines()


def test_the_status_and_the_pull_agree_on_whether_work_is_unsaved(workspace: Workspace) -> None:
    workspace.create_a_scratchpad()

    assert workspace.says_unsaved() is workspace.pull_would_be_held_back()


CONFIGURATION = Path(".arch-repo") / "viewpoint-pins.yaml"


def test_configuration_is_content(workspace: Workspace) -> None:
    """No artifact kind, and still committed by a save — so the status reports it."""
    (workspace.engagement / CONFIGURATION).parent.mkdir(exist_ok=True)
    (workspace.engagement / CONFIGURATION).write_text("pins: []\n", encoding="utf-8")

    assert workspace.says_unsaved() is True
    assert CONFIGURATION.as_posix() in workspace.save().splitlines()


@pytest.mark.parametrize(
    "runtime_state",
    [
        ".arch/enterprise-sync.json",
        ".arch-repo/exchange-identity.json",
        ".arch-repo/transactions/abandoned/intent.tmp",
        ".arch-repo/sync-worktrees/sync-0123456789abcdef/model/x.md",
    ],
)
def test_runtime_state_is_never_unsaved_work(workspace: Workspace, runtime_state: str) -> None:
    """The other side of the one definition: what the deployment keeps for itself is not offered for
    saving, not listed, and does not hold back a pull — whether or not a `.gitignore` covers it."""
    path = workspace.engagement / runtime_state
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")

    assert workspace.says_unsaved() is False
    assert workspace.listed_for_saving() == []
    assert workspace.pull_would_be_held_back() is False


@pytest.mark.parametrize(
    "content",
    [
        "scratchpads/p/SCR@1000000933.UnsSc.a-pad.scratchpad.yaml",
        "projects/p/model/motivation/requirement/REQ@1000000934.UnsNw.a-new-one.md",
        "docs/note/a-note.md",
        "diagram-catalog/rendered/p/a-picture.svg",
        ".arch-repo/groups.yaml",
        ".arch-repo/documents/briefing.json",
        "README.md",
        "a-directory-the-layout-does-not-know-yet/a-file.txt",
    ],
)
def test_the_readings_agree_for_content_anywhere(workspace: Workspace, content: str) -> None:
    """The round trip the readings never had: whatever the file, the status offers the save, the
    pull waits, and the save's own staging takes that file.

    Stated over what the layout *permits* — including a directory it does not have yet — rather
    than over the directories it has today, which is the list this replaced."""
    path = workspace.engagement / content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("name: anything\n", encoding="utf-8")

    assert workspace.says_unsaved() is True
    assert workspace.pull_would_be_held_back() is True
    rc, _, stderr = run_repo_git(workspace.engagement, *STAGE_ALL_BUT_RUNTIME_STATE)
    assert rc == 0, stderr
    assert git(workspace.engagement, "diff", "--cached", "--name-only").splitlines() == [content]
