"""`ARCH_SETTINGS_PATH` selects the runtime settings document (stage 1 sharing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import load_settings, settings_document_path


class TestSettingsDocumentSelection:
    def test_default_is_the_source_tree_document(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ARCH_SETTINGS_PATH", raising=False)
        path = settings_document_path()
        assert path.name == "settings.yaml"
        assert path.parent.name == "config"

    def test_env_selector_wins_and_load_settings_reads_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        doc = tmp_path / "settings.yaml"
        doc.write_text("backend:\n  port: 9321\n", encoding="utf-8")
        monkeypatch.setenv("ARCH_SETTINGS_PATH", str(doc))
        assert settings_document_path() == doc
        assert load_settings()["backend"]["port"] == 9321

    def test_absent_env_document_falls_back_to_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ARCH_SETTINGS_PATH", str(tmp_path / "missing.yaml"))
        settings = load_settings()
        assert settings["backend"]["port"] == 8000
