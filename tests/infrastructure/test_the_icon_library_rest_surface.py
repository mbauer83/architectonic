"""The icon library's REST surface, through the ASGI stack: list, add, read, edit, replace, delete, the picture."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from src.infrastructure.rest.routers import icons as icon_router
from src.infrastructure.rest.routers import state as s
from tests.support.api_app import build_api_app
from tests.support.icon_files import icon_file, png_of, write_icon
from tests.support.rest_state import reset_state_for_test

NODE_ICON = "ICO@1790000000.aks001.azure-kubernetes-service"


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    write_icon(root, icon_file(NODE_ICON, applies_to=("technology-node",)))
    write_icon(root, icon_file("ICO@1790000001.any001.generic", name="Generic mark", png=png_of((1, 2, 3, 255))))
    return root


@pytest.fixture
def client(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([repo_root])), repo_root, None)
    # The mutation executor is the write queue and gate; this suite is about the HTTP contract.
    monkeypatch.setattr(s, "authorized_write", lambda _operation_id, fn, *args, **kwargs: fn(*args, **kwargs))
    try:
        with TestClient(build_api_app(icon_router.router)) as test_client:
            yield test_client
    finally:
        reset_state_for_test()


def _ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["artifact_id"] for item in response.json()["items"]]


def test_the_list_offers_only_what_applies(client: TestClient) -> None:
    assert _ids(client.get("/api/icons", params={"applicable_to": "technology-node"})) == [
        NODE_ICON, "ICO@1790000001.any001.generic"
    ]
    assert _ids(client.get("/api/icons", params={"applicable_to": "application-service"})) == [
        "ICO@1790000001.any001.generic"
    ]
    assert _ids(client.get("/api/icons", params={"q": "generic"})) == ["ICO@1790000001.any001.generic"]


def test_a_row_says_what_a_picker_chooses_by_and_how_it_stands(client: TestClient) -> None:
    row = client.get(f"/api/icons/{NODE_ICON}").json()

    assert row["applies_to"] == ["technology-node"] and row["is_global"] is False
    assert row["baseline_standing"]["kind"] == "enterprise-baseline"


def test_the_picture_is_served_as_png_and_may_be_kept(client: TestClient) -> None:
    response = client.get(f"/api/icons/{NODE_ICON}/image")

    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG") and "private" in response.headers["cache-control"]


def test_an_unknown_icon_is_404(client: TestClient) -> None:
    assert client.get("/api/icons/ICO@1790000009.gone01").status_code == 404
    assert client.get("/api/icons/ICO@1790000009.gone01/image").status_code == 404


def test_an_icon_is_added_and_named_in_location(client: TestClient) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"><rect width="4" height="4" fill="#123"/></svg>'
    response = client.post("/api/icons", json={
        "name": "Queue", "attribution": "Drawn here", "source_format": "svg",
        "content_base64": base64.b64encode(svg).decode(), "applies_to": ["technology-node"], "dry_run": False,
    })

    assert response.status_code == 201, response.text
    assert client.get(response.headers["Location"]).json()["name"] == "Queue"


def test_a_refused_upload_answers_200_with_its_reason(client: TestClient) -> None:
    response = client.post("/api/icons", json={
        "name": "Queue", "attribution": "", "source_format": "png",
        "content_base64": base64.b64encode(png_of()).decode(), "dry_run": False,
    })

    assert response.status_code == 200
    assert "attribution" in response.json()["verification"]["issues"][0]["message"]


def test_a_dry_run_delete_reports_and_a_real_one_answers_204(client: TestClient) -> None:
    generic = "ICO@1790000001.any001.generic"

    planned = client.delete(f"/api/icons/{generic}")
    deleted = client.delete(f"/api/icons/{generic}", params={"dry_run": "false"})

    assert planned.status_code == 200 and planned.json()["wrote"] is False
    assert deleted.status_code == 204 and client.get(f"/api/icons/{generic}").status_code == 404


def _diagram_showing_the_node_icon(repo_root: Path) -> None:
    diagram = repo_root / "diagram-catalog" / "diagrams" / "ARC@1790000005.dia001.view.puml"
    diagram.write_text(f"""---
artifact-id: ARC@1790000005.dia001.view
artifact-type: diagram
diagram-type: archimate-technology
name: View
version: 0.1.0
status: draft
diagram-entities:
  type_icons:
    technology-node: {NODE_ICON}
---
@startuml
title View
@enduml
""", encoding="utf-8")
    s.get_repo().refresh()


def test_deleting_an_icon_in_use_is_409_naming_the_diagram(client: TestClient, repo_root: Path) -> None:
    _diagram_showing_the_node_icon(repo_root)

    response = client.delete(f"/api/icons/{NODE_ICON}", params={"dry_run": "false"})

    assert response.status_code == 409 and "ARC@1790000005.dia001.view" in response.text


def test_a_retired_icon_is_no_longer_offered(client: TestClient) -> None:
    generic = "ICO@1790000001.any001.generic"

    response = client.patch(f"/api/icons/{generic}", json={"status": "retired", "dry_run": False})

    assert response.status_code == 200 and response.json()["wrote"] is True
    assert generic not in _ids(client.get("/api/icons"))
    assert generic in _ids(client.get("/api/icons", params={"include_retired": "true"}))


def test_editing_an_unknown_icon_is_404(client: TestClient) -> None:
    assert client.patch("/api/icons/ICO@1790000009.gone01", json={"name": "X"}).status_code == 404


def test_a_dry_run_replacement_names_the_diagram_it_would_re_point(client: TestClient, repo_root: Path) -> None:
    _diagram_showing_the_node_icon(repo_root)

    response = client.post(
        f"/api/icons/{NODE_ICON}/replace", json={"replacement_id": "ICO@1790000001.any001.generic"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["wrote"] is False and "ARC@1790000005.dia001.view" in response.text


def test_a_replacement_the_library_does_not_hold_is_404(client: TestClient) -> None:
    response = client.post(f"/api/icons/{NODE_ICON}/replace", json={"replacement_id": "ICO@1790000009.gone01"})

    assert response.status_code == 404


def test_an_icon_replacing_itself_is_400(client: TestClient) -> None:
    assert client.post(f"/api/icons/{NODE_ICON}/replace", json={"replacement_id": NODE_ICON}).status_code == 400
