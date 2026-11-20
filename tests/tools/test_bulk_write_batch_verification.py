"""`artifact_bulk_write` answers with what verifying the batch as a whole found.

A batch is verified twice: each item as it is applied, and the staged repository once every item has
been. The second pass sees what no item can — a file the batch rewrote as a consequence rather than as
a request, such as a diagram naming an entity the batch renamed. Its findings are the batch's, stated
once beside the items, as `artifact_bulk_delete` states them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import (
    artifact_bulk_delete,
    artifact_bulk_write,
    artifact_get_operation,
)

_REFUSED_DIAGRAM = "hand-written.puml"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make(repo: Path, artifact_type: str, name: str) -> str:
    created = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo)
    )
    assert created["wrote"], created
    return str(created["artifact_id"])


def _rename_a_diagram_cannot_follow(repo: Path) -> list[dict[str, Any]]:
    """A batch whose one item is accepted and whose staged repository is refused.

    Renaming an entity rewrites every diagram that names it, so the diagram becomes part of the batch.
    This one's body draws nothing the model knows, which the rename itself has no reason to notice.
    """
    entity_id = _make(repo, "requirement", "Named In A Diagram")
    (repo / "diagram-catalog" / "diagrams" / _REFUSED_DIAGRAM).write_text(
        f"""\
---
artifact-id: hand-written
artifact-type: diagram
diagram-type: archimate-application
name: "Hand written"
entity-ids-used:
  - {entity_id}
