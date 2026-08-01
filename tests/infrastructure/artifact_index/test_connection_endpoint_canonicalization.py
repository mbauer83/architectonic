"""A connection naming its target by an older slug still joins to that entity.

The slug tail is a human-readable hint; identity is the ``PREFIX@epoch.random`` stem. A
record left holding the literal file text resolves no name and matches no entity in a
population join, so the connection vanishes from queries, explorations and diagrams while
the file still looks correct and every resolver still accepts the reference. Canonicalizing
endpoints as records enter the read model keeps the leniency honest end to end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.parsing import parse_outgoing_file
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-CANON" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _drift(repo: Path, source_id: str, target_id: str) -> Path:
    """Rewrite the referrer to name *target_id* by a slug the entity does not have."""
    path = next(repo.rglob(f"{source_id}.outgoing.md"))
    stem = target_id.rsplit(".", 1)[0]
    path.write_text(
        path.read_text(encoding="utf-8").replace(target_id, f"{stem}.a-former-slug"),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def drifted(repo: Path) -> tuple[Path, str, str]:
    source = _entity(repo, "requirement", "Drift Source")
    target = _entity(repo, "outcome", "Drift Target")
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type="archimate-realization",
        description="Realizes it.", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    _drift(repo, source, target)
    return repo, source, target


def test_the_endpoint_resolves_to_the_current_id(drifted: tuple[Path, str, str]) -> None:
    repo, source, target = drifted

    index = shared_artifact_index([repo])
    index.refresh()
    outgoing = index.find_connections_for(source, direction="outbound")

    assert [c.target for c in outgoing] == [target]


def test_the_target_entity_is_reachable_from_the_connection(drifted: tuple[Path, str, str]) -> None:
    """A target that does not resolve renders as a nameless, unclickable node."""
    repo, source, _target = drifted

    index = shared_artifact_index([repo])
    index.refresh()
    connection = index.find_connections_for(source, direction="outbound")[0]

    assert index.get_entity(connection.target) is not None


def test_an_undrifted_repo_is_left_alone(repo: Path) -> None:
    source = _entity(repo, "requirement", "Clean Source")
    target = _entity(repo, "outcome", "Clean Target")
    mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type="archimate-realization",
        description="Realizes it.", dry_run=False, repo_root=str(repo),
    )

    index = shared_artifact_index([repo])
    index.refresh()

    assert [c.target for c in index.find_connections_for(source, direction="outbound")] == [target]


def test_every_producer_goes_through_the_same_door(drifted: tuple[Path, str, str]) -> None:
    """upsert_connection is the single incremental entry point for a connection record.

    Canonicalizing at a call site instead covers only the producer that call site serves:
    diagram-owned connections reach the read model through the same door from a different
    caller, and would enter unresolved.
    """
    repo, source, target = drifted
    index = shared_artifact_index([repo])
    index.refresh()
    raw = parse_outgoing_file(next(repo.rglob(f"{source}.outgoing.md")))[0]
    assert raw.target != target, "fixture no longer exercises drift"

    index._db.upsert_connection(raw)

    assert index._mem.connections[raw.artifact_id].target == target
