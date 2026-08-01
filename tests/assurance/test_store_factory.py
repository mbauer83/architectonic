"""Tests for store_factory + storage settings config loading.

Covers:
  - Factory builds port-typed adapters for sqlcipher, private-git backends
  - Unknown backend fails closed (ValueError)
  - Signals backend incompatibility detected (sqlcipher-colocated + non-sqlcipher)
  - Config loader returns correct defaults and overrides
  - clear_factory_cache evicts cached bundles
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Settings helpers ──────────────────────────────────────────────────────────


class TestStorageSettings:
    def test_default_store_backend(self) -> None:
        from src.config.storage_settings import storage_assurance_store_backend

        # settings.yaml has sqlcipher as default
        assert storage_assurance_store_backend() in {"sqlcipher", "pocketbase", "private-git"}

    def test_default_signals_backend(self) -> None:
        from src.config.storage_settings import storage_assurance_signals_backend

        assert storage_assurance_signals_backend() in {"sqlcipher-colocated", "sqlite", "encrypted"}

    def test_default_max_classification(self) -> None:
        from src.config.storage_settings import storage_assurance_max_classification

        assert storage_assurance_max_classification() in {"TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED"}

    def test_unknown_store_backend_fails_closed(self) -> None:
        from src.config.storage_settings import storage_assurance_store_backend

        with patch("src.config.settings.load_settings") as mock_load:
            mock_load.return_value = {
                "storage": {"assurance": {"store_backend": "unknown-db"}}
            }
            with pytest.raises(ValueError, match="Unknown storage.assurance.store_backend"):
                storage_assurance_store_backend()

    def test_unknown_signals_backend_fails_closed(self) -> None:
        from src.config.storage_settings import storage_assurance_signals_backend

        with patch("src.config.settings.load_settings") as mock_load:
            mock_load.return_value = {
                "storage": {"assurance": {"signals_backend": "badvalue"}}
            }
            with pytest.raises(ValueError, match="Unknown storage.assurance.signals_backend"):
                storage_assurance_signals_backend()

    def test_invalid_tlp_falls_back_to_amber(self) -> None:
        from src.config.storage_settings import storage_assurance_max_classification

        with patch("src.config.settings.load_settings") as mock_load:
            mock_load.return_value = {
                "storage": {"assurance": {"max_classification": "TLP:ULTRAVIOLET"}}
            }
            assert storage_assurance_max_classification() == "TLP:AMBER"

    def test_storage_read_model_seam(self) -> None:
        from src.config.storage_settings import storage_read_model_seam

        seam = storage_read_model_seam()
        assert isinstance(seam, dict)

    def test_load_settings_includes_storage(self) -> None:
        from src.config.settings import load_settings

        settings = load_settings()
        assert "storage" in settings
        assert "assurance" in settings["storage"]
        assert "read_model" in settings["storage"]


# ── Factory: private-git backend ──────────────────────────────────────────────


class TestStoreFactoryPrivateGit:
    def setup_method(self) -> None:
        from src.infrastructure.assurance.store_factory import clear_factory_cache
        clear_factory_cache()

    def teardown_method(self) -> None:
        from src.infrastructure.assurance.store_factory import clear_factory_cache
        clear_factory_cache()

    def test_builds_private_git_bundle(self) -> None:
        from src.application.assurance.ports import (
            AssuranceArchive,
            ConfidentialAssuranceStore,
        )
        from src.infrastructure.assurance.store_factory import get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            workspace = Path(tmpdir)
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "private-git",
                        "signals_backend": "sqlite",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            bundle = get_assurance_bundle(workspace)
            assert isinstance(bundle.store, ConfidentialAssuranceStore)
            assert isinstance(bundle.archive, AssuranceArchive)
            assert bundle.store_backend == "private-git"
            assert bundle.signals_backend == "sqlite"

    def test_workspace_keyed_singleton(self) -> None:
        from src.infrastructure.assurance.store_factory import get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            workspace = Path(tmpdir)
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "private-git",
                        "signals_backend": "sqlite",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            b1 = get_assurance_bundle(workspace)
            b2 = get_assurance_bundle(workspace)
            assert b1 is b2

    def test_different_workspaces_get_different_bundles(self) -> None:
        from src.infrastructure.assurance.store_factory import get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            tempfile.TemporaryDirectory() as tmp1,
            tempfile.TemporaryDirectory() as tmp2,
        ):
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "private-git",
                        "signals_backend": "sqlite",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            b1 = get_assurance_bundle(Path(tmp1))
            b2 = get_assurance_bundle(Path(tmp2))
            assert b1 is not b2

    def test_clear_cache_evicts_bundle(self) -> None:
        from src.infrastructure.assurance.store_factory import clear_factory_cache, get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            workspace = Path(tmpdir)
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "private-git",
                        "signals_backend": "sqlite",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            b1 = get_assurance_bundle(workspace)
            clear_factory_cache()
            b2 = get_assurance_bundle(workspace)
            assert b1 is not b2


# ── Factory: fail-closed cases ────────────────────────────────────────────────


class TestStoreFactoryFailClosed:
    def setup_method(self) -> None:
        from src.infrastructure.assurance.store_factory import clear_factory_cache
        clear_factory_cache()

    def teardown_method(self) -> None:
        from src.infrastructure.assurance.store_factory import clear_factory_cache
        clear_factory_cache()

    def test_colocated_signals_requires_sqlcipher(self) -> None:
        from src.infrastructure.assurance.store_factory import get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            workspace = Path(tmpdir)
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "private-git",
                        "signals_backend": "sqlcipher-colocated",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            with pytest.raises(ValueError, match="sqlcipher-colocated.*requires.*sqlcipher"):
                get_assurance_bundle(workspace)

    def test_pocketbase_missing_url_fails(self) -> None:
        from src.infrastructure.assurance.store_factory import get_assurance_bundle

        with (
            patch("src.config.settings.load_settings") as mock_load,
            patch.dict(os.environ, {}, clear=False),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            os.environ.pop("ARCH_POCKETBASE_URL", None)
            workspace = Path(tmpdir)
            mock_load.return_value = {
                "storage": {
                    "assurance": {
                        "store_backend": "pocketbase",
                        "signals_backend": "sqlite",
                        "max_classification": "TLP:AMBER",
                    }
                }
            }
            with pytest.raises(RuntimeError, match="ARCH_POCKETBASE_URL"):
                get_assurance_bundle(workspace)


# ── Local SQLite archive for non-SQLCipher backends ───────────────────────────


class TestLocalSQLiteArchive:
    def test_archive_round_trip(self) -> None:
        from src.infrastructure.assurance.store_factory import _make_local_sqlite_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_archive.db"
            archive = _make_local_sqlite_archive(path)
            entry = archive.append("TEST_OP", payload={"key": "val"})
            assert "seq" in entry
            assert entry["operation"] == "TEST_OP"
            entries = archive.list_entries()
            assert len(entries) == 1
            assert archive.verify_chain()

    def test_archive_path_created_lazily(self) -> None:
        from src.infrastructure.assurance.store_factory import _make_local_sqlite_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "archive.db"
            # sub/ does not exist yet — archive is created lazily on first access
            archive = _make_local_sqlite_archive(path)
            assert not path.exists()  # lazy: not created yet
            archive.append("LAZY_INIT", payload={})
            assert path.exists()
