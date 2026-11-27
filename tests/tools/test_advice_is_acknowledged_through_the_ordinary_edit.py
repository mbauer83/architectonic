"""An element acknowledges advice through the ordinary entity edit, by REST and by MCP alike.

Stored in the element's own frontmatter as `accepted-advice: [{code, reason}]`, written by the entity
formatter and read back by the one reader in `verification_advice` — tested here as a pair, over the
reasons YAML has to quote. Only advice can be acknowledged: a warning or an error code is refused at
the write, by both surfaces, and an edit that does not mention the field keeps what is stored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.domain.repository.frontmatter import parse_frontmatter
from src.domain.verification_advice import AcceptedAdvice, accepted_advice_from_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities.router import router as entities_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

_REASON = "A checklist: the steps run in any order."


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-ADVICE" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def client(repo: Path):
    from starlette.testclient import TestClient

    gui_state.init_state(ArtifactRepository(shared_artifact_index([repo])), repo, None)
    return TestClient(build_api_app(entities_router))


def _process(repo: Path, **fields: object) -> tuple[str, Path]:
    result = mcp.artifact_create_entity(
        artifact_type="process", name="Handle Order", summary="A process.", dry_run=False, repo_root=str(repo),
        **fields,  # type: ignore[arg-type]
    )
    assert result["wrote"], result
    return str(result["artifact_id"]), Path(str(result["path"]))


def _stored(path: Path) -> tuple[AcceptedAdvice, ...]:
    return accepted_advice_from_frontmatter(parse_frontmatter(path.read_text(encoding="utf-8")).get("accepted-advice"))


@pytest.mark.verifies("REQ@1795776616.gmLsdPo")
def test_rest_stores_an_acknowledgement_in_the_element(client, repo: Path) -> None:
    artifact_id, path = _process(repo)

    response = client.patch(
        f"/api/entities/{artifact_id}",
        json={"accepted_advice": [{"code": "A341", "reason": _REASON}], "dry_run": False},
    )

    assert response.status_code == 200, response.text
    assert _stored(path) == (AcceptedAdvice("A341", _REASON),)


@pytest.mark.parametrize("code", ["W307", "E340"])
def test_rest_refuses_to_acknowledge_a_warning_or_an_error(client, repo: Path, code: str) -> None:
    artifact_id, path = _process(repo)

    response = client.patch(
        f"/api/entities/{artifact_id}",
        json={"accepted_advice": [{"code": code, "reason": "deliberate"}], "dry_run": False},
    )

    assert response.status_code == 400, response.text
    assert "only advice can be acknowledged" in response.text
    assert _stored(path) == ()


def test_rest_refuses_an_entry_of_the_wrong_shape(client, repo: Path) -> None:
    artifact_id, _path = _process(repo)

    response = client.patch(
        f"/api/entities/{artifact_id}",
        json={"accepted_advice": [{"code": "A341", "reason": "r", "by": "someone"}], "dry_run": False},
    )

    assert response.status_code == 422, response.text


def test_mcp_edit_stores_and_an_unrelated_edit_keeps_it(repo: Path) -> None:
    artifact_id, path = _process(repo)

    mcp.artifact_edit_entity(
        artifact_id=artifact_id, accepted_advice=[{"code": "A341", "reason": _REASON}],  # type: ignore[list-item]
        dry_run=False, repo_root=str(repo),
    )
    mcp.artifact_edit_entity(artifact_id=artifact_id, summary="Still a process.", dry_run=False, repo_root=str(repo))

    assert _stored(path) == (AcceptedAdvice("A341", _REASON),)


def test_mcp_edit_refuses_a_warning_code(repo: Path) -> None:
    artifact_id, path = _process(repo)

    with pytest.raises(ValueError, match="W307 is a warning"):
        mcp.artifact_edit_entity(
            artifact_id=artifact_id, accepted_advice=[{"code": "W307", "reason": "r"}],  # type: ignore[list-item]
            dry_run=False, repo_root=str(repo),
        )
    assert _stored(path) == ()


def test_an_empty_list_clears_the_acknowledgements(repo: Path) -> None:
    artifact_id, path = _process(repo, accepted_advice=[{"code": "A341", "reason": _REASON}])
    assert _stored(path) == (AcceptedAdvice("A341", _REASON),)

    mcp.artifact_edit_entity(artifact_id=artifact_id, accepted_advice=[], dry_run=False, repo_root=str(repo))

    assert _stored(path) == ()
    assert "accepted-advice" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("reason", [
    "plain",
    "Reason: with a colon",
    "'single' and \"double\" quotes",
    "# not a comment",
    "- not a list item",
    "ünïcode — and a dash",
    "yes",
    "null",
    "123",
    "x" * 280,
])
def test_the_writer_and_the_reader_agree_over_what_a_reason_may_say(repo: Path, reason: str) -> None:
    """The round trip over what the syntax permits: any reason the check accepts, through the entity
    formatter and back through the frontmatter reader and the acknowledgement reader."""
    _artifact_id, path = _process(repo, accepted_advice=[{"code": "A341", "reason": reason}])

    assert _stored(path) == (AcceptedAdvice("A341", reason.strip()),)


def test_the_index_carries_the_acknowledgement_the_rule_reads(repo: Path) -> None:
    """The rule reads the element through the index's point lookup; it must see what the file says."""
    artifact_id, _path = _process(repo, accepted_advice=[{"code": "A341", "reason": _REASON}])
    index = shared_artifact_index(repo)
    index.refresh()

    record = index.get_entity(artifact_id)

    assert record is not None
    assert accepted_advice_from_frontmatter(record.extra.get("accepted-advice")) == (AcceptedAdvice("A341", _REASON),)
