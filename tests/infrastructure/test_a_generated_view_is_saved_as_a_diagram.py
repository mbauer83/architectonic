"""*Save as diagram* (S3): a candidate drawn on a view generated from its scope stores that view as a diagram
through the diagram create, and is drawn on it from then on — over REST and MCP alike. Nothing the candidate
changes is written: the diagram draws the model's entities, as the view did."""

from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.parsing import extract_yaml_block
from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

_SOURCE = Path(__file__).resolve().parents[2] / "engagements/ENG-ARCH-REPO/architecture-repository"
_DIAGRAM = "ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements"
_SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    for filename in (f"{_DIAGRAM}.puml", f"{_SERVICE}.md"):
        original = next(_SOURCE.rglob(filename))
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


def _root(client: TestClient) -> Path:
    root: Path = client.root  # type: ignore[attr-defined]
    return root


def _candidate(client: TestClient, record: dict[str, object]) -> dict[str, object]:
    created = client.post("/api/change-sets", json={"record": record})
    assert created.status_code == 200, created.text
    answer: dict[str, object] = created.json()
    return answer


def _frontmatter_of(root: Path, diagram: str) -> dict[str, object]:
    (path,) = root.rglob(f"{diagram}*.puml")
    frontmatter = extract_yaml_block(path.read_text(encoding="utf-8"))
    assert isinstance(frontmatter, dict)
    return frontmatter


def test_a_searched_scope_is_saved_as_a_diagram_the_candidate_is_then_drawn_on(client: TestClient) -> None:
    searched = _candidate(client, {"name": "Searched", "scope": [_SERVICE]})
    ref = searched["record"]["id"]  # type: ignore[index]

    planned = client.post(f"/api/change-sets/{ref}/save-as-diagram", json={"based_on": searched["version"]})
    assert planned.status_code == 200, planned.text
    assert planned.json() == {"candidate": ref, "dry_run": True, "name": "Searched", "entities": 1, "relations": 0}

    saved = client.post(f"/api/change-sets/{ref}/save-as-diagram", json={
        "based_on": searched["version"], "name": "Promotion as searched", "dry_run": False,
    })

    assert saved.status_code == 200, saved.text
    diagram = saved.json()["diagram"]
    frontmatter = _frontmatter_of(_root(client), diagram)
    assert frontmatter["name"] == "Promotion as searched"
    assert [stable_id(str(one)) for one in frontmatter["entity-ids-used"]] == [stable_id(_SERVICE)]
    read = client.get(f"/api/change-sets/{ref}").json()
    assert read["record"]["diagram"] == diagram
    assert read["version"] == saved.json()["version"]
    assert client.get(f"/api/change-sets/{ref}/diff").json()["drawing"]["artifact_id"] == diagram


def test_what_the_candidate_creates_is_not_written_with_the_diagram(client: TestClient) -> None:
    created = client.post("/api/change-sets", json={
        "record": {"name": "With a queue", "scope": [_SERVICE]},
        "operations": [{"op": "create_entity", "fields": {
            "artifact_type": "application-component", "name": "Queue", "group": "uncategorized",
        }}],
    })
    assert created.status_code == 200, created.text
    ref = created.json()["record"]["id"]
    queue = created.json()["record"]["changes"]["operations"][0]["artifact_id"]

    saved = client.post(f"/api/change-sets/{ref}/save-as-diagram", json={
        "based_on": created.json()["version"], "dry_run": False,
    })

    assert saved.status_code == 200, saved.text
    assert saved.json()["entities"] == 1
    assert stable_id(queue) not in {stable_id(str(one)) for one in _frontmatter_of(
        _root(client), saved.json()["diagram"])["entity-ids-used"]}  # type: ignore[union-attr]
    assert not list(_root(client).rglob(f"{stable_id(queue)}*.md"))
    assert client.get(f"/api/change-sets/{ref}").json()["record"]["changes"] == created.json()["record"]["changes"]


def test_an_empty_start_has_no_view_to_save_and_writes_nothing(client: TestClient) -> None:
    empty = _candidate(client, {"name": "From nothing"})
    ref = empty["record"]["id"]  # type: ignore[index]

    refused = client.post(
        f"/api/change-sets/{ref}/save-as-diagram", json={"based_on": empty["version"], "dry_run": False},
    )

    assert refused.status_code == 422, refused.text
    assert "no view to save" in refused.text
    assert "diagram" not in client.get(f"/api/change-sets/{ref}").json()["record"]
    assert not [path for path in _root(client).rglob("*.puml") if _DIAGRAM not in path.name]


def test_a_candidate_drawn_on_a_stored_diagram_is_refused(client: TestClient) -> None:
    drawn = _candidate(client, {"name": "On a diagram", "diagram": _DIAGRAM})
    on_top = _candidate(client, {"name": "On top", "parent": drawn["record"]["id"]})  # type: ignore[index]

    for one in (drawn, on_top):
        refused = client.post(f"/api/change-sets/{one['record']['id']}/save-as-diagram", json={  # type: ignore[index]
            "based_on": one["version"], "dry_run": False,
        })
        assert refused.status_code == 409, refused.text
        assert _DIAGRAM in refused.text


def test_a_candidate_changed_since_it_was_read_is_refused_before_anything_is_written(client: TestClient) -> None:
    searched = _candidate(client, {"name": "Searched", "scope": [_SERVICE]})

    ref = searched["record"]["id"]  # type: ignore[index]
    refused = client.post(f"/api/change-sets/{ref}/save-as-diagram", json={"based_on": "stale", "dry_run": False})

    assert refused.status_code == 409, refused.text
    assert not [path for path in _root(client).rglob("*.puml") if _DIAGRAM not in path.name]


def test_an_agent_saves_the_same_diagram_through_mcp(client: TestClient) -> None:
    root = str(_root(client))
    searched = _candidate(client, {"name": "Searched by an agent", "scope": [_SERVICE]})
    ref = str(searched["record"]["id"])  # type: ignore[index]
    over_rest = client.post(
        f"/api/change-sets/{ref}/save-as-diagram", json={"based_on": searched["version"]},
    ).json()

    # REST leaves out what is null; the operation's answer is the same.
    by_mcp = mcp.change_set_save_diagram(ref, str(searched["version"]), repo_root=root)
    assert {key: value for key, value in by_mcp.items() if value is not None} == over_rest
    saved = mcp.change_set_save_diagram(ref, str(searched["version"]), dry_run=False, repo_root=root)

    assert mcp.change_set_read(ref, repo_root=root)["record"]["diagram"] == saved["diagram"]
