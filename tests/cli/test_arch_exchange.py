"""``arch-exchange`` CLI (WU-F4, D10 §4.5): import/export subcommands over real tmp repos —
the underlying use cases (WU-F3a/F3b) already have their own dedicated test suites; this
file covers the CLI's own concerns: argv wiring, dry-run default, --commit, --scope, and
malformed-input error handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.cli import arch_exchange as cli
from src.infrastructure.mcp import mcp_artifact_server as mcp


def _eng_root(tmp_path: Path, tag: str) -> Path:
    root = tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _registry(root: Path) -> ArtifactRegistry:
    return ArtifactRegistry(shared_artifact_index([root]))


def _create(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert result["wrote"], result
    return str(result["artifact_id"])


def test_export_then_import_round_trip_via_main(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "CLI1")
    _create(source_root, "business-actor", "Alice Actor")
    out_path = tmp_path / "export.xml"

    export_exit = cli.main(["export", "--out", str(out_path), "--repo", str(source_root)])
    assert export_exit == 0
    assert out_path.exists()
    assert b"BusinessActor" in out_path.read_bytes()

    dest_root = _eng_root(tmp_path, "CLI2")
    import_exit = cli.main(["import", "--source", str(out_path), "--commit", "--repo", str(dest_root)])
    assert import_exit == 0

    dest_registry = _registry(dest_root)
    entities = [dest_registry.get_entity(e) for e in dest_registry.entity_ids()]
    names = {e.name for e in entities if e is not None}
    assert "Alice Actor" in names


def test_import_without_commit_writes_nothing(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "CLI3")
    _create(source_root, "business-actor", "Alice Actor")
    out_path = tmp_path / "export.xml"
    cli.main(["export", "--out", str(out_path), "--repo", str(source_root)])

    dest_root = _eng_root(tmp_path, "CLI4")
    exit_code = cli.main(["import", "--source", str(out_path), "--repo", str(dest_root)])

    assert exit_code == 0
    assert len(_registry(dest_root).entity_ids()) == 0


def test_export_scope_restricts_to_given_entities(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "CLI5")
    alice = _create(source_root, "business-actor", "Alice Actor")
    _create(source_root, "business-actor", "Bob Actor")
    out_path = tmp_path / "export.xml"

    report = cli.run_export(repo_root=source_root, out=out_path, scope=[alice])

    assert len(report.entities) == 1
    assert report.entities[0].artifact_id == alice
    assert b"Bob Actor" not in out_path.read_bytes()


def test_export_default_scope_exports_every_entity(tmp_path: Path) -> None:
    source_root = _eng_root(tmp_path, "CLI6")
    _create(source_root, "business-actor", "Alice Actor")
    _create(source_root, "business-actor", "Bob Actor")
    out_path = tmp_path / "export.xml"

    report = cli.run_export(repo_root=source_root, out=out_path, scope=None)

    assert len(report.entities) == 2


def test_import_malformed_document_reports_error_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bogus = tmp_path / "bogus.xml"
    bogus.write_text("not xml at all", encoding="utf-8")
    dest_root = _eng_root(tmp_path, "CLI7")

    exit_code = cli.main(["import", "--source", str(bogus), "--repo", str(dest_root)])

    assert exit_code == 1
    assert "ERROR" in capsys.readouterr().err


def test_import_report_prints_created_entities(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source_root = _eng_root(tmp_path, "CLI8")
    _create(source_root, "business-actor", "Alice Actor")
    out_path = tmp_path / "export.xml"
    cli.main(["export", "--out", str(out_path), "--repo", str(source_root)])

    dest_root = _eng_root(tmp_path, "CLI9")
    cli.main(["import", "--source", str(out_path), "--commit", "--repo", str(dest_root)])

    out = capsys.readouterr().out
    assert "created" in out
    assert "Alice Actor" in out
