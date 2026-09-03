"""Removing the last connection deletes the file, and the staged transaction carries that deletion.

Removing a connection normally *edits* `.outgoing.md`. Removing the last one **deletes** it, and that
removal is a side effect of the edit rather than an operation anyone requested — the batch was asked to
delete a connection, and a file disappeared. A side effect is exactly the kind of change a staged
transaction can drop: the manifest is derived from the paths a write reported touching, so a write that
unlinks without reporting would answer `wrote: true` in the staging copy and leave the file in the live
repository, with the tool's own dependency check still seeing the connection afterwards.

That was reported from use. It is not reproducible on this code — nine shapes were tried, including the
reported one exactly, and the deletion propagates every time — but the invariant is worth holding
because nothing else asserted it, and because the counts that look alarming in a report are normal:
a batch of seven items verifies **six** files when one of them was deleted, since a deleted file is not
a file to verify.

The manifest is asserted directly, not only the filesystem. A test that checked the file was gone would
pass on a build where the live repository is written directly and staging is bypassed, which is the one
thing that must not silently become true.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.infrastructure.write.artifact_write.batch_transaction as batch_transaction
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_delete

DIRECTED = "archimate-influence"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def manifest(monkeypatch) -> dict:
    """What the staged transaction decided to carry, captured as it is derived."""
    captured: dict = {}
    original = batch_transaction._derive_manifest_from_touched_paths

    def spy(**kwargs):
        entries, result = original(**kwargs)
        captured["entries"] = {Path(e.dest).name: e.kind for e in entries}
        captured["touched"] = {p.name for p in kwargs["touched_paths"]}
        return entries, result

    monkeypatch.setattr(batch_transaction, "_derive_manifest_from_touched_paths", spy)
    return captured


def _entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(artifact_type="value", name=name, dry_run=False, repo_root=str(repo))
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, metadata: dict | None = None) -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, connection_type=DIRECTED, target_entity=target,
        metadata=metadata, dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result


def _outgoing(repo: Path, artifact_id: str) -> list[Path]:
    stem = artifact_id.split(".")[1]
    return [p for p in repo.rglob("*.outgoing.md") if stem in p.name]


def _delete_connections(repo: Path, pairs: list[tuple[str, str]]) -> dict:
    return artifact_bulk_delete(
        items=[
            {"op": "delete_connection", "source_entity": s, "connection_type": DIRECTED, "target_entity": t}
            for s, t in pairs
        ],
        dry_run=False, repo_root=str(repo),
    )


class TestTheEmptiedFileIsRemovedFromTheLiveRepository:
    def test_the_manifest_carries_the_deletion_as_a_delete(self, repo: Path, manifest: dict) -> None:
        """The mechanism, not the outcome. A dropped side effect shows up here first."""
        target, lone, busy, spare = (_entity(repo, n) for n in ("Goal", "Lone", "Busy", "Spare"))
        _connect(repo, lone, target)
        _connect(repo, busy, target)
        _connect(repo, busy, spare)

        _delete_connections(repo, [(lone, target), (busy, target)])

        lone_file = f"{lone}.outgoing.md"
        busy_file = f"{busy}.outgoing.md"
        assert manifest["touched"] == {lone_file, busy_file}
        assert manifest["entries"] == {lone_file: "delete", busy_file: "replace"}

    def test_the_file_is_gone_and_the_surviving_one_is_not(self, repo: Path) -> None:
        target, lone, busy, spare = (_entity(repo, n) for n in ("Goal", "Lone", "Busy", "Spare"))
        _connect(repo, lone, target)
        _connect(repo, busy, target)
        _connect(repo, busy, spare)

        results = _delete_connections(repo, [(lone, target), (busy, target)])["results"]

        assert [r["wrote"] for r in results] == [True, True], results
        assert _outgoing(repo, lone) == []
        assert len(_outgoing(repo, busy)) == 1

    def test_the_entity_can_then_be_deleted(self, repo: Path) -> None:
        """The reported symptom: the dependency check still naming a connection reported deleted."""
        target, lone = _entity(repo, "Goal"), _entity(repo, "Lone")
        _connect(repo, lone, target)

        _delete_connections(repo, [(lone, target)])
        deleted = mcp.artifact_delete_entity(artifact_id=target, dry_run=False, repo_root=str(repo))

        assert deleted["wrote"], deleted

    def test_a_connection_carrying_attributes_is_no_different(self, repo: Path) -> None:
        """Reported alongside the failure, so pinned rather than assumed irrelevant."""
        target, lone = _entity(repo, "Goal"), _entity(repo, "Lone")
        _connect(repo, lone, target, metadata={"polarity": "positive"})

        results = _delete_connections(repo, [(lone, target)])["results"]

        assert results[0]["wrote"] and results[0]["warnings"] == ["Deleted empty .outgoing.md file"]
        assert _outgoing(repo, lone) == []


def test_a_deleted_file_is_not_a_verified_file(repo: Path) -> None:
    """Seven items verifying six files is arithmetic, not evidence of a dropped change.

    The report that prompted these tests read the discrepancy as proof the deletion never entered the
    change set. It is what a correct batch reports, and stating it here is cheaper than deriving it
    from a live repository again.
    """
    target, spare = _entity(repo, "Goal"), _entity(repo, "Spare")
    busy = [_entity(repo, f"Busy{i}") for i in range(6)]
    lone = _entity(repo, "Lone")
    for source in busy:
        _connect(repo, source, target)
        _connect(repo, source, spare)
    _connect(repo, lone, target)

    payload = _delete_connections(repo, [(source, target) for source in (*busy, lone)])

    assert all(r["wrote"] for r in payload["results"])
    assert len(payload["results"]) == 7
    assert payload["batch_verification"]["counts"]["files"] == 6
    assert _outgoing(repo, lone) == []
