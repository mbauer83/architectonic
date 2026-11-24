"""The bulk write's transaction core carries an entity removal, after the connections it removes.

Applying a change set needs a removal and the rest of the set in one transaction. The core takes
`delete_entity` when its caller accepts it, and stages it last; the public tool does not accept it,
and leaves removal to `artifact_bulk_delete` as its description says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk.write import CHANGE_SET_OPS, artifact_bulk_write, write_batch

_REALIZATION = "archimate-realization"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _joined(repo: Path) -> tuple[str, str]:
    source = mcp.artifact_create_entity(
        artifact_type="application-component", name="Billing", dry_run=False, repo_root=str(repo),
    )["artifact_id"]
    target = mcp.artifact_create_entity(
        artifact_type="requirement", name="Old rule", dry_run=False, repo_root=str(repo),
    )["artifact_id"]
    joined = mcp.artifact_add_connection(
        source_entity=source, connection_type=_REALIZATION, target_entity=target, dry_run=False, repo_root=str(repo),
    )
    assert joined["wrote"], joined
    return str(source), str(target)


def _files(repo: Path) -> list[str]:
    return sorted(path.name for path in (repo / "model").rglob("*.md"))


def test_a_removal_listed_first_is_staged_after_the_disconnect(repo: Path) -> None:
    source, target = _joined(repo)
    items = [
        {"op": "delete_entity", "artifact_id": target},
        {"op": "edit_connection", "source_entity": source, "connection_type": _REALIZATION,
         "target_entity": target, "operation": "remove"},
    ]

    answer = write_batch(items=items, accepted_ops=CHANGE_SET_OPS, tool_name="test", dry_run=False,
                         repo_root=str(repo))

    assert answer["committed"] is True, answer
    assert not any(name.startswith(target) for name in _files(repo))


def test_a_removal_of_what_is_still_connected_refuses_the_whole_batch(repo: Path) -> None:
    source, target = _joined(repo)
    before = _files(repo)

    answer = write_batch(
        items=[{"op": "edit_entity", "artifact_id": source, "summary": "Renamed"},
               {"op": "delete_entity", "artifact_id": target}],
        accepted_ops=CHANGE_SET_OPS, tool_name="test", dry_run=False, repo_root=str(repo), return_mode="full",
    )

    assert answer["committed"] is False
    assert "still referenced" in str(answer["items"])
    assert _files(repo) == before


def test_the_public_tool_still_leaves_removal_to_the_bulk_delete(repo: Path) -> None:
    _source, target = _joined(repo)

    answer = artifact_bulk_write(items=[{"op": "delete_entity", "artifact_id": target}], dry_run=False,
                                 repo_root=str(repo), return_mode="full")

    assert answer["committed"] is False
    assert "Unknown op 'delete_entity'" in str(answer["items"])
