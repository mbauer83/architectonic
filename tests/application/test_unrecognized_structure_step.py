"""Tests for the catch-all anomaly detector: fires on a narrow, well-understood
signal (missing/unrecognized `artifact-type`, malformed frontmatter); silent on ordinary
current content, diagrams, documents, and connection records — a false-positive check
against a realistic fixture repo, not just the positive cases."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.steps.unrecognized_structure import UnrecognizedStructureScanStep
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _view(root: Path) -> FilesystemRepoUpgradeView:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    return FilesystemRepoUpgradeView(root)


def test_silent_on_well_formed_entity_document_and_diagram(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "model/motivation/requirement/REQ@1.abc.name.md",
        "---\nartifact-id: REQ@1.abc.name\nartifact-type: requirement\nname: X\n---\nbody\n",
    )
    _write(
        tmp_path,
        "diagram-catalog/diagrams/uncategorized/D1.md",
        "---\nartifact-id: DIA@1.abc.d1\nartifact-type: diagram\nname: D1\n---\n@startuml\n@enduml\n",
    )
    _write(
        tmp_path,
        "docs/DOC1.md",
        "---\nartifact-id: DOC@1.abc.doc1\nartifact-type: document\ntitle: T\n---\nbody\n",
    )

    findings = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert findings == []


def test_silent_on_connection_record_without_artifact_type(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "model/motivation/requirement/REQ@1.abc.name.outgoing.md",
        "---\nsource-entity: REQ@1.abc.name\nversion: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n"
        "---\n<!-- §connections -->\n",
    )

    findings = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert findings == []


def test_silent_on_plain_markdown_without_frontmatter(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", "# Just a doc\n\nNo frontmatter here.\n")

    findings = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert findings == []


def test_fires_on_missing_artifact_type(tmp_path: Path) -> None:
    _write(tmp_path, "model/weird/WEIRD.md", "---\nartifact-id: WEIRD@1.abc.x\nname: X\n---\nbody\n")

    (finding,) = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("missing-artifact-type:")
    assert finding.auto_migratable is False
    assert finding.severity == "warning"
    assert finding.manual_instructions is not None


def test_fires_on_unrecognized_artifact_type(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "model/weird/WEIRD.md",
        "---\nartifact-id: WEIRD@1.abc.x\nartifact-type: not-a-real-type\nname: X\n---\nbody\n",
    )

    (finding,) = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("unrecognized-artifact-type:")


def test_fires_on_malformed_frontmatter_block(tmp_path: Path) -> None:
    _write(tmp_path, "model/weird/WEIRD.md", "---\nno closing marker at all\nbody\n")

    (finding,) = UnrecognizedStructureScanStep().detect(_view(tmp_path))

    assert finding.finding_id.startswith("malformed-frontmatter:")


def test_apply_repository_never_writes_and_reports_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "model/weird/WEIRD.md", "---\nartifact-id: WEIRD@1.abc.x\nname: X\n---\nbody\n")
    view = _view(tmp_path)

    write_calls: list[str] = []

    class _SpyWriter(FilesystemRepoUpgradeWriter):
        def write_text(self, relative_path: str, content: str) -> None:
            write_calls.append(relative_path)
            super().write_text(relative_path, content)

    registry = StepRegistry()
    registry.register(UnrecognizedStructureScanStep())

    report = apply_repository(view, _SpyWriter(tmp_path), registry=registry, software_version="0.0.0-test")

    assert write_calls == []
    assert len(report.results) == 1
    assert report.results[0].outcome == "skipped"
    assert report.results[0].finding.auto_migratable is False
    assert report.touched_locations == frozenset()