version: 0.1.0
status: draft
last-updated: '2026-04-28'
---
@startuml
Alice -> Bob
@enduml
""",
        encoding="utf-8",
    )
    return [{"op": "edit_entity", "artifact_id": entity_id, "name": "Renamed Away"}]


def _a_connection_beside_a_stale_one(repo: Path) -> list[dict[str, Any]]:
    """A batch that is accepted, and whose staged repository carries a warning.

    The source already holds a connection naming its target by a slug the target no longer has. Adding
    a second connection rewrites that file; the stale name is a warning on the file, not on the item.
    """
    source = _make(repo, "requirement", "Warned Source")
    target = _make(repo, "outcome", "Warned Target")
    other = _make(repo, "outcome", "Other Target")
    added = mcp.artifact_add_connection(
        source_entity=source, connection_type="archimate-realization", target_entity=target,
        dry_run=False, repo_root=str(repo),
    )
    outgoing = Path(str(added["path"]))
    outgoing.write_text(
        outgoing.read_text(encoding="utf-8").replace(target, f"{target.rsplit('.', 1)[0]}.an-older-name"),
        encoding="utf-8",
    )
    return [{
        "op": "add_connection", "source_entity": source,
        "connection_type": "archimate-realization", "target_entity": other,
    }]


def _verification(payload: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], payload["batch_verification"])


def _codes(payload: dict[str, object]) -> set[str]:
    return {
        issue["code"] for result in _verification(payload)["results"] for issue in result["issues"]
    }


# ── A batch the verification refuses ──────────────────────────────────────────


def test_a_dry_run_reports_what_the_batch_would_be_refused_for(repo: Path) -> None:
    """The regression: every item read "Batch verification failed before commit" and nothing said why."""
    payload = artifact_bulk_write(
        items=_rename_a_diagram_cannot_follow(repo), dry_run=True, repo_root=str(repo)
    )

    verification = _verification(payload)
    assert verification["valid"] is False
    assert verification["executed"] is True
    assert verification["counts"]["errors"] >= 1
    refused = [result for result in verification["results"] if not result["valid"]]
    assert [Path(result["path"]).name for result in refused] == [_REFUSED_DIAGRAM]
    assert all(issue["message"] for issue in refused[0]["issues"])
    assert payload["committed"] is False


def test_a_refused_write_reports_the_same_findings_and_commits_nothing(repo: Path) -> None:
    items = _rename_a_diagram_cannot_follow(repo)
    payload = artifact_bulk_write(items=items, dry_run=False, repo_root=str(repo))

    assert _verification(payload)["valid"] is False
    assert _codes(payload), "the findings are what a caller acts on"
    assert payload["committed"] is False
    assert list((repo / "model").rglob("*renamed-away*")) == []


def test_the_findings_are_stated_once_and_each_item_points_at_them(repo: Path) -> None:
    payload = artifact_bulk_write(
        items=_rename_a_diagram_cannot_follow(repo), dry_run=True, repo_root=str(repo),
        return_mode="full",
    )

    items = cast(list[dict[str, Any]], payload["items"])
    assert all("Batch verification failed" in str(item["error"]) for item in items)
    assert all("batch_verification" in str(item["error"]) for item in items)
    assert all(_REFUSED_DIAGRAM not in str(item) for item in items), "findings are the batch's"


def test_findings_name_the_repository_rather_than_the_staging_copy(repo: Path) -> None:
    """The staging directory is gone by the time the caller reads the answer."""
    payload = artifact_bulk_write(
        items=_rename_a_diagram_cannot_follow(repo), dry_run=True, repo_root=str(repo),
        return_mode="full",
    )

    assert ".arch-repo/transactions" not in str(_verification(payload))
    assert _verification(payload)["results"][0]["path"] == str(
        repo / "diagram-catalog" / "diagrams" / _REFUSED_DIAGRAM
    )


# ── A batch the verification accepts with a warning ───────────────────────────


@pytest.mark.parametrize("dry_run", [True, False])
def test_an_accepted_batch_still_reports_its_warnings(repo: Path, dry_run: bool) -> None:
    payload = artifact_bulk_write(
        items=_a_connection_beside_a_stale_one(repo), dry_run=dry_run, repo_root=str(repo)
    )

    verification = _verification(payload)
    assert verification["valid"] is True
    assert verification["counts"]["warnings"] >= 1
    assert "W121" in _codes(payload)
    assert payload["committed"] is (not dry_run)
    assert payload["failed_count"] == 0


def test_a_clean_batch_reports_a_verification_with_nothing_in_it(repo: Path) -> None:
    payload = artifact_bulk_write(
        items=[{"op": "create_entity", "artifact_type": "requirement", "name": "Clean"}],
        dry_run=False, repo_root=str(repo),
    )

    verification = _verification(payload)
    assert (verification["valid"], verification["executed"]) == (True, True)
    assert verification["results"] == []
    assert verification["counts"]["files"] >= 1


# ── A batch that never reached verification ───────────────────────────────────


@pytest.mark.parametrize(
    "items",
    [
        pytest.param([{"op": "edit_entity", "artifact_id": "REQ@1.nosuch", "name": "Nope"}], id="item-failed"),
        pytest.param([{"op": "not_an_op", "name": "X"}], id="unknown-op"),
    ],
)
def test_a_batch_stopped_before_verification_says_it_was_not_verified(
    repo: Path, items: list[dict[str, Any]]
) -> None:
    payload = artifact_bulk_write(items=items, dry_run=False, repo_root=str(repo))

    verification = _verification(payload)
    assert verification["executed"] is False
    assert verification["valid"] is False
    assert verification["results"] == []


# ── Every way of reading the answer ───────────────────────────────────────────


@pytest.mark.parametrize("return_mode", ["summary", "full", "ids"])
def test_the_findings_survive_every_return_mode(repo: Path, return_mode: str) -> None:
    payload = artifact_bulk_write(
        items=_rename_a_diagram_cannot_follow(repo), dry_run=True, repo_root=str(repo),
        return_mode=cast(Any, return_mode),
    )

    verification = _verification(payload)
    assert verification["valid"] is False
    assert _codes(payload)
    assert {"valid", "executed", "counts", "results"} <= set(verification)
    assert "content" not in str(payload), "no file content, in any mode"


def test_the_compact_modes_carry_the_findings_and_not_the_bookkeeping(repo: Path) -> None:
    items = _rename_a_diagram_cannot_follow(repo)
    answers = {
        mode: artifact_bulk_write(
            items=items, dry_run=True, repo_root=str(repo), return_mode=cast(Any, mode)
        )
        for mode in ("summary", "full", "ids")
    }

    assert set(_verification(answers["summary"])) == {"valid", "executed", "counts", "results"}
    assert set(_verification(answers["ids"])) == set(_verification(answers["summary"]))
    assert set(_verification(answers["full"])) > set(_verification(answers["summary"]))
    assert _codes(answers["summary"]) == _codes(answers["full"])


def test_a_replayed_batch_answers_with_the_findings_it_was_refused_for(repo: Path) -> None:
    items = _rename_a_diagram_cannot_follow(repo)
    key = "batch-verification-replay"
    first = artifact_bulk_write(
        items=items, dry_run=False, repo_root=str(repo), idempotency_key=key, return_mode="ids"
    )
    replayed = artifact_bulk_write(
        items=items, dry_run=False, repo_root=str(repo), idempotency_key=key, return_mode="full"
    )

    assert replayed["operation_id"] == first["operation_id"]
    assert _codes(replayed) == _codes(first) != set()
    assert "repo_root" in _verification(replayed), "a replay can be widened back to the full record"
    assert "repo_root" not in _verification(first)


def test_the_recorded_operation_keeps_the_findings(repo: Path) -> None:
    payload = artifact_bulk_write(
        items=_rename_a_diagram_cannot_follow(repo), dry_run=False, repo_root=str(repo)
    )

    operation = artifact_get_operation(operation_id=cast(str, payload["operation_id"]))
    recorded = cast(dict[str, Any], operation["result"])

    assert recorded["batch_verification"]["valid"] is False
    assert recorded["batch_verification"]["results"]


# ── The delete side reads the same findings the same way ──────────────────────


def test_bulk_delete_lists_a_warning_on_a_file_it_leaves_valid(repo: Path) -> None:
    """Both tools answer through one verification payload, so a warning counted is a warning listed."""
    write_items = _a_connection_beside_a_stale_one(repo)
    source = write_items[0]["source_entity"]
    artifact_bulk_write(items=write_items, dry_run=False, repo_root=str(repo))

    payload = artifact_bulk_delete(
        items=[{
            "op": "delete_connection", "source_entity": source,
            "connection_type": "archimate-realization",
            "target_entity": write_items[0]["target_entity"],
        }],
        dry_run=True, repo_root=str(repo),
    )

    verification = cast(dict[str, Any], payload["batch_verification"])
    assert verification["valid"] is True
    listed = {issue["code"] for result in verification["results"] for issue in result["issues"]}
    assert verification["counts"]["warnings"] == len(listed) == 1
    assert listed == {"W121"}
