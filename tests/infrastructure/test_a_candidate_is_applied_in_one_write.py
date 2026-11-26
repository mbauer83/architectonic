"""Applying a candidate writes all of its operations in one staged transaction, or none of them.

The candidate here holds every kind the apply has to carry at once — a create, an edit, a connection
added and one removed, and an entity removed — so the entity removal, which the public bulk write
leaves to the bulk delete, is proven to ride in the same batch. A refusal raised by the last item to
be staged leaves the model exactly as it was.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.modeling.artifact_write import generate_entity_id
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as model
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.mcp.artifact_mcp.bulk import write as bulk_write
from src.infrastructure.rest.routers import candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test

_REALIZES = "archimate-realization"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (repo / "model").mkdir(parents=True)
    (repo / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return repo


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router)) as served:
            yield served
    finally:
        reset_state_for_test()


@pytest.fixture
def commits(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every staged transaction the bulk write commits, by live root."""
    seen: list[Path] = []
    commit = bulk_write.commit_staged_repo

    def counted(**kwargs: Any) -> None:
        seen.append(kwargs["live_root"])
        commit(**kwargs)

    monkeypatch.setattr(bulk_write, "commit_staged_repo", counted)
    return seen


def _entity(root: Path, artifact_type: str, name: str) -> str:
    made = model.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(root))
    assert made["wrote"], made
    return str(made["artifact_id"])


def _connect(root: Path, source: str, target: str) -> None:
    made = model.artifact_add_connection(
        source_entity=source, connection_type=_REALIZES, target_entity=target, dry_run=False, repo_root=str(root),
    )
    assert made["wrote"], made


def _candidate(client: TestClient, *intents: dict[str, Any]) -> str:
    created = client.post("/api/change-sets", json={"record": {"name": "Replace the rule"}}).json()
    ref, version = created["record"]["id"], created["version"]
    for intent in intents:
        recorded = client.post(f"/api/change-sets/{ref}/operations", json={"based_on": version, "operations": [intent]})
        assert recorded.status_code == 200, recorded.text
        version = recorded.json()["version"]
    return ref


def _names(root: Path) -> dict[str, str]:
    """Every entity's name, by the id a rename does not change."""
    return {stable_id(entity.artifact_id): entity.name for entity in shared_artifact_index([root]).list_entities()}


def _connections(root: Path) -> set[tuple[str, str]]:
    """Every connection's ends, by the ids a rename does not change."""
    return {(stable_id(c.source), stable_id(c.target)) for c in shared_artifact_index([root]).list_connections()}


def _state(client: TestClient, ref: str) -> str:
    return client.get(f"/api/change-sets/{ref}").json()["record"]["state"]


@pytest.mark.verifies("REQ@1795548363.kNlXgAA")
def test_a_create_an_edit_a_connection_and_a_removal_land_in_one_write(
    root: Path, client: TestClient, commits: list[Path],
) -> None:
    ledger = _entity(root, "application-component", "Ledger")
    billing = _entity(root, "application-component", "Billing")
    old_rule = _entity(root, "requirement", "Old rule")
    _connect(root, billing, old_rule)
    new_rule = generate_entity_id("REQ", "New rule")
    ref = _candidate(
        client,
        {"op": "create_entity", "artifact_id": new_rule,
         "fields": {"artifact_type": "requirement", "name": "New rule", "group": "uncategorized"}},
        {"op": "edit_entity", "artifact_id": ledger, "field": "name", "value": "Ledger service"},
        {"op": "add_connection", "source_entity": ledger, "connection_type": _REALIZES, "target_entity": new_rule},
        {"op": "remove_connection", "source_entity": billing, "connection_type": _REALIZES, "target_entity": old_rule},
        {"op": "remove_entity", "artifact_id": old_rule},
    )

    preview = client.post(f"/api/change-sets/{ref}/apply", json={})
    assert preview.status_code == 200, preview.text
    assert "refusal" not in preview.json() and preview.json()["integrated"] is False
    assert {item["standing"] for item in preview.json()["standing"]} == {"applies"}
    assert commits == [] and stable_id(old_rule) in _names(root)

    applied = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})

    assert applied.status_code == 200, applied.text
    assert applied.json()["integrated"] is True
    assert commits == [root]
    names = _names(root)
    assert names[stable_id(ledger)] == "Ledger service" and names[stable_id(new_rule)] == "New rule"
    assert stable_id(old_rule) not in names
    assert _connections(root) == {(stable_id(ledger), stable_id(new_rule))}
    assert _state(client, ref) == "integrated"
    again = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})
    assert again.status_code == 409 and "integrated" in again.text


