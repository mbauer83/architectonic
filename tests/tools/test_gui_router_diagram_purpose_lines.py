"""A diagram's purpose line over REST: the create and replace bodies take it, the read shows it (its viewpoint's
where the diagram states none), the diagram list filters by stakeholder, and a stakeholder's page lists the
views that address it.

Against a fixture repository this file builds, so exact contents are the test's own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

STK_ID = "STK@1000000071.PurStk.purpose-stakeholder"
GOL_ID = "GOL@1000000072.PurGol.purpose-goal"


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    return (
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: {name}\nversion: 0.1.0\n"
        f"status: active\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n## {name}\n\nFixture.\n\n"
        "<!-- §display -->\n\n### archimate\n\n```yaml\ndomain: Motivation\n"
        f"element-type: {artifact_type.title()}\nlabel: \"{name}\"\nalias: {artifact_id[:3]}_{name}\n```\n"
    )


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-PUR" / "architecture-repository"
    for artifact_id, artifact_type, name in ((STK_ID, "stakeholder", "Operations"), (GOL_ID, "goal", "Fast")):
        folder = root / "model" / "motivation" / artifact_type
        folder.mkdir(parents=True)
        (folder / f"{artifact_id}.md").write_text(_entity_md(artifact_id, artifact_type, name), encoding="utf-8")
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    gui_state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    return TestClient(build_api_app(diagrams_router, entities_router))


def _create(client, name: str, **stated: object) -> str:
    response = client.post("/api/diagrams", json={
        "diagram_type": "archimate-motivation", "name": name, "entity_ids": [STK_ID], "connection_ids": [],
        "dry_run": False, **stated,
    })
    body = response.json()
    assert response.status_code == 201 and body["wrote"], body
    return str(body["artifact_id"])


def test_the_read_shows_the_line_with_each_reference_named(client) -> None:
    diagram = _create(client, "Own", stakeholders=[{"ref": STK_ID}, "Warehouse"], concerns=[{"ref": GOL_ID}])

    read = client.get(f"/api/diagrams/{diagram}").json()

    assert read["stakeholders"] == [{"ref": STK_ID}, "Warehouse"]
    assert read["purpose"]["stakeholders"] == [{"text": "Operations", "ref": STK_ID}, {"text": "Warehouse"}]
    assert read["purpose"]["concerns"] == [{"text": "Fast", "ref": GOL_ID}]
    assert "inherited_from" not in read["purpose"]


def test_a_diagram_stating_none_shows_its_viewpoints_line(client) -> None:
    diagram = _create(client, "Inherits", viewpoint={"slug": "stakeholder", "version": 1}, concerns=["Why?"])

    read = client.get(f"/api/diagrams/{diagram}").json()

    assert "stakeholders" not in read, "the diagram states none of its own"
    assert read["purpose"]["stakeholders"], "the viewpoint's stakeholders are shown"
    assert read["purpose"]["concerns"] == [{"text": "Why?"}], "its own concerns win"
    assert read["purpose"]["inherited_from"] == "stakeholder"


def test_a_diagram_without_a_line_reads_without_one(client) -> None:
    read = client.get(f"/api/diagrams/{_create(client, 'Plain')}").json()

    assert "purpose" not in read and "stakeholders" not in read


def test_a_reference_to_a_missing_element_is_refused_with_its_code(client) -> None:
    response = client.post("/api/diagrams", json={
        "diagram_type": "archimate-motivation", "name": "Bad", "entity_ids": [STK_ID], "connection_ids": [],
        "stakeholders": [{"ref": "STK@1999999999.Nobody.gone"}], "dry_run": False,
    })

    body = response.json()
    assert not body["wrote"]
    assert "E186" in {issue["code"] for issue in body["verification"]["issues"]}


def test_a_malformed_entry_is_refused_by_the_body_contract(client) -> None:
    response = client.post("/api/diagrams", json={
        "diagram_type": "archimate-motivation", "name": "Bad", "entity_ids": [STK_ID], "connection_ids": [],
        "stakeholders": [{"name": STK_ID}], "dry_run": True,
    })

    assert response.status_code == 422


def test_the_list_filters_by_stakeholder_reference_or_words(client) -> None:
    for_operations = _create(client, "For operations", stakeholders=[{"ref": STK_ID}])
    for_warehouse = _create(client, "For the warehouse", stakeholders=["Warehouse staff"])
    _create(client, "For nobody")

    def listed(stakeholder: str) -> set[str]:
        items = client.get("/api/diagrams", params={"stakeholder": stakeholder}).json()["items"]
        return {d["artifact_id"] for d in items}

    by_reference, by_words = listed(STK_ID), listed("warehouse STAFF")

    assert by_reference == {for_operations}
    assert by_words == {for_warehouse}


def test_a_replace_keeps_the_line_it_omits(client) -> None:
    diagram = _create(client, "Kept", stakeholders=["Warehouse staff"])

    response = client.put(f"/api/diagrams/{diagram}", json={
        "diagram_type": "archimate-motivation", "name": "Kept", "entity_ids": [STK_ID], "connection_ids": [],
        "concerns": [{"ref": GOL_ID}], "dry_run": False,
    })

    assert response.json()["wrote"], response.json()
    read = client.get(f"/api/diagrams/{diagram}").json()
    assert read["stakeholders"] == ["Warehouse staff"]
    assert read["concerns"] == [{"ref": GOL_ID}]


def test_an_elements_page_lists_the_views_that_address_it(client) -> None:
    addressing = _create(client, "Addresses", concerns=[{"ref": GOL_ID}])
    _create(client, "Does not")

    entity = client.get(f"/api/entities/{GOL_ID}/context").json()["entity"]

    assert [d["artifact_id"] for d in entity["addressed_by_diagrams"]] == [addressing]
