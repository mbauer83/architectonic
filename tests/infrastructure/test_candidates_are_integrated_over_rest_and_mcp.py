"""Integrating candidates (S4) over REST and MCP alike: a dry run lists the conflicts still standing with the
actions each permits; resolutions settle them in order; the integration is stored as a new draft on the parent
the candidates share, and nothing reaches the model."""

from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.candidate_wire import IntegrationResolution
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

_SOURCE = Path(__file__).resolve().parents[2] / "engagements/ENG-ARCH-REPO/architecture-repository"
_SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    original = next(_SOURCE.rglob(f"{_SERVICE}.md"))
    target = root / original.relative_to(_SOURCE)
    target.parent.mkdir(parents=True, exist_ok=True)
    copyfile(original, target)
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _renaming(client: TestClient, parent: str, name: str) -> str:
    made = client.post("/api/change-sets", json={
        "record": {"name": f"Adaptation: {name}", "parent": parent},
        "operations": [{"op": "edit_entity", "artifact_id": _SERVICE, "field": "name", "value": name}],
    })
    assert made.status_code == 200, made.text
    return str(made.json()["record"]["id"])


@pytest.fixture
def adaptations(client: TestClient) -> tuple[str, str, str]:
    naive = client.post("/api/change-sets", json={"record": {"name": "Naive", "scope": [_SERVICE]}})
    assert naive.status_code == 200, naive.text
    parent = str(naive.json()["record"]["id"])
    return parent, _renaming(client, parent, "Promotion Queue Service"), _renaming(client, parent, "Promotion Gate")


def test_a_dry_run_lists_each_conflict_with_the_actions_it_permits_and_writes_nothing(
    client: TestClient, adaptations: tuple[str, str, str],
) -> None:
    _parent, ours, theirs = adaptations
    before = client.get("/api/change-sets").json()["candidates"]

    planned = client.post("/api/change-set-integrations", json={"candidates": [ours, theirs], "name": "Integration"})

    assert planned.status_code == 200, planned.text
    (conflict,) = planned.json()["conflicts"]
    assert (conflict["kind"], conflict["actions"]) == ("same-key", ["take", "drop", "merge"])
    assert {party["set_id"] for party in conflict["parties"]} == {ours, theirs}
    assert "integration" not in planned.json()
    assert client.get("/api/change-sets").json()["candidates"] == before


def test_integrating_while_a_conflict_stands_is_refused(client: TestClient, adaptations: tuple[str, str, str]) -> None:
    _parent, ours, theirs = adaptations

    refused = client.post("/api/change-set-integrations", json={
        "candidates": [ours, theirs], "name": "Integration", "dry_run": False,
    })

    assert refused.status_code == 409, refused.text
    assert "1 conflict still stands" in refused.text


def test_a_resolved_integration_is_a_new_draft_on_the_shared_parent(
    client: TestClient, adaptations: tuple[str, str, str],
) -> None:
    parent, ours, theirs = adaptations
    subject = client.post("/api/change-set-integrations", json={
        "candidates": [ours, theirs], "name": "Integration",
    }).json()["conflicts"][0]["subject"]

    made = client.post("/api/change-set-integrations", json={
        "candidates": [ours, theirs], "name": "Integration", "dry_run": False,
        "resolutions": [{"kind": "same-key", "subject": subject, "action": "merge", "value": "Promotion Gate Queue"}],
    })

    assert made.status_code == 200, made.text
    record = made.json()["integration"]["record"]
    assert (record["state"], record["parent"], record["name"]) == ("draft", parent, "Integration")
    (operation,) = record["changes"]["operations"]
    assert (stable_id(operation["artifact_id"]), operation["value"]) == (stable_id(_SERVICE), "Promotion Gate Queue")
    for chosen in (ours, theirs):
        assert client.get(f"/api/change-sets/{chosen}").json()["record"]["state"] == "draft"
    root: Path = client.root  # type: ignore[attr-defined]
    assert "Promotion Gate Queue" not in next(root.rglob(f"{_SERVICE}.md")).read_text(encoding="utf-8")


def test_an_agent_integrates_through_mcp_as_the_page_does(
    client: TestClient, adaptations: tuple[str, str, str],
) -> None:
    root = str(client.root)  # type: ignore[attr-defined]
    _parent, ours, theirs = adaptations
    over_rest = client.post("/api/change-set-integrations", json={"candidates": [ours, theirs], "name": "By hand"})
    subject = over_rest.json()["conflicts"][0]["subject"]

    assert mcp.change_set_integrate([ours, theirs], "By hand", repo_root=root) == over_rest.json()
    made = mcp.change_set_integrate(
        [ours, theirs], "By an agent", dry_run=False, repo_root=root,
        resolutions=[IntegrationResolution(kind="same-key", subject=subject, action="take", party=theirs)],
    )

    assert made["integration"]["record"]["changes"]["operations"][0]["value"] == "Promotion Gate"
