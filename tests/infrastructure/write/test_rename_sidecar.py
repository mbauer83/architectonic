"""Tests for entity+sidecar rename atomicity: M4 transaction path and sidecar-less os.rename path."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write._entity_rename import rename_entity_via_m4
from src.infrastructure.write.artifact_write.m4_transaction import recover_transactions


class SimulatedKill(BaseException):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_entity_with_sidecar(
    repo_root: Path,
    *,
    artifact_id: str = "model.entities.old-name",
    entity_content: str = "entity content",
    sidecar_content: str = "",
) -> tuple[Path, Path]:
    entity_file = repo_root / "model" / "entities" / f"{artifact_id}.md"
    sidecar_file = entity_file.with_suffix(".outgoing.md")
    _write(entity_file, entity_content)
    _write(sidecar_file, sidecar_content or f"artifact-id: {artifact_id}\n")
    return entity_file, sidecar_file


@pytest.fixture()
def mcp_repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type,
        name=name,
        summary=f"Summary for {name}",
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _make_connection(repo: Path, src: str, tgt: str, conn_type: str) -> None:
    result = mcp.artifact_add_connection(
        source_entity=src,
        connection_type=conn_type,
        target_entity=tgt,
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result


def _no_transactions(repo_root: Path) -> bool:
    txns = repo_root / ".arch-repo" / "transactions"
    return not txns.exists() or not any(txns.iterdir())


# ---------------------------------------------------------------------------
# Direct M4 rename tests (with sidecar)
# ---------------------------------------------------------------------------


def test_rename_with_sidecar_happy_path(tmp_path: Path) -> None:
    """rename_entity_via_m4 atomically moves entity+sidecar and cleans up the transaction dir."""
    repo_root = tmp_path / "repo"
    old_id = "model.entities.old-name"
    new_id = "model.entities.new-name"
    entity_file, old_sidecar = _make_entity_with_sidecar(repo_root, artifact_id=old_id)
    target_entity_file = entity_file.parent / f"{new_id}.md"
    new_sidecar = target_entity_file.with_suffix(".outgoing.md")

    rebuilt: list[str] = []
    rename_entity_via_m4(
        entity_file=entity_file,
        target_entity_file=target_entity_file,
        new_content="new entity content",
        repo_root=repo_root,
        artifact_id=old_id,
        effective_artifact_id=new_id,
        rebuild_index=lambda: rebuilt.append("rebuilt"),
    )

    assert not entity_file.exists()
    assert not old_sidecar.exists()
    assert target_entity_file.read_text(encoding="utf-8") == "new entity content"
    assert new_sidecar.exists()
    assert rebuilt, "rebuild_index must be called after commit"
    assert _no_transactions(repo_root), "transaction dir must be removed after commit"


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        ("payloads_written", "pre"),
        ("intent_installed", "post"),
        ("entry_applied:0", "post"),
        ("entry_applied:1", "post"),
        ("entry_applied:2", "post"),
        ("entry_applied:3", "post"),
        ("done_written", "post"),
        ("index_rebuilt", "post"),
    ],
)
def test_rename_sidecar_boundary_kill_recovers(
    tmp_path: Path, boundary: str, expected: str
) -> None:
    """Kill at any M4 boundary recovers to pre or post state — never a half-state."""
    repo_root = tmp_path / "repo"
    old_id = "model.entities.old"
    new_id = "model.entities.new"
    entity_file, old_sidecar = _make_entity_with_sidecar(repo_root, artifact_id=old_id)
    target_entity_file = entity_file.parent / f"{new_id}.md"
    new_sidecar = target_entity_file.with_suffix(".outgoing.md")
    rebuilt: list[str] = []

    def kill_at(name: str) -> None:
        if name == boundary:
            raise SimulatedKill

    with pytest.raises(SimulatedKill):
        rename_entity_via_m4(
            entity_file=entity_file,
            target_entity_file=target_entity_file,
            new_content="content",
            repo_root=repo_root,
            artifact_id=old_id,
            effective_artifact_id=new_id,
            rebuild_index=lambda: rebuilt.append("rebuilt"),
            on_boundary=kill_at,
        )

    recover_transactions(repo_root, rebuild_index=lambda: rebuilt.append("recovered"))

    if expected == "pre":
        assert entity_file.exists() and old_sidecar.exists()
        assert not target_entity_file.exists() and not new_sidecar.exists()
    else:
        assert not entity_file.exists() and not old_sidecar.exists()
        assert target_entity_file.exists() and new_sidecar.exists()
        assert rebuilt, "rebuild_index must be called during recovery"

    assert _no_transactions(repo_root), "all transactions cleaned up after recovery"


def test_connection_edit_after_rename_has_exactly_one_sidecar(tmp_path: Path) -> None:
    """After rename, exactly one sidecar exists at the new identity — old sidecar is gone."""
    repo_root = tmp_path / "repo"
    old_id = "model.entities.original"
    new_id = "model.entities.renamed"
    entity_file, old_sidecar = _make_entity_with_sidecar(repo_root, artifact_id=old_id)
    target_entity_file = entity_file.parent / f"{new_id}.md"
    new_sidecar = target_entity_file.with_suffix(".outgoing.md")

    rename_entity_via_m4(
        entity_file=entity_file,
        target_entity_file=target_entity_file,
        new_content="renamed entity content",
        repo_root=repo_root,
        artifact_id=old_id,
        effective_artifact_id=new_id,
        rebuild_index=lambda: None,
    )

    all_outgoing = sorted((repo_root / "model").rglob("*.outgoing.md"))
    assert all_outgoing == [new_sidecar], (
        f"expected exactly 1 sidecar at new path; got: {all_outgoing}"
    )
    assert not old_sidecar.exists()


# ---------------------------------------------------------------------------
# MCP-level sidecar-less rename (no outgoing connections → no sidecar)
# ---------------------------------------------------------------------------


def test_rename_without_sidecar_via_mcp(mcp_repo: Path) -> None:
    """Entity without connections (no sidecar) renames via os.rename without creating a transaction dir."""
    eid = _make_entity(mcp_repo, "requirement", "No Connections")
    entity_file = next((mcp_repo / "model").rglob(f"{eid}.md"))
    assert not entity_file.with_suffix(".outgoing.md").exists(), "precondition: no sidecar"

    result = mcp.artifact_edit_entity(
        artifact_id=eid,
        name="No Connections Renamed",
        dry_run=False,
        repo_root=str(mcp_repo),
    )

    assert result["wrote"] is True
    new_path = Path(str(result["path"]))
    assert new_path.exists()
    assert not entity_file.exists()
    assert _no_transactions(mcp_repo), "sidecar-less rename must not leave a transaction dir"
