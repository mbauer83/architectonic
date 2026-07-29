"""Operational-target discovery from a manifest: present surfaces only, correct
kinds/configured flags, credential-gated SQLCipher inspection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.domain.deployment.layout import (
    DeploymentManifest,
    ProvenanceEntry,
    ResolvedPathField,
    SettingsDocumentSelection,
)
from src.infrastructure.deployment import discovery
from src.infrastructure.deployment.discovery import discover_operational_handles


def _field(path: Path) -> ResolvedPathField:
    return ResolvedPathField(path, "compat_default", (ProvenanceEntry("compat_default", str(path)),))


def _manifest(
    tmp_path: Path,
    *,
    operator_owned: bool = True,
    signals_backend: str = "sqlcipher-colocated",
    store_backend: str = "sqlcipher",
) -> DeploymentManifest:
    source: str = "cli" if operator_owned else "source_tree_default"
    return DeploymentManifest(
        settings_document=SettingsDocumentSelection(tmp_path / "settings.yaml", source),  # type: ignore[arg-type]
        workspace_root=None,
        assurance_db_path=_field(tmp_path / ".arch-assurance" / "store.db"),
        signals_db_path=_field(tmp_path / ".arch-assurance" / "security-signals.db"),
        guidance_cache_root=_field(tmp_path / "guidance-cache"),
        store_backend=store_backend,
        signals_backend=signals_backend,
        archive_backend="standard",
        assurance_enabled=True,
        archive_identity=None,
    )


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(discovery, "_stored_key", lambda _path: None)


class TestDiscovery:
    def test_absent_surfaces_are_no_targets(self, tmp_path: Path) -> None:
        assert discover_operational_handles(_manifest(tmp_path)) == ()

    def test_source_tree_settings_document_is_never_a_target(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text("a: 1\n", encoding="utf-8")
        handles = discover_operational_handles(_manifest(tmp_path, operator_owned=False))
        assert [h.target.kind for h in handles] == []

    def test_operator_owned_settings_document_is_a_target(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text("a: 1\n", encoding="utf-8")
        handles = discover_operational_handles(_manifest(tmp_path))
        assert [h.target.kind for h in handles] == ["deployment_settings"]

    def test_guidance_cache_discovered_only_with_cached_documents(self, tmp_path: Path) -> None:
        cache = tmp_path / "guidance-cache"
        cache.mkdir()
        assert discover_operational_handles(_manifest(tmp_path)) == ()
        (cache / "archimate-4.guidance.yaml").write_text("guidance_format: 1\n", encoding="utf-8")
        handles = discover_operational_handles(_manifest(tmp_path))
        assert [h.target.kind for h in handles] == ["guidance_cache"]
        assert handles[0].target.current_version == 1

    def test_legacy_public_signals_file_is_discovered_even_when_not_configured(
        self, tmp_path: Path
    ) -> None:
        signals = tmp_path / ".arch-assurance" / "security-signals.db"
        signals.parent.mkdir(parents=True)
        conn = sqlite3.connect(signals)
        conn.execute("CREATE TABLE boms (id INTEGER)")
        conn.commit()
        conn.close()
        handles = discover_operational_handles(_manifest(tmp_path, signals_backend="sqlcipher-colocated"))
        assert [h.target.kind for h in handles] == ["signals_sqlite"]
        target = handles[0].target
        assert target.current_version == 0
        assert not target.configured

    def test_sqlcipher_store_without_credential_is_uninspectable(self, tmp_path: Path) -> None:
        store = tmp_path / ".arch-assurance" / "store.db"
        store.parent.mkdir(parents=True)
        store.write_bytes(b"SQLite format 3\x00" + b"\x00" * 32)
        handles = discover_operational_handles(_manifest(tmp_path))
        assert [h.target.kind for h in handles] == ["assurance_sqlcipher"]
        assert not handles[0].inspectable
        assert handles[0].target.current_version is None
        assert handles[0].target.credential_requirement == "sqlcipher_key"

    def test_sqlcipher_store_with_credential_reports_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sqlcipher3 = pytest.importorskip("sqlcipher3")
        store = tmp_path / ".arch-assurance" / "store.db"
        store.parent.mkdir(parents=True)
        conn = sqlcipher3.connect(str(store))
        conn.execute("PRAGMA key = 'k'")
        conn.execute("CREATE TABLE boms (id TEXT)")
        conn.commit()
        conn.close()
        monkeypatch.setattr(discovery, "_stored_key", lambda _path: "k")
        handles = discover_operational_handles(_manifest(tmp_path))
        assert handles[0].inspectable
        assert handles[0].target.current_version == 0