def test_a_refusal_by_the_last_operation_staged_leaves_the_model_unchanged(
    root: Path, client: TestClient, commits: list[Path],
) -> None:
    ledger = _entity(root, "application-component", "Ledger")
    billing = _entity(root, "application-component", "Billing")
    old_rule = _entity(root, "requirement", "Old rule")
    _connect(root, billing, old_rule)
    new_rule = generate_entity_id("REQ", "New rule")
    # The removal is staged last, after the create and the edit, and is refused: Billing still
    # realizes the rule, and nothing in the candidate removes that connection.
    ref = _candidate(
        client,
        {"op": "create_entity", "artifact_id": new_rule,
         "fields": {"artifact_type": "requirement", "name": "New rule", "group": "uncategorized"}},
        {"op": "edit_entity", "artifact_id": ledger, "field": "name", "value": "Ledger service"},
        {"op": "remove_entity", "artifact_id": old_rule},
    )
    before, joined = _names(root), _connections(root)

    preview = mcp.change_set_apply(ref, repo_root=str(root))
    refused = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False})

    assert "still referenced" in preview["refusal"]
    assert refused.status_code == 409 and "still referenced" in refused.text
    assert commits == []
    assert _names(root) == before and stable_id(new_rule) not in before
    assert _connections(root) == joined
    assert _state(client, ref) == "draft"


def test_the_dry_run_says_what_each_edit_replaces_and_nothing_for_a_create(root: Path, client: TestClient) -> None:
    """An edit of a content field is based on a revision, so the operation alone cannot say what it replaces;
    the dry run reads it from the model, as the apply would overwrite it."""
    ledger = _entity(root, "application-component", "Ledger")
    ref = _candidate(
        client,
        {"op": "edit_entity", "artifact_id": ledger, "field": "summary", "value": "Keeps every posting twice."},
        {"op": "create_entity",
         "fields": {"artifact_type": "requirement", "name": "New rule", "group": "uncategorized"}},
    )

    standing = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": True}).json()["standing"]

    edits = [item for item in standing if item["operation"]["op"] == "edit_entity"]
    assert [item["operation"]["value"] for item in edits] == ["Keeps every posting twice."]
    assert all("holds" in item for item in edits)
    assert all("holds" not in item for item in standing if item["operation"]["op"] == "create_entity")
    over_mcp = mcp.change_set_apply(ref, dry_run=True, repo_root=str(root))["standing"]
    assert [item.get("holds") for item in over_mcp] == [item.get("holds") for item in standing]


def test_where_the_model_holds_nothing_both_transports_say_so(root: Path, client: TestClient) -> None:
    """A property the entity does not hold is read, and found empty: `holds` is present and null over REST as
    over MCP, distinct from an operation whose place was not read at all (no `holds`)."""
    made = model.artifact_create_entity(
        artifact_type="application-component", name="Ledger", properties={"owner": "Finance"},
        dry_run=False, repo_root=str(root),
    )
    assert made["wrote"], made
    ref = _candidate(
        client,
        {"op": "edit_entity", "artifact_id": str(made["artifact_id"]), "field": "properties", "key": "tier",
         "value": "gold"},
    )

    over_rest = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": True}).json()["standing"]
    over_mcp = mcp.change_set_apply(ref, dry_run=True, repo_root=str(root))["standing"]

    for standing in (over_rest, over_mcp):
        assert [("holds" in item, item.get("holds")) for item in standing] == [(True, None)]
    read = client.get(f"/api/change-sets/{ref}/standing").json()["standing"]
    assert [("holds" in item, item.get("holds")) for item in read] == [(True, None)]


def test_both_transports_answer_an_apply_alike(root: Path, client: TestClient) -> None:
    ledger = _entity(root, "application-component", "Ledger")
    ref = _candidate(client, {"op": "edit_entity", "artifact_id": ledger, "field": "name", "value": "Ledger service"})

    def answered(answer: dict[str, Any]) -> dict[str, Any]:
        """The answer without the write's operation id, which is new on every call, and without nulls."""
        return {key: value for key, value in answer.items() if key != "operation_id" and value is not None}

    over_rest = client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": True}).json()
    assert answered(over_rest) == answered(mcp.change_set_apply(ref, dry_run=True, repo_root=str(root)))

    applied = mcp.change_set_apply(ref, dry_run=False, repo_root=str(root))
    assert applied["integrated"] is True and _names(root)[stable_id(ledger)] == "Ledger service"
    with pytest.raises(ValueError, match="integrated"):
        mcp.change_set_apply(ref, dry_run=False, repo_root=str(root))
    assert client.post(f"/api/change-sets/{ref}/apply", json={}).json()["refusal"].startswith(ref)


def test_an_applied_edit_of_a_list_field_differs_from_the_model_in_nothing(root: Path, client: TestClient) -> None:
    """The model reads `keywords` as a tuple and the candidate states it as a list: compared by `==`, an edit
    already applied was answered as its value replaced by itself, and the page struck it and added it again."""
    made = model.artifact_create_entity(
        artifact_type="application-component", name="Indexer", keywords=["search"], dry_run=False,
        repo_root=str(root),
    )
    ref = _candidate(client, {"op": "edit_entity", "artifact_id": made["artifact_id"], "field": "keywords",
                              "value": ["applied"]})
    assert client.get(f"/api/change-sets/{ref}/diff").json()["diff"][0]["fields"]["keywords"] == {
        "before": ["search"], "after": ["applied"]}

    assert client.post(f"/api/change-sets/{ref}/apply", json={"dry_run": False}).status_code == 200

    after = client.get(f"/api/change-sets/{ref}/diff").json()
    assert after["diff"] == []
    assert [item["standing"] for item in after["standing"]] == ["already-there"]
