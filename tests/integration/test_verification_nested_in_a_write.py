"""Promote and cascade-delete verify the whole tree *while holding WRITE*, and must not hang.

This is F6, the most severe hazard in the verification-concurrency work: `WorkspaceMutationGate` is
not reentrant — `reading()` waits while `_writing` is set — so a verifier that acquired READ for
itself would wait on its own caller for ever. No error, no log line, just a backend that stops.

Both tests assert the *premise* as well as the outcome. "The promote completed" proves nothing by
itself: it passes just as well if the verification step stops being nested inside the write, at
which point the hazard is no longer being guarded and nobody finds out. So each test observes the
gate at the moment verification runs, and fails loudly if the nesting has gone away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.artifact_write import cascade_delete as cascade_delete_module
from src.infrastructure.write.artifact_write import promote_execute as promote_execute_module
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import install_mutation_executor
from src.infrastructure.write.workspace_authorization import (
    WorkspaceAuthorizationSnapshots,
    persisted_sync_health,
)
from tests.support.api_app import build_api_app
from tests.support.git_workflow_fixtures import build_workflow_pair, git, valid_entity_md

pytest.importorskip("httpx")

ENTITY_ID = "REQ@1000001301.NestVer.nested-verification-requirement"
ENTITY_NAME = "Nested Verification Requirement"
GAR_TYPE = "global-artifact-reference"


@pytest.fixture()
def promotion_client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.routers.promote import router as promote_router

    engagement, enterprise = build_workflow_pair(tmp_path)
    entity_path = engagement / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md"
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    entity_path.write_text(valid_entity_md(ENTITY_ID, ENTITY_NAME), encoding="utf-8")
    git(engagement, "add", "-A")
    git(engagement, "commit", "-m", "add nested-verification entity")

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
    app = build_api_app(promote_router)
    install_module_registry(app)
    yield TestClient(app)


def _observe_gate_during(monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> dict[str, bool]:
    """Wrap a module's verification call so the gate's state at that moment is recorded."""
    observed: dict[str, bool] = {}
    real = getattr(module, name)

    def observing(*args: object, **kwargs: object) -> object:
        observed["write_held"] = get_workspace_gate().is_writing
        observed["completed"] = False
        result = real(*args, **kwargs)
        observed["completed"] = True
        return result

    monkeypatch.setattr(module, name, observing)
    return observed


def test_a_promote_verifies_while_holding_write_and_completes(
    promotion_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _observe_gate_during(monkeypatch, promote_execute_module, "collect_verification_errors")

    response = promotion_client.post(
        "/api/promote/execute", json={"entity_ids": [ENTITY_ID], "dry_run": False}
    )

    assert response.status_code == 200, response.text
    assert response.json()["executed"] is True
    assert observed.get("write_held") is True, (
        "promote no longer verifies while holding WRITE — this test is the F6 deadlock guard, and "
        "it has stopped guarding anything. Either restore the nesting or retire the hazard."
    )
    assert observed.get("completed") is True


def test_a_cascade_delete_verifies_while_holding_write_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second nested caller: deleting a model-project verifies what is left behind."""
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.routers.groups import router as groups_router
    from src.infrastructure.write.artifact_write.group_ops import group_create

    engagement, enterprise = build_workflow_pair(tmp_path)
    group_create(engagement, axis="model-project", slug="doomed", name="Doomed Project")
    entity_path = (
        engagement / "projects" / "doomed" / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md"
    )
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    entity_path.write_text(valid_entity_md(ENTITY_ID, ENTITY_NAME), encoding="utf-8")
    git(engagement, "add", "-A")
    git(engagement, "commit", "-m", "add a project to delete")

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
    app = build_api_app(groups_router)
    install_module_registry(app)
    client = TestClient(app)

    observed = _observe_gate_during(monkeypatch, cascade_delete_module, "collect_verification_errors")

    response = client.request(
        "DELETE", "/api/groups/model-project/doomed", params={"confirm": "doomed"}
    )

    assert response.status_code == 200, response.text
    assert observed.get("write_held") is True, (
        "cascade-delete no longer verifies while holding WRITE — this test is the F6 deadlock guard "
        "and it has stopped guarding anything."
    )
    assert observed.get("completed") is True
