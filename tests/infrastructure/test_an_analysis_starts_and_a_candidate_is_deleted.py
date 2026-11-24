"""Starting an analysis is one write, a candidate is deleted only when nothing depends on it, and a
drifted candidate is re-based — over REST and MCP alike."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import entity_in, repository_in


def _declaring_analyses(tmp_path: Path) -> Path:
    root = repository_in(tmp_path)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    return root


def _candidate_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.candidate.yaml"))


@contextmanager
def _served(root: Path) -> Iterator[TestClient]:
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _served(_declaring_analyses(tmp_path)) as served:
        yield served


def test_a_start_writes_the_naive_and_the_document_naming_it(client: TestClient) -> None:
    started = client.post("/api/stress-analyses", json={
        "title": "Stress analysis — start", "question": "Does it hold?", "naive": {"name": "Naive architecture"},
    })
    assert started.status_code == 200, started.text
    body = started.json()
    naive = body["naive_candidate"]["record"]["id"]
    document = client.get(f"/api/documents/{body['document']}/progress")
    assert document.status_code == 200, document.text
    assert document.json()["naive_candidate"] == naive
    assert [p.name for p in _candidate_files(client.root)] == [f"{naive}.candidate.yaml"]  # type: ignore[attr-defined]


def test_a_refused_start_leaves_nothing_behind(tmp_path: Path) -> None:
    root = repository_in(tmp_path)  # declares no stress-analysis document type
    with _served(root) as client:
        refused = client.post("/api/stress-analyses", json={"title": "Refused", "naive": {"name": "Naive"}})
        assert refused.status_code == 422, refused.text
        assert "stress-analysis" in refused.text
    with pytest.raises(ValueError, match="stress-analysis"):
        mcp.analysis_start("Refused", {"name": "Naive"}, repo_root=str(root))
    assert _candidate_files(root) == []
    assert list(root.rglob("*.md")) == []


def test_a_start_refused_only_by_the_write_takes_its_naive_back(tmp_path: Path) -> None:
    from src.infrastructure.candidates.service import CandidateService
    from src.infrastructure.write.artifact_write.types import WriteResult

    root = _declaring_analyses(tmp_path)

    def writer(title: str, frontmatter: dict[str, object], dry_run: bool) -> WriteResult:
        return WriteResult(wrote=False, path=root / "x.md", artifact_id="SA@1", content=None, warnings=[],
                           verification={"issues": [] if dry_run else [{"severity": "error", "message": "late"}]})

    with pytest.raises(ValueError, match="late"):
        CandidateService(root).start("Late refusal", {"name": "Naive"}, writer)
    assert _candidate_files(root) == []


def test_a_candidate_is_deleted_only_when_nothing_depends_on_it(client: TestClient) -> None:
    root = client.root  # type: ignore[attr-defined]
    started = mcp.analysis_start("Stress analysis — delete", {"name": "Naive"}, repo_root=str(root))
    naive = started["naive_candidate"]["record"]["id"]
    adaptation = client.post("/api/change-sets", json={"record": {"name": "On top", "parent": naive}}).json()
    on_top = adaptation["record"]["id"]

    stacked = client.delete(f"/api/change-sets/{naive}")
    assert stacked.status_code == 409 and on_top in stacked.text
    assert client.delete(f"/api/change-sets/{on_top}").status_code == 204
    named = client.delete(f"/api/change-sets/{naive}")
    assert named.status_code == 409 and started["document"] in named.text
    with pytest.raises(ValueError, match="naive architecture of"):
        mcp.change_set_delete(naive, str(root))
    assert client.delete(f"/api/change-sets/{on_top}").status_code == 404

    loose = mcp.change_set_create({"name": "Loose"}, repo_root=str(root))["record"]["id"]
    assert mcp.change_set_delete(loose, str(root)) == {"deleted": loose}
    assert [c["id"] for c in client.get("/api/change-sets").json()["candidates"]] == [naive]


def test_a_drifted_candidate_is_rebased_and_then_applies(client: TestClient) -> None:
    root = client.root  # type: ignore[attr-defined]
    entity = entity_in(root, "application-component", "queueing")
    notify_paths_changed([entity])
    ref = entity.stem
    created = client.post("/api/change-sets", json={"record": {"name": "Rename", "scope": [ref]}}).json()
    path = f"/api/change-sets/{created['record']['id']}"
    rename = {"op": "edit_entity", "artifact_id": ref, "field": "name", "value": "Promotion queue"}
    recorded = client.post(path + "/operations", json={"based_on": created["version"], "operation": rename}).json()

    entity.write_text(entity.read_text().replace("name: queueing", "name: Queue desk"))
    notify_paths_changed([entity])
    assert [s["standing"] for s in client.get(path + "/standing").json()["standing"]] == ["drifted"]

    rebased = client.post(path + "/rebase", json={"based_on": recorded["version"]})
    assert rebased.status_code == 200, rebased.text
    assert [s["standing"] for s in client.get(path + "/standing").json()["standing"]] == ["applies"]
    operation = rebased.json()["record"]["changes"]["operations"][0]
    assert operation["value"] == "Promotion queue"
    again = mcp.change_set_rebase(created["record"]["id"], rebased.json()["version"], str(root))
    assert again["version"] == rebased.json()["version"]


def test_the_composed_view_names_the_id_chosen_for_what_the_candidate_creates(client: TestClient) -> None:
    queue = "DOB@1795000000.Queue01.promotion-queue"
    created = client.post("/api/change-sets", json={"record": {"name": "Creates"}}).json()
    path = f"/api/change-sets/{created['record']['id']}"
    create = {"op": "create_entity", "artifact_id": queue,
              "fields": {"artifact_type": "data-object", "name": "Queue", "group": "uncategorized"}}
    client.post(path + "/operations", json={"based_on": created["version"], "operation": create}).raise_for_status()

    entities = client.get(path + "/diff").json()["view"]["entities"]

    assert [(one["id"].startswith("$ref:"), one.get("artifact_id")) for one in entities] == [(True, queue)]
