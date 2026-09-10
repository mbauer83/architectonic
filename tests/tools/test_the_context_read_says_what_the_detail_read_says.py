"""The context read's entity is the detail read's entity, field for field.

Both are declared as `EntityDetailResponse`, and the GUI's entity page is driven by the *context*
read — so a field the detail read produces and the context read does not is a field the page cannot
show, while the contract says it can. Responses omit nulls, so the omission is invisible: the key is
simply not there, and a client reading it finds `undefined` rather than an error.

That is not hypothetical. The context projection did not carry `group`, so the entity edit form —
driven from this payload — could not show which collection an entity was filed in. Its home control
opened blank on an entity that had one, and saving would then have offered to move it out.

Asserted as a set comparison rather than a list of the fields that matter, because the next omission
will be a different field and a list of remembered ones would not mention it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    from starlette.testclient import TestClient

    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.rest.routers import state as gui_state
    from src.infrastructure.rest.routers.entities import router as entities_router
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults
    from tests.support.api_app import build_api_app

    root = tmp_path / "engagements" / "ENG-CTX" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)

    with shared_artifact_index([root]) as index:
        gui_state.init_state(ArtifactRepository(index), root, None, admin_mode=False)
        yield TestClient(build_api_app(entities_router.router))


#: Fields the context read deliberately does not repeat on its entity, because it answers them
#: better elsewhere: the per-direction connection counts are its own top-level `counts`, and
#: duplicating them on the entity would give a reader two places to look and two chances to
#: disagree. Everything else the detail read carries, the context read carries too.
CARRIED_ELSEWHERE = frozenset({"conn_in", "conn_out", "conn_sym"})


def _create(api: Any, **body: Any) -> str:
    response = api.post("/api/entities", json={"dry_run": False, **body})
    assert response.status_code in (200, 201), response.text
    return response.json()["artifact_id"]


def test_the_two_reads_report_the_same_fields(client) -> None:  # noqa: ANN001
    api = client
    artifact_id = _create(
        api, artifact_type="requirement", name="Compared Requirement", group="platform-core",
        summary="A summary, so the field is not omitted for being empty.",
    )

    detail = api.get(f"/api/entities/{artifact_id}")
    context = api.get(f"/api/entities/{artifact_id}/context")

    assert detail.status_code == 200, detail.text
    assert context.status_code == 200, context.text
    missing = sorted(set(detail.json()) - set(context.json()["entity"]) - CARRIED_ELSEWHERE)
    assert missing == [], f"the context read omits what the detail read carries: {missing}"


def test_the_context_read_says_where_the_entity_is_filed(client) -> None:
    """Named on its own because it is what the entity edit form needs, and what it lacked."""
    api = client
    artifact_id = _create(
        api, artifact_type="requirement", name="Filed Requirement", group="platform-core",
    )

    context = api.get(f"/api/entities/{artifact_id}/context")

    assert context.json()["entity"]["group"] == "platform-core"
