"""Exercise candidate and analysis reads across the two public transports against one repository."""

import json
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.document_schema import normalize_document_schema
from src.domain.artifact_id import stable_id
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.typed_table_documents import document_path, document_text, repository_in, table_of, table_text


def test_agents_and_canvas_share_versions_and_composed_diffs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repository_in(tmp_path)
    monkeypatch.setattr(state, "maybe_engagement_root", lambda: root)
    with TestClient(build_api_app(candidates.router)) as client:
        created = client.post("/api/change-sets", json={"record": {"name": "Hold promotions during outage"}})
        assert created.status_code == 200, created.text
        document = created.json()
        ref = document["record"]["id"]
        path = f"/api/change-sets/{ref}"
        assert mcp.change_set_read(ref, repo_root=str(root)) == document == client.get(path).json()
        assert client.get("/api/change-sets").json() == mcp.change_set_list(str(root))
        patch = {
            "changes": {
                **document["record"]["changes"],
                "operations": [
                    {
                        "op": "create_entity",
                        "ref": "queue",
                        "fields": {"artifact_type": "service", "name": "Queue", "group": "uncategorized"},
                    }
                ],
            },
            "state": "candidate",
        }
        update = mcp.change_set_edit(ref, document["version"], patch, str(root))
        assert update["version"] != document["version"]
        assert client.patch(path, json={"based_on": document["version"], "patch": {"name": "Stale"}}).status_code == 409
        assert client.get(path + "/standing").json() == mcp.change_set_read(ref, "standing", repo_root=str(root))
        diff = mcp.change_set_read(ref, "diff", repo_root=str(root))
        assert client.get(path + "/diff").json() == diff
        assert diff["diff"][0]["fields"]["name"] == {"before": None, "after": "Queue"}
        (listed,) = client.get("/api/change-sets").json()["candidates"]
        assert (listed["scope"], listed["operations"]) == ([], 1)
        assert client.post("/api/change-set-checks", json={"candidates": [ref]}).json() == mcp.change_set_check(
            [ref], str(root)
        )


def test_analysis_reads_the_scoped_naive_candidate_on_both_surfaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = repository_in(tmp_path)
    source = Path(__file__).resolve().parents[2] / "engagements/ENG-ARCH-REPO/architecture-repository"
    diagram = "ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements"
    service = "SRV@1712870400.Uv9Wx9.repository-promotion-service"
    for filename in (f"{diagram}.puml", f"{service}.md"):
        original = next(source.rglob(filename))
        target = root / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(original, target)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    schema = normalize_document_schema("stress-analysis", STRESS_ANALYSIS_SCHEMA)
    naive_id = "CAND@1790000000.Promot.naive"
    document = document_path(root, schema)
    document.parent.mkdir(parents=True)
    document.write_text(
        document_text(
            schema,
            {
                "stressors": table_text(
                    table_of(schema, "stressors"),
                    [
                        {
                            "stressor": "Promotion queue stalls",
                            "kind": "outage",
                            "subject": "$ref:queue",
                            "set": "design",
                        },
                    ],
                ),
                "incidence": table_text(
                    table_of(schema, "incidence"),
                    [
                        {"stressor": "S1", "component": ref, "note": "Promotion delayed"}
                        for ref in (service, "$ref:queue")
                    ],
                ),
            },
            **{"naive-candidate": naive_id, "scope-diagram": diagram},
        )
    )
    monkeypatch.setattr(state, "maybe_engagement_root", lambda: root)
    with TestClient(build_api_app(candidates.router)) as client:
        naive = mcp.change_set_create({"name": "Queued promotion", "id": naive_id}, diagram, str(root))
        stable_service = stable_id(service)  # scope and view hold an entity by its stable id
        assert stable_service in naive["record"]["scope"]
        ops = [
            {
                "op": "create_entity",
                "ref": "queue",
                "fields": {"name": "Promotion queue", "artifact_type": "service", "group": "uncategorized"},
            }
        ]
        patch = {"changes": {**naive["record"]["changes"], "operations": ops}}
        client.patch(
            f"/api/change-sets/{naive_id}", json={"based_on": naive["version"], "patch": patch}
        ).raise_for_status()
        comparison = client.get(f"/api/change-sets/{naive_id}/diff")
        comparison.raise_for_status()
        assert {row["id"] for row in comparison.json()["view"]["entities"]} >= {stable_service, "$ref:queue"}
        path = f"/api/documents/{document.stem}"
        grid = client.get(path + "/incidence").json()
        assert grid == mcp.analysis_incidence(document.stem, str(root))
        assert grid["stressors"][0]["missing_elements"] == []
        assert grid["coupling"] == [{"left": "$ref:queue", "right": stable_service, "count": 1}]
        progress = client.get(path + "/progress").json()
        assert progress == mcp.analysis_progress(document.stem, str(root))
        assert progress["coverage"]["by_kind"] == {"outage": 1}
        current = mcp.change_set_read(naive_id, repo_root=str(root))
        original_changes = naive["record"]["changes"]
        mcp.change_set_edit(naive_id, current["version"], {"changes": original_changes}, str(root))
        assert client.get(path + "/incidence").json()["stressors"][0]["missing_elements"] == ["$ref:queue"]
