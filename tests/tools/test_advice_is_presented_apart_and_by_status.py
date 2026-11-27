"""Advice is reported apart from errors and warnings, and how loudly follows the element's status.

`artifact_verify` counts it on its own (`counts.advice`, `counts.advice_by_status`) and lists it under
its own key — in the summary only for active elements, in `full` for all — while the per-file results
keep only what is wrong. The promotion dry run shows the open advice on what it would carry, apart
from `schema_errors`, because advice never blocks a promotion. The entity read serves the element's
open and acknowledged advice for its page.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

_REASON = "A checklist: the steps run in any order."


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-ADVP" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _create(repo: Path, atype: str, name: str, **fields: object) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=atype, name=name, summary=f"{name}.", dry_run=False, repo_root=str(repo),
        **fields,  # type: ignore[arg-type]
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _sequence(repo: Path, name: str, *, status: str = "draft", **fields: object) -> str:
    whole = _create(repo, "process", name, status=status, **fields)
    for step in ("First", "Second"):
        part = _create(repo, "process", f"{name} {step}")
        added = mcp.artifact_add_connection(
            source_entity=whole, connection_type="archimate-composition", target_entity=part,
            dry_run=False, repo_root=str(repo),
        )
        assert added["wrote"], added
    return whole


def _verify(repo: Path, return_mode: str = "summary") -> dict:
    return asyncio.run(mcp.artifact_verify(
        repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True,
        return_mode=return_mode,  # type: ignore[arg-type]
    ))


def test_artifact_verify_counts_advice_on_its_own_and_lists_only_an_active_elements(repo: Path) -> None:
    draft = _sequence(repo, "Draft Flow")
    active = _sequence(repo, "Active Flow", status="active")

    verified = _verify(repo)

    counts = verified["counts"]
    assert counts["advice"] == 2
    assert counts["advice_by_status"] == {"active": 1, "draft": 1}
    assert counts["errors"] == 0 and counts["warnings"] == 0, verified["results"]
    listed = {issue["details"]["artifact_id"] for issue in verified["advice"]}
    assert listed == {active}, "a draft's advice is a count in the summary, not a listing"
    assert draft not in listed
    assert all(
        issue["severity"] != "advice" for result in verified["results"] for issue in result["issues"]
    ), "advice is reported apart from the per-file results"


def test_artifact_verify_full_lists_every_advice(repo: Path) -> None:
    draft = _sequence(repo, "Draft Flow")
    active = _sequence(repo, "Active Flow", status="active")

    verified = _verify(repo, "full")

    assert {issue["details"]["artifact_id"] for issue in verified["advice"]} == {draft, active}
    assert {issue["details"]["status"] for issue in verified["advice"]} == {"draft", "active"}


def test_an_acknowledged_advice_is_neither_counted_nor_listed(repo: Path) -> None:
    _sequence(repo, "Checklist", status="active", accepted_advice=[{"code": "A341", "reason": _REASON}])

    verified = _verify(repo, "full")

    assert verified["counts"]["advice"] == 0
    assert verified["advice"] == []


def _promotion_plan(repo: Path, entity_id: str):
    index = shared_artifact_index([repo])
    index.refresh()
    return plan_promotion(entity_id, ArtifactRegistry(index), ArtifactRepository(index))


def test_the_promotion_dry_run_shows_advice_and_is_not_blocked_by_it(repo: Path) -> None:
    whole = _sequence(repo, "Order Handling", status="active")

    plan = _promotion_plan(repo, whole)

    assert [issue.code for issue in plan.advice] == ["A341"]
    assert plan.advice[0].details is not None and plan.advice[0].details["artifact_id"] == whole
    assert not [error for error in plan.schema_errors if "A341" in error], "advice never blocks"


def test_an_acknowledged_advice_is_quiet_in_the_promotion_dry_run(repo: Path) -> None:
    whole = _sequence(repo, "Checklist", accepted_advice=[{"code": "A341", "reason": _REASON}])

    assert _promotion_plan(repo, whole).advice == []


def test_the_promotion_response_carries_the_advice(repo: Path) -> None:
    whole = _sequence(repo, "Order Handling")

    planned = mcp.artifact_promote_to_enterprise(entity_id=whole, dry_run=True, repo_root=str(repo))

    assert [issue["code"] for issue in planned["advice"]] == ["A341"]


# ── the entity read the page is built from ──────────────────────────────────


@pytest.fixture()
def client(repo: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.rest.routers import state as gui_state
    from src.infrastructure.rest.routers.entities.router import router as entities_router
    from tests.support.api_app import build_api_app

    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    return TestClient(build_api_app(entities_router))


def test_the_entity_read_serves_open_advice_with_its_status(client, repo: Path) -> None:
    whole = _sequence(repo, "Order Handling", status="active")

    body = client.get(f"/api/entities/{whole}").json()

    assert [issue["code"] for issue in body["advice"]["open"]] == ["A341"]
    assert body["advice"]["open"][0]["details"]["status"] == "active"
    assert body["advice"]["accepted"] == []


def test_the_entity_read_serves_an_acknowledgement_in_place_of_the_advice(client, repo: Path) -> None:
    whole = _sequence(repo, "Checklist", accepted_advice=[{"code": "A341", "reason": _REASON}])

    body = client.get(f"/api/entities/{whole}").json()

    assert body["advice"]["open"] == []
    (accepted,) = body["advice"]["accepted"]
    assert accepted["code"] == "A341" and accepted["reason"] == _REASON and accepted["title"]
