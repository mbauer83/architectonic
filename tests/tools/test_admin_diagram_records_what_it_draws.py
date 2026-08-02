"""`POST /admin/api/diagrams` records the entities and connections its body draws.

Without that it cannot write a diagram at all. The verifier refuses a body that draws an alias listed in
neither `entity-ids-used` nor `diagram-entities` (E315) and a relation absent from `connection-ids-used`
(E316) — correctly, because a diagram whose frontmatter does not name what it draws is one the reconcile
would silently rewrite. The route asked `resolve_diagram_selection` for four values and discarded two of
them with `_, _`, and `_write_diagram_to_enterprise` had no parameters to receive them anyway. So the
enterprise diagram-create route answered **200 with `wrote: false`** and three verification errors for
every non-empty entity selection, which is the only thing the route is for.

**Nothing saw it because nothing had ever requested the operation.** `admin_create_diagram` was one of
seven entries `NEVER_REQUESTED_OPERATIONS` held for `/admin/api/*`, dark behind `--admin-mode` being
process-wide: reaching it needed a second, sequential fixture backend, and the first run that had one
found this. The engagement route beside it passes both lists; only the admin copy dropped them.

**Driven entirely through the admin surface**, including the setup. That is not incidental — the
engagement write tools *refuse* an enterprise root (`assert_engagement_write_root`), so `/admin/api/*`
is the only way to put an entity there, and a test that arranged the content another way would be
arranging something the product cannot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    """An enterprise repository and an admin-mode app over it.

    The directory's *name* is part of the contract rather than an arrangement of this test:
    `assert_enterprise_write_root` is checked at every entry point of this surface.
    """
    from starlette.testclient import TestClient

    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.rest.routers import admin as admin_router
    from src.infrastructure.rest.routers import state as gui_state
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults
    from tests.support.api_app import build_api_app

    # Two distinct roots. The index mounts both and refuses the same path twice ("Duplicate repo root
    # in ArtifactIndex mounts"), which is right: an engagement and an enterprise repository are
    # different tiers, and a deployment where they were one would have no boundary to enforce.
    engagement = tmp_path / "engagements" / "ENG-ADMIN" / "architecture-repository"
    root = tmp_path / "enterprise-repository"
    for path in (engagement, root):
        (path / "model").mkdir(parents=True)
        ensure_arch_repo_defaults(path)

    with shared_artifact_index([engagement, root]) as index:
        gui_state.init_state(ArtifactRepository(index), engagement, root, admin_mode=True)
        yield TestClient(build_api_app(admin_router.router)), root


def _wrote(response: Any) -> str:
    """The id, having checked the write was not refused inside a success.

    The distinction this whole file is about: the route answered 201 the entire time it was broken, with
    the refusal in `verification.issues`.
    """
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload.get("wrote") is True, payload.get("verification")
    identifier = payload.get("artifact_id")
    assert isinstance(identifier, str), payload
    return identifier


def test_a_diagram_over_a_real_selection_is_written_and_names_what_it_draws(client: Any) -> None:
    """The regression and the delegation in one pass, because they are one fact seen twice.

    `wrote is True` is the regression — before the fix this was False with three verification errors.
    The frontmatter assertion is the delegation: the ids the route was given reach the file, which is
    where the verifier reads them from and therefore the only place worth checking them.
    """
    api, root = client

    first = _wrote(api.post("/admin/api/entities", json={
        "artifact_type": "application-component", "name": "Recorded One", "dry_run": False,
    }))
    second = _wrote(api.post("/admin/api/entities", json={
        "artifact_type": "application-component", "name": "Recorded Two", "dry_run": False,
    }))
    connection = _wrote(api.post("/admin/api/connections", json={
        "source_entity": first, "connection_type": "archimate-serving",
        "target_entity": second, "dry_run": False,
    }))

    diagram = _wrote(api.post("/admin/api/diagrams", json={
        "diagram_type": "archimate-application",
        "name": "Admin Selection View",
        "entity_ids": [first, second],
        "connection_ids": [connection],
        "dry_run": False,
    }))

    written = next((root / "diagram-catalog" / "diagrams").glob(f"{diagram}.puml"))
    frontmatter = yaml.safe_load(written.read_text(encoding="utf-8").split("---\n")[1])
    assert set(frontmatter["entity-ids-used"]) == {first, second}, frontmatter
    assert frontmatter["connection-ids-used"] == [connection], frontmatter
