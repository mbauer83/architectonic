"""Text-file operational targets: staged atomic writes + cache version probing."""

from __future__ import annotations

from pathlib import Path

from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.deployment.file_targets import (
    GuidanceCacheHandle,
    SettingsDocumentHandle,
    guidance_cache_version,
)


def _target(kind: str, location: str) -> UpgradeTarget:
    return UpgradeTarget(
        kind=kind,  # type: ignore[arg-type]
        stable_id=f"{kind}:{location}",
        display_location=location,
        current_version=None,
    )


class TestSettingsDocumentHandle:
    def test_view_reads_and_uow_writes_atomically(self, tmp_path: Path) -> None:
        doc = tmp_path / "settings.yaml"
        doc.write_text("signals_backend: encrypted\n", encoding="utf-8")
        handle = SettingsDocumentHandle(target=_target("deployment_settings", str(doc)), path=doc)

        assert handle.view().read_text() == "signals_backend: encrypted\n"

        uow = handle.begin()
        uow.write_text("", "signals_backend: sqlcipher-colocated\n")
        # Staged, not yet visible:
        assert doc.read_text(encoding="utf-8") == "signals_backend: encrypted\n"
        uow.commit()
        assert doc.read_text(encoding="utf-8") == "signals_backend: sqlcipher-colocated\n"
        assert not list(tmp_path.glob("*.tmp-*"))

    def test_rollback_discards_staged_writes(self, tmp_path: Path) -> None:
        doc = tmp_path / "settings.yaml"
        doc.write_text("a: 1\n", encoding="utf-8")
        handle = SettingsDocumentHandle(target=_target("deployment_settings", str(doc)), path=doc)
        uow = handle.begin()
        uow.write_text("", "a: 2\n")
        uow.rollback()
        uow.commit()  # committing after rollback writes nothing
        assert doc.read_text(encoding="utf-8") == "a: 1\n"


class TestGuidanceCacheHandle:
    def test_directory_view_lists_and_reads_members(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("guidance_format: 1\n", encoding="utf-8")
        (tmp_path / "a.guidance.meta.yaml").write_text("sha256: x\n", encoding="utf-8")
        handle = GuidanceCacheHandle(target=_target("guidance_cache", str(tmp_path)), root=tmp_path)
        view = handle.view()
        assert view.list_files("*.guidance.yaml") == ["a.guidance.yaml"]
        assert view.read_text("a.guidance.yaml") == "guidance_format: 1\n"

    def test_uow_writes_members_atomically(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("guidance_format: 1\n", encoding="utf-8")
        handle = GuidanceCacheHandle(target=_target("guidance_cache", str(tmp_path)), root=tmp_path)
        uow = handle.begin()
        uow.write_text("a.guidance.yaml", "guidance_format: 2\n")
        uow.commit()
        assert (tmp_path / "a.guidance.yaml").read_text(encoding="utf-8") == "guidance_format: 2\n"


class TestGuidanceCacheVersion:
    def test_lowest_format_across_documents(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("guidance_format: 2\n", encoding="utf-8")
        (tmp_path / "b.guidance.yaml").write_text("guidance_format: 1\n", encoding="utf-8")
        assert guidance_cache_version(tmp_path) == 1

    def test_empty_cache_has_no_version(self, tmp_path: Path) -> None:
        assert guidance_cache_version(tmp_path) is None

    def test_unreadable_document_is_never_assumed_current(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("guidance_format: [unclosed\n", encoding="utf-8")
        assert guidance_cache_version(tmp_path) is None

    def test_missing_format_key_is_unknown(self, tmp_path: Path) -> None:
        (tmp_path / "a.guidance.yaml").write_text("meta_ontologies: {}\n", encoding="utf-8")
        assert guidance_cache_version(tmp_path) is None
