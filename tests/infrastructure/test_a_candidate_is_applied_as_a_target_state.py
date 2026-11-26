"""A candidate applied as a target state stands beside the baseline, and moving it in leaves one state.

The candidate adds a requirement, renames a component and connects the two, and removes another
requirement. Applied as a target state, the model keeps the originals as they were and gains a draft
requirement, a "Ledger (target)" copy carrying the rename and the new relation, a trace from the copy to
the original, a Baseline and a Target plateau aggregating originals and replacements, and a «gap»
associated with both. Moving it into the baseline applies the kept operations to the originals, keeps a
relation drawn to the copy meanwhile, removes the copy, the plateaus and the gap, and integrates the
candidate. All of it over REST and MCP alike, through the one staged write.
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
from src.infrastructure.rest.routers import candidate_target_state, candidates, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test

_REALIZES = "archimate-realization"
_SERVES = "archimate-serving"


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
        with TestClient(build_api_app(candidates.router, candidate_target_state.router)) as served:
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


def _connect(root: Path, source: str, kind: str, target: str) -> None:
    made = model.artifact_add_connection(
        source_entity=source, connection_type=kind, target_entity=target, dry_run=False, repo_root=str(root),
    )
    assert made["wrote"], made


def _candidate(client: TestClient, *intents: dict[str, Any]) -> str:
    created = client.post("/api/candidates", json={"record": {"name": "Ledger realizes the rule"}}).json()
    ref, version = created["record"]["id"], created["version"]
    recorded = client.post(f"/api/candidates/{ref}/operations", json={"based_on": version, "operations": intents})
    assert recorded.status_code == 200, recorded.text
    return str(ref)


def _entities(root: Path) -> dict[str, Any]:
    return {stable_id(e.artifact_id): e for e in shared_artifact_index([root]).list_entities()}


def _connections(root: Path) -> set[tuple[str, str, str]]:
    return {
        (stable_id(c.source), c.conn_type, stable_id(c.target))
        for c in shared_artifact_index([root]).list_connections()
    }


def _record(client: TestClient, ref: str) -> dict[str, Any]:
    return dict(client.get(f"/api/candidates/{ref}").json())


@pytest.fixture
def scene(root: Path, client: TestClient) -> dict[str, str]:
    ledger = _entity(root, "application-component", "Ledger")
    billing = _entity(root, "application-component", "Billing")
    old_rule = _entity(root, "requirement", "Old rule")
    _connect(root, billing, _SERVES, ledger)
    new_rule = generate_entity_id("REQ", "New rule")
    ref = _candidate(
        client,
        {"op": "create_entity", "artifact_id": new_rule,
         "fields": {"artifact_type": "requirement", "name": "New rule", "group": "uncategorized"}},
        {"op": "edit_entity", "artifact_id": ledger, "field": "name", "value": "Ledger service"},
        {"op": "add_connection", "source_entity": ledger, "connection_type": _REALIZES, "target_entity": new_rule},
        {"op": "remove_entity", "artifact_id": old_rule},
    )
    return {"ledger": stable_id(ledger), "billing": stable_id(billing), "old_rule": stable_id(old_rule),
            "new_rule": stable_id(new_rule), "candidate": ref}


def test_a_target_state_stands_beside_the_baseline(
    root: Path, client: TestClient, commits: list[Path], scene: dict[str, str],
) -> None:
    ref, ledger = scene["candidate"], scene["ledger"]
    preview = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={})
    assert preview.status_code == 200, preview.text
    assert preview.json()["applied"] is False and commits == []
    planned = preview.json()["target_state"]
    assert set(planned["copies"]) == {ledger}
    # Shown by the ids they are given: a reader is never shown an alias the write resolves.
    assert "$ref:" not in str(preview.json()["operations"])
    assert planned["target"] in str(preview.json()["operations"])

    applied = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False})

    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True and commits == [root]
    ids = applied.json()["target_state"]
    copy = stable_id(ids["copies"][ledger])
    baseline, target, gap = (stable_id(ids[key]) for key in ("baseline", "target", "gap"))
    entities = _entities(root)
    assert entities[ledger].name == "Ledger"  # the original is not changed
    assert scene["old_rule"] in entities  # nor is what the candidate removes
    assert entities[copy].name == "Ledger service (target)" and entities[copy].status == "draft"
    assert entities[copy].artifact_type == "application-component"
    assert entities[scene["new_rule"]].status == "draft"
    assert entities[baseline].artifact_type == entities[target].artifact_type == "plateau"
    assert entities[gap].artifact_type == "assessment" and "gap" in entities[gap].specializations
    joined = _connections(root)
    assert (copy, "archimate-association", ledger) in joined  # the trace
    assert (copy, _REALIZES, scene["new_rule"]) in joined  # the candidate's relation, on the copy
    assert (scene["billing"], _SERVES, copy) in joined  # the original's relation, copied
    assert (scene["billing"], _SERVES, ledger) in joined  # and still the original's
    holds = "archimate-aggregation"
    assert {(target, holds, copy), (target, holds, scene["new_rule"]),
            (baseline, holds, ledger), (baseline, holds, scene["old_rule"])} <= joined
    assert {(gap, "archimate-association", baseline), (gap, "archimate-association", target)} <= joined
    record = _record(client, ref)["record"]
    assert record["state"] == "candidate" and record["target-state"]["gap"] == ids["gap"]


def test_while_its_target_state_stands_a_candidate_is_held(
    root: Path, client: TestClient, scene: dict[str, str],
) -> None:
    ref = scene["candidate"]
    assert client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).status_code == 200
    read = _record(client, ref)

    again = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False})
    direct = client.post(f"/api/candidates/{ref}/apply", json={"dry_run": False})
    rejected = client.patch(f"/api/candidates/{ref}", json={"based_on": read["version"], "patch": {"state": "draft"}})
    emptied = client.patch(
        f"/api/candidates/{ref}",
        json={"based_on": read["version"], "patch": {"changes": {**read["record"]["changes"], "operations": []}}},
    )
    deleted = client.delete(f"/api/candidates/{ref}", params={"dry_run": "false"})

    for refused in (again, direct, deleted):
        assert refused.status_code == 409 and "target state" in refused.text, refused.text
    for refused in (rejected, emptied):
        assert refused.status_code == 409 and "target state" in refused.text, refused.text
    renamed = client.patch(f"/api/candidates/{ref}", json={"based_on": read["version"], "patch": {"name": "Renamed"}})
    assert renamed.status_code == 200, renamed.text


def test_moving_into_the_baseline_leaves_one_state(
    root: Path, client: TestClient, commits: list[Path], scene: dict[str, str],
) -> None:
    ref, ledger = scene["candidate"], scene["ledger"]
    ids = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).json()["target_state"]
    copy = stable_id(ids["copies"][ledger])
    # Drawn to the copy while the target state stood: the move carries it to the original.
    reporting = _entity(root, "application-component", "Reporting")
    _connect(root, reporting, _SERVES, copy)
    commits.clear()

    preview = client.post(f"/api/candidates/{ref}/move-into-baseline", json={})
    assert preview.status_code == 200, preview.text
    assert preview.json()["integrated"] is False and "refusal" not in preview.json() and commits == []

    moved = client.post(f"/api/candidates/{ref}/move-into-baseline", json={"dry_run": False})

    assert moved.status_code == 200, moved.text
    assert moved.json()["integrated"] is True and commits == [root]
    entities = _entities(root)
    assert entities[ledger].name == "Ledger service"
    assert entities[scene["new_rule"]].status == "active"
    assert scene["old_rule"] not in entities
    assert not {copy, *(stable_id(ids[key]) for key in ("baseline", "target", "gap"))} & set(entities)
    joined = _connections(root)
    assert (ledger, _REALIZES, scene["new_rule"]) in joined
    assert (stable_id(reporting), _SERVES, ledger) in joined
    assert (scene["billing"], _SERVES, ledger) in joined
    assert not any(copy in (source, target) for source, _kind, target in joined)
    record = _record(client, ref)["record"]
    assert record["state"] == "integrated" and "target-state" not in record
    again = client.post(f"/api/candidates/{ref}/move-into-baseline", json={"dry_run": False})
    assert again.status_code == 409 and "not in the model as a target state" in again.text


def test_a_move_over_an_original_changed_meanwhile_is_refused_until_re_based(
    root: Path, client: TestClient, scene: dict[str, str],
) -> None:
    ref, ledger = scene["candidate"], scene["ledger"]
    assert client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).status_code == 200
    edited = model.artifact_edit_entity(artifact_id=ledger, name="Ledger core", dry_run=False, repo_root=str(root))
    assert edited["wrote"], edited

    refused = client.post(f"/api/candidates/{ref}/move-into-baseline", json={"dry_run": False})
    assert refused.status_code == 409 and "re-based" in refused.text
    read = _record(client, ref)
    rebased = client.post(f"/api/candidates/{ref}/rebase", json={"based_on": read["version"]})
    assert rebased.status_code == 200, rebased.text

    moved = client.post(f"/api/candidates/{ref}/move-into-baseline", json={"dry_run": False})
    assert moved.status_code == 200, moved.text
    assert _entities(root)[ledger].name == "Ledger service"


def test_both_transports_answer_alike(root: Path, client: TestClient, scene: dict[str, str]) -> None:
    ref = scene["candidate"]

    def answered(answer: dict[str, Any]) -> dict[str, Any]:
        """Without the ids minted afresh on every dry run, and without nulls."""
        return {key: value for key, value in answer.items()
                if key not in {"operation_id", "target_state", "operations"} and value is not None}

    over_rest = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": True}).json()
    over_mcp = mcp.candidate_apply_as_target_state(ref, dry_run=True, repo_root=str(root))
    assert answered(over_rest) == answered(over_mcp)
    assert len(over_rest["operations"]) == len(over_mcp["operations"])

    applied = mcp.candidate_apply_as_target_state(ref, dry_run=False, repo_root=str(root))
    assert applied["applied"] is True
    moved = mcp.candidate_move_into_baseline(ref, dry_run=False, repo_root=str(root))
    assert moved["integrated"] is True
    with pytest.raises(ValueError, match="not in the model as a target state"):
        mcp.candidate_move_into_baseline(ref, dry_run=False, repo_root=str(root))


def test_an_element_the_candidate_created_is_compared_once_when_the_model_holds_it(
    client: TestClient, scene: dict[str, str],
) -> None:
    """Once applied as a target state, the element the candidate creates is in the model under the id chosen for
    it. The comparison read it from the model by that id and from the candidate by its alias, and listed it twice:
    once removed, once added."""
    ref, new_rule = scene["candidate"], scene["new_rule"]
    assert client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).status_code == 200

    compared = client.get(f"/api/candidates/{ref}/diff", params={"base": "model"}).json()

    about_it = [row for row in compared["diff"] if row["kind"] == "entity"
                and stable_id(str(row["target"]).removeprefix("$ref:")) in {new_rule, "new-rule"}
                or "New rule" in str(row["fields"])]
    assert len(about_it) <= 1, about_it  # held by the model as the candidate creates it: no change at all
    named = [one for one in compared["view"]["entities"]
             if stable_id(one.get("artifact_id") or one["id"]) == new_rule or one["id"] == new_rule]
    assert len(named) == 1, compared["view"]["entities"]


def test_withdrawing_a_target_state_leaves_the_baseline_as_it_was(
    root: Path, client: TestClient, commits: list[Path], scene: dict[str, str],
) -> None:
    ref = scene["candidate"]
    before_entities, before_connections = set(_entities(root)), _connections(root)
    assert client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).status_code == 200
    commits.clear()

    preview = client.post(f"/api/candidates/{ref}/withdraw-target-state", json={})
    assert preview.status_code == 200, preview.text
    assert preview.json()["released"] is False and "refusal" not in preview.json() and commits == []
    assert {op["op"] for op in preview.json()["operations"]} == {"remove_connection", "remove_entity"}

    withdrawn = client.post(f"/api/candidates/{ref}/withdraw-target-state", json={"dry_run": False})

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["released"] is True and commits == [root]
    assert set(_entities(root)) == before_entities
    assert _connections(root) == before_connections
    record = _record(client, ref)["record"]
    assert record["state"] == "draft" and "target-state" not in record
    # Released: it may be applied as a target state again, or set aside, or deleted.
    again = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": True})
    assert again.status_code == 200 and "refusal" not in again.json(), again.text
    gone = client.post(f"/api/candidates/{ref}/withdraw-target-state", json={"dry_run": False})
    assert gone.status_code == 409 and "not in the model as a target state" in gone.text


def test_a_withdrawal_names_what_was_written_since_and_refuses_until_it_is_resolved(
    root: Path, client: TestClient, commits: list[Path], scene: dict[str, str],
) -> None:
    ref, ledger = scene["candidate"], scene["ledger"]
    ids = client.post(f"/api/candidates/{ref}/apply-as-target-state", json={"dry_run": False}).json()["target_state"]
    copy = stable_id(ids["copies"][ledger])
    # Drawn to the copy while the target state stood, and a diagram drawing it: neither is the target state's.
    reporting = _entity(root, "application-component", "Reporting")
    _connect(root, reporting, _SERVES, copy)
    drawn = model.artifact_create_diagram(
        diagram_type="archimate-application", name="Target picture", entity_ids=[copy, ledger],
        dry_run=False, repo_root=str(root),
    )
    assert drawn["wrote"], drawn
    commits.clear()

    preview = client.post(f"/api/candidates/{ref}/withdraw-target-state", json={})
    refusal = preview.json()["refusal"]
    assert stable_id(reporting) in refusal and stable_id(str(drawn["artifact_id"])) in refusal
    refused = client.post(f"/api/candidates/{ref}/withdraw-target-state", json={"dry_run": False})
    assert refused.status_code == 409 and commits == []
    assert copy in _entities(root)  # nothing was removed
    assert _record(client, ref)["record"]["target-state"]["gap"] == ids["gap"]

    model.artifact_delete_diagram(artifact_id=str(drawn["artifact_id"]), dry_run=False, repo_root=str(root))
    cut = model.artifact_edit_connection(
        source_entity=reporting, connection_type=_SERVES, target_entity=copy, operation="remove",
        dry_run=False, repo_root=str(root),
    )
    assert cut["wrote"], cut
    withdrawn = mcp.candidate_withdraw_target_state(ref, dry_run=False, repo_root=str(root))
    assert withdrawn["released"] is True and copy not in _entities(root)
