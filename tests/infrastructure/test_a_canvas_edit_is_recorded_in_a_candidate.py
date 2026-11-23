"""The workspace canvas records each edit in the candidate through one route: merged, versioned, refused when stale."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.typed_table_documents import repository_in

QUEUE = "DOB@1795000000.Queue01.promotion-queue"
CREATE = {"op": "create_entity", "artifact_id": QUEUE,
          "fields": {"artifact_type": "data-object", "name": "Queue", "group": "uncategorized"}}


def test_an_edit_is_recorded_merged_and_refused_when_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repository_in(tmp_path)
    monkeypatch.setattr(state, "maybe_engagement_root", lambda: root)
    with TestClient(build_api_app(candidates.router)) as client:
        created = client.post("/api/change-sets", json={"record": {"name": "Naive architecture"}}).json()
        path = f"/api/change-sets/{created['record']['id']}/operations"

        first = client.post(path, json={"based_on": created["version"], "operation": CREATE})
        assert first.status_code == 200, first.text
        rename = {"op": "edit_entity", "artifact_id": QUEUE, "field": "name", "value": "Promotion Queue"}
        second = client.post(path, json={"based_on": first.json()["version"], "operation": rename})
        assert second.status_code == 200, second.text

        operations = second.json()["record"]["changes"]["operations"]
        assert [(op["op"], op["fields"]["name"]) for op in operations] == [("create_entity", "Promotion Queue")]
        stale = {**rename, "value": "Bounded Queue"}
        assert client.post(path, json={"based_on": created["version"], "operation": stale}).status_code == 409
        unknown = client.post(path, json={"based_on": second.json()["version"], "operation": {"op": "rename"}})
        assert unknown.status_code == 422
