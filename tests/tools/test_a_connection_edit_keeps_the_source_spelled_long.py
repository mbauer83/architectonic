"""A connection file names its source in the long form, however the edit that rewrote it was addressed.

Every edit of a connection — its description, its associations, the removal of a sibling — rewrites the
whole `.outgoing.md` file, `source-entity` included. The file schema requires the slugged form, and a
short one is reported (W041). The write path spells it from the model, so the MCP tools (asserted here,
with a real write) and the REST routes (`test_gui_router_connections.py`) cannot store a short source.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from src.domain.artifact_id import stable_id
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-LONG" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


def _goal(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="goal", name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connected(repo: Path) -> tuple[str, str, str]:
    source, target, other = _goal(repo, "Source Goal"), _goal(repo, "Target Goal"), _goal(repo, "Other Goal")
    for end in (target, other):
        added = mcp.artifact_add_connection(
            source_entity=source, connection_type="archimate-association", target_entity=end,
            description="first", dry_run=False, repo_root=str(repo),
        )
        assert added["wrote"], added
    return source, target, other


def _recorded_source(repo: Path, source: str) -> str:
    (path,) = repo.glob(f"model/**/{source}.outgoing.md")
    return str(yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])["source-entity"])


def test_an_edit_addressed_by_the_short_form(repo: Path) -> None:
    source, target, _other = _connected(repo)

    edited = mcp.artifact_edit_connection(
        source_entity=stable_id(source), connection_type="archimate-association", target_entity=stable_id(target),
        description="edited", dry_run=False, repo_root=str(repo),
    )

    assert edited["wrote"], edited
    assert _recorded_source(repo, source) == source


def test_a_removal_addressed_by_the_short_form(repo: Path) -> None:
    source, target, _other = _connected(repo)

    removed = mcp.artifact_edit_connection(
        source_entity=stable_id(source), connection_type="archimate-association", target_entity=stable_id(target),
        operation="remove", dry_run=False, repo_root=str(repo),
    )

    assert removed["wrote"], removed
    assert _recorded_source(repo, source) == source


def test_an_association_change_addressed_by_the_short_form(repo: Path) -> None:
    source, target, other = _connected(repo)

    associated = mcp.artifact_edit_connection_associations(
        source_entity=stable_id(source), connection_type="archimate-association", target_entity=stable_id(target),
        add_entities=[other], dry_run=False, repo_root=str(repo),
    )

    assert associated["wrote"], associated
    assert _recorded_source(repo, source) == source
